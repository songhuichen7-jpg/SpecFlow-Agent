from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from specflow.agents import (
    ArchitectAgent,
    CoderAgent,
    ReviewerAgent,
    ReviewFixLoop,
)
from specflow.config import Settings, get_settings
from specflow.mcp import WorkspaceSandbox
from specflow.models import ExecutionEvent, ExecutionEventType, ExecutionMode, Project, RunStatus
from specflow.orchestrator.human_gate import (
    HumanGate,
    PendingHumanGate,
    resolve_gate_decision,
)
from specflow.orchestrator.logging import ExecutionLogger
from specflow.orchestrator.models import (
    HumanGateDecision,
    HumanGateRequest,
    ProjectConfig,
    SupervisorRunResult,
)
from specflow.storage import ArtifactRepository, CheckpointManager, RunStateManager
from specflow.storage.db import get_session_factory, session_scope
from specflow.templates import DEFAULT_TARGET_STACK


class SupervisorOrchestrator:
    """Deterministic Sprint 6 orchestration layer for full pipeline runs."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: sessionmaker[Session] | None = None,
        artifact_repository: ArtifactRepository | None = None,
        run_state_manager: RunStateManager | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        architect: ArchitectAgent | None = None,
        coder: CoderAgent | None = None,
        reviewer: ReviewerAgent | None = None,
        review_loop: ReviewFixLoop | None = None,
        human_gate: HumanGate | None = None,
        execution_logger: ExecutionLogger | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_runtime_directories()
        self.session_factory = (
            session_factory
            or (run_state_manager.session_factory if run_state_manager is not None else None)
            or get_session_factory()
        )
        self.artifact_repository = artifact_repository or ArtifactRepository(
            session_factory=self.session_factory,
            settings=self.settings,
        )
        self.run_state_manager = run_state_manager or RunStateManager(
            session_factory=self.session_factory,
            settings=self.settings,
            artifact_repository=self.artifact_repository,
        )
        self.checkpoint_manager = checkpoint_manager or CheckpointManager(
            settings=self.settings,
            artifact_repository=self.artifact_repository,
            run_state_manager=self.run_state_manager,
        )
        self.architect = architect or ArchitectAgent(
            settings=self.settings,
            session_factory=self.session_factory,
            artifact_repository=self.artifact_repository,
            run_state_manager=self.run_state_manager,
            checkpoint_manager=self.checkpoint_manager,
        )
        self.coder = coder or CoderAgent(
            settings=self.settings,
            session_factory=self.session_factory,
            artifact_repository=self.artifact_repository,
            run_state_manager=self.run_state_manager,
        )
        self.reviewer = reviewer or ReviewerAgent(
            settings=self.settings,
            session_factory=self.session_factory,
            artifact_repository=self.artifact_repository,
            run_state_manager=self.run_state_manager,
        )
        self.review_loop = review_loop or ReviewFixLoop(
            settings=self.settings,
            artifact_repository=self.artifact_repository,
            run_state_manager=self.run_state_manager,
            coder=self.coder,
            reviewer=self.reviewer,
        )
        self.human_gate = human_gate or PendingHumanGate()
        self.execution_logger = execution_logger or ExecutionLogger(
            run_state_manager=self.run_state_manager,
            session_factory=self.session_factory,
        )

    def start_run(
        self,
        *,
        input_prompt: str,
        mode: ExecutionMode | str = ExecutionMode.STANDARD,
        project_config: ProjectConfig | None = None,
        project_id: str | None = None,
        supplemental_inputs: list[str] | None = None,
        review_iterations: int = 1,
    ) -> SupervisorRunResult:
        execution_mode = ExecutionMode(mode)
        resolved_project_id = project_id or self.ensure_project(project_config or ProjectConfig())
        run = self.run_state_manager.create_run(
            project_id=resolved_project_id,
            input_prompt=input_prompt,
            mode=execution_mode,
            summary="Supervisor created the run and is preparing orchestration.",
        )
        self.execution_logger.log_run_summary(
            run.run_id,
            summary="Supervisor created the run.",
            payload={"project_id": resolved_project_id, "mode": execution_mode.value},
        )
        return self._continue_run(
            run.run_id,
            supplemental_inputs=supplemental_inputs,
            review_iterations=review_iterations,
        )

    def resume_run(
        self,
        run_id: str,
        *,
        decision: HumanGateDecision | bool | None = None,
        review_iterations: int = 1,
    ) -> SupervisorRunResult:
        snapshot = self.run_state_manager.load_run(run_id)
        pending_gate = self._latest_pending_gate(run_id)
        if snapshot.human_gate_pending:
            if pending_gate is None:
                raise ValueError(f"Run {run_id!r} is pending human approval without a gate record.")
            gate_result = self._resolve_pending_gate(
                run_id,
                pending_gate=pending_gate,
                mode=snapshot.mode,
                explicit_decision=decision,
            )
            if gate_result is not None:
                return gate_result
        return self._continue_run(run_id, review_iterations=review_iterations)

    def get_run_status(self, run_id: str) -> SupervisorRunResult:
        pending_gate = self._latest_pending_gate(run_id)
        return self._build_result(run_id, pending_gate=pending_gate)

    def ensure_project(self, config: ProjectConfig) -> str:
        with session_scope(self.session_factory) as session:
            existing = session.scalar(select(Project).where(Project.slug == config.slug))
            if existing is not None:
                existing.name = config.name
                existing.template_type = config.template_type
                existing.target_stack = config.target_stack
                existing.description = config.description
                return existing.id

            project = Project(
                id=str(uuid4()),
                name=config.name,
                slug=config.slug,
                template_type=config.template_type,
                target_stack=config.target_stack or DEFAULT_TARGET_STACK,
                description=config.description,
            )
            session.add(project)
            session.flush()
            return project.id

    def _continue_run(
        self,
        run_id: str,
        *,
        supplemental_inputs: list[str] | None = None,
        review_iterations: int = 1,
    ) -> SupervisorRunResult:
        snapshot = self.run_state_manager.load_run(run_id)
        if snapshot.status in {RunStatus.FAILED, RunStatus.COMPLETED, RunStatus.CANCELLED}:
            return self._build_result(run_id)

        if self._should_run_architect(run_id):
            self.execution_logger.log_agent_started(
                run_id,
                agent="architect",
                summary="Generating clarification, spec, plan, contracts, and task draft.",
            )
            architect_result = self._run_with_retries(
                run_id,
                agent_name="architect",
                operation=lambda: self.architect.run(
                    run_id,
                    supplemental_inputs=supplemental_inputs,
                ),
            )
            self.execution_logger.log_agent_completed(
                run_id,
                agent="architect",
                summary=(
                    "Architect generated spec artifacts."
                    f" completeness={architect_result.clarification.completeness_score}"
                ),
                payload={"artifacts": architect_result.artifact_versions},
            )

        if not self._gate_already_approved(run_id, "freeze_spec"):
            gate_result = self._handle_gate(
                run_id,
                gate_name="freeze_spec",
                message="Freeze the generated spec before implementation?",
                payload={"stage": "post_architect"},
            )
            if gate_result is not None:
                return gate_result

        current_phase = self.run_state_manager.load_run(run_id).current_phase
        if (
            current_phase.value in {"tasks", "implement"}
            and self._workspace_has_files(run_id)
            and not self._gate_already_approved(run_id, "overwrite_workspace")
        ):
            gate_result = self._handle_gate(
                run_id,
                gate_name="overwrite_workspace",
                message="Workspace already contains files. Allow the coder to overwrite them?",
                payload={"stage": "pre_coder"},
            )
            if gate_result is not None:
                return gate_result

        if self.run_state_manager.load_run(run_id).current_phase.value in {"tasks", "implement"}:
            self.execution_logger.log_agent_started(
                run_id,
                agent="coder",
                summary="Generating workspace files and running quality gates.",
            )
            coder_result = self._run_with_retries(
                run_id,
                agent_name="coder",
                operation=lambda: self.coder.run(run_id),
            )
            self.execution_logger.log_agent_completed(
                run_id,
                agent="coder",
                summary=f"Coder wrote {len(coder_result.written_files)} files.",
                payload={"artifacts": coder_result.artifact_versions},
            )
            self.execution_logger.log_quality_summary(run_id, result=coder_result)

        review_approved = False
        completed_review_iterations = 0
        if not self._gate_already_approved(run_id, "review_arbitration"):
            review_loop_result = self._run_with_retries(
                run_id,
                agent_name="review_loop",
                operation=lambda: self.review_loop.run(
                    run_id,
                    max_iterations=review_iterations,
                ),
            )
            completed_review_iterations = review_loop_result.iterations
            latest_review = review_loop_result.reviews[-1]
            self.execution_logger.log_review_summary(run_id, result=latest_review)
            review_approved = latest_review.approved

            if review_loop_result.requires_human_arbitration:
                pending_gate = self._latest_pending_gate(run_id)
                if pending_gate is None:
                    raise ValueError(
                        f"Run {run_id!r} requires human arbitration without a gate record."
                    )
                gate_result = self._resolve_pending_gate(
                    run_id,
                    pending_gate=pending_gate,
                    mode=self.run_state_manager.load_run(run_id).mode,
                )
                if gate_result is not None:
                    return gate_result
                review_approved = False

        if not self._gate_already_approved(run_id, "deliver"):
            gate_result = self._handle_gate(
                run_id,
                gate_name="deliver",
                message="Review passed. Approve final delivery?",
                payload={"stage": "pre_deliver", "review_approved": review_approved},
            )
            if gate_result is not None:
                return gate_result

        self.run_state_manager.complete_run(
            run_id,
            summary="Supervisor completed the run and finalized delivery.",
        )
        self.execution_logger.log_run_summary(
            run_id,
            summary="Supervisor completed the full delivery pipeline.",
            payload={
                "review_approved": review_approved,
                "iterations": completed_review_iterations,
            },
        )
        return self._build_result(run_id, review_approved=review_approved)

    def _handle_gate(
        self,
        run_id: str,
        *,
        gate_name: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> SupervisorRunResult | None:
        snapshot = self.run_state_manager.load_run(run_id)
        request = HumanGateRequest(
            run_id=run_id,
            gate_name=gate_name,
            phase=snapshot.current_phase,
            message=message,
            payload=cast(dict[str, object], payload or {}),
        )
        decision = resolve_gate_decision(
            mode=snapshot.mode,
            request=request,
            gate=self.human_gate,
        )
        if decision is None:
            self.run_state_manager.request_human_gate(
                run_id,
                message=message,
                payload={"gate_name": gate_name, **(payload or {})},
            )
            return self._build_result(run_id, pending_gate=request)
        self.run_state_manager.resolve_human_gate(
            run_id,
            approved=decision.approved,
            message=decision.reason,
            payload={"gate_name": gate_name, **(payload or {})},
        )
        if not decision.approved:
            self.execution_logger.log_run_summary(
                run_id,
                summary=f"Run stopped because gate {gate_name} was rejected.",
                payload={"gate_name": gate_name, "approved": False},
            )
            return self._build_result(run_id)
        self.execution_logger.log_run_summary(
            run_id,
            summary=f"Gate {gate_name} approved.",
            payload={"gate_name": gate_name, "approved": True},
        )
        return None

    def _resolve_pending_gate(
        self,
        run_id: str,
        *,
        pending_gate: HumanGateRequest,
        mode: ExecutionMode,
        explicit_decision: HumanGateDecision | bool | None = None,
    ) -> SupervisorRunResult | None:
        gate_decision = resolve_gate_decision(
            mode=mode,
            request=pending_gate,
            gate=self.human_gate,
            explicit_decision=explicit_decision,
        )
        if gate_decision is None:
            return self._build_result(run_id, pending_gate=pending_gate)
        self.run_state_manager.resolve_human_gate(
            run_id,
            approved=gate_decision.approved,
            message=gate_decision.reason,
            payload={"gate_name": pending_gate.gate_name, **pending_gate.payload},
        )
        if not gate_decision.approved:
            self.execution_logger.log_run_summary(
                run_id,
                summary=f"Human gate rejected: {pending_gate.gate_name}.",
                payload={"gate_name": pending_gate.gate_name, "approved": False},
            )
            return self._build_result(run_id)
        self.execution_logger.log_run_summary(
            run_id,
            summary=f"Gate {pending_gate.gate_name} approved.",
            payload={"gate_name": pending_gate.gate_name, "approved": True},
        )
        return None

    def _run_with_retries(
        self,
        run_id: str,
        *,
        agent_name: str,
        operation: Any,
        max_attempts: int = 2,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return operation()
            except Exception as exc:  # pragma: no cover - covered through supervisor tests
                last_error = exc
                if attempt < max_attempts:
                    self.run_state_manager.schedule_retry(
                        run_id,
                        message=f"Retrying {agent_name} after failure.",
                        payload={"attempt": attempt, "agent": agent_name},
                    )
                    self.execution_logger.log_run_summary(
                        run_id,
                        summary=f"Retry scheduled for {agent_name}.",
                        payload={"attempt": attempt, "agent": agent_name, "error": str(exc)},
                    )
                    continue
                self.run_state_manager.mark_phase_failed(
                    run_id,
                    message=f"{agent_name} failed after retries.",
                    error_details=str(exc),
                    payload={"agent": agent_name, "attempts": attempt},
                )
                self.execution_logger.log_run_summary(
                    run_id,
                    summary=f"{agent_name} failed after retries.",
                    payload={"agent": agent_name, "error": str(exc)},
                )
                raise
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"{agent_name} did not execute.")

    def _workspace_has_files(self, run_id: str) -> bool:
        sandbox = WorkspaceSandbox(
            run_id,
            settings=self.settings,
            artifact_repository=self.artifact_repository,
        )
        return any(sandbox.root.rglob("*"))

    def _should_run_architect(self, run_id: str) -> bool:
        snapshot = self.run_state_manager.load_run(run_id)
        if snapshot.current_phase.value in {"clarify", "specify", "plan"}:
            return True
        if snapshot.current_phase.value != "tasks":
            return False
        required = {"spec.md", "plan.md", "tasks.md", "data-model.md", "contracts/openapi.yaml"}
        present = {
            artifact.name
            for artifact in self.artifact_repository.list_artifacts(run_id, latest_only=True)
        }
        return not required.issubset(present)

    def _gate_already_approved(self, run_id: str, gate_name: str) -> bool:
        with session_scope(self.session_factory) as session:
            statement = (
                select(ExecutionEvent)
                .where(
                    ExecutionEvent.run_id == run_id,
                    ExecutionEvent.event_type == ExecutionEventType.HUMAN_GATE_APPROVED,
                )
                .order_by(ExecutionEvent.created_at.desc())
            )
            events = list(session.scalars(statement))
        return any(str(event.payload.get("gate_name")) == gate_name for event in events)

    def _latest_pending_gate(self, run_id: str) -> HumanGateRequest | None:
        snapshot = self.run_state_manager.load_run(run_id)
        if not snapshot.human_gate_pending:
            return None
        with session_scope(self.session_factory) as session:
            statement = select(ExecutionEvent).where(
                ExecutionEvent.run_id == run_id,
                ExecutionEvent.event_type == ExecutionEventType.HUMAN_GATE_REQUESTED,
            )
            events = list(session.scalars(statement))
        if not events:
            return None
        event = max(events, key=_gate_request_sort_key)
        payload = dict(event.payload)
        gate_name = str(payload.pop("gate_name", "human_gate"))
        return HumanGateRequest(
            run_id=run_id,
            gate_name=gate_name,
            phase=event.phase,
            message=event.message,
            payload=cast(dict[str, object], payload),
        )

    def _build_result(
        self,
        run_id: str,
        *,
        pending_gate: HumanGateRequest | None = None,
        review_approved: bool | None = None,
    ) -> SupervisorRunResult:
        snapshot = self.run_state_manager.load_run(run_id)
        artifacts = self.artifact_repository.list_artifacts(run_id, latest_only=True)
        workspace_root = str(self.artifact_repository.get_run_layout(run_id).workspace_dir)
        return SupervisorRunResult(
            run_id=run_id,
            project_id=snapshot.project_id,
            status=snapshot.status,
            current_phase=snapshot.current_phase,
            mode=snapshot.mode,
            review_approved=review_approved,
            pending_gate=pending_gate,
            artifact_names=sorted(artifact.name for artifact in artifacts),
            workspace_root=workspace_root,
            summary=snapshot.summary,
        )


def _gate_request_sort_key(event: ExecutionEvent) -> tuple[int, str, str]:
    raw_sequence = event.payload.get("gate_sequence", 0)
    try:
        gate_sequence = int(raw_sequence)
    except (TypeError, ValueError):
        gate_sequence = 0
    return (gate_sequence, event.created_at.isoformat(), event.id)
