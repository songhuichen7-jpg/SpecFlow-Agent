from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from specflow.config import Settings, get_settings
from specflow.models import (
    ExecutionEvent,
    ExecutionEventType,
    ExecutionMode,
    Project,
    Run,
    RunPhase,
    RunStatus,
)
from specflow.storage.artifacts import ArtifactRepository
from specflow.storage.db import get_session_factory, session_scope
from specflow.storage.types import RunStateSnapshot

PHASE_SEQUENCE = (
    RunPhase.CLARIFY,
    RunPhase.SPECIFY,
    RunPhase.PLAN,
    RunPhase.TASKS,
    RunPhase.IMPLEMENT,
    RunPhase.REVIEW,
    RunPhase.DELIVER,
)
PHASE_INDEX = {phase: index for index, phase in enumerate(PHASE_SEQUENCE)}


class RunNotFoundError(LookupError):
    """Raised when a run_id cannot be loaded."""


class InvalidPhaseTransitionError(ValueError):
    """Raised when a phase move violates the state machine."""


class RunStateManager:
    """Manage persisted run state, transitions, retries, and audit events."""

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None = None,
        settings: Settings | None = None,
        artifact_repository: ArtifactRepository | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_runtime_directories()
        self.session_factory = session_factory or get_session_factory()
        self.artifact_repository = artifact_repository or ArtifactRepository(
            session_factory=self.session_factory,
            settings=self.settings,
        )

    def create_run(
        self,
        *,
        project_id: str,
        input_prompt: str,
        mode: ExecutionMode = ExecutionMode.STANDARD,
        initial_phase: RunPhase = RunPhase.CLARIFY,
        summary: str | None = None,
    ) -> RunStateSnapshot:
        with session_scope(self.session_factory) as session:
            project = session.get(Project, project_id)
            if project is None:
                raise ValueError(f"Project {project_id!r} does not exist.")

            run = Run(
                project_id=project_id,
                status=RunStatus.IN_PROGRESS,
                current_phase=initial_phase,
                mode=mode,
                input_prompt=input_prompt,
                summary=summary,
            )
            session.add(run)
            session.flush()

            self.artifact_repository.ensure_run_layout(run.id)
            self._record_event(
                session=session,
                run=run,
                phase=initial_phase,
                event_type=ExecutionEventType.PHASE_STARTED,
                message=f"Run created and entered {initial_phase.value}.",
            )
            return self._to_snapshot(run)

    def load_run(self, run_id: str) -> RunStateSnapshot:
        with session_scope(self.session_factory) as session:
            run = self._get_run(session, run_id)
            return self._to_snapshot(run)

    def transition_to_phase(
        self,
        run_id: str,
        target_phase: RunPhase,
        *,
        message: str | None = None,
        summary: str | None = None,
    ) -> RunStateSnapshot:
        with session_scope(self.session_factory) as session:
            run = self._get_run(session, run_id)
            self._validate_forward_transition(run.current_phase, target_phase)
            previous_phase = run.current_phase
            run.current_phase = target_phase
            run.status = RunStatus.IN_PROGRESS
            if summary is not None:
                run.summary = summary
            self._record_event(
                session=session,
                run=run,
                phase=previous_phase,
                event_type=ExecutionEventType.PHASE_COMPLETED,
                message=message or f"Completed {previous_phase.value}.",
                payload={"to_phase": target_phase.value},
            )
            self._record_event(
                session=session,
                run=run,
                phase=target_phase,
                event_type=ExecutionEventType.PHASE_STARTED,
                message=f"Entered {target_phase.value}.",
                payload={"from_phase": previous_phase.value},
            )
            return self._to_snapshot(run)

    def rollback_to_phase(
        self,
        run_id: str,
        target_phase: RunPhase,
        *,
        reason: str,
    ) -> RunStateSnapshot:
        with session_scope(self.session_factory) as session:
            run = self._get_run(session, run_id)
            current_phase = run.current_phase
            self._validate_rollback_transition(current_phase, target_phase)
            run.current_phase = target_phase
            run.status = RunStatus.IN_PROGRESS
            self._record_event(
                session=session,
                run=run,
                phase=current_phase,
                event_type=ExecutionEventType.PHASE_ROLLED_BACK,
                message=reason,
                payload={"to_phase": target_phase.value},
            )
            self._record_event(
                session=session,
                run=run,
                phase=target_phase,
                event_type=ExecutionEventType.PHASE_STARTED,
                message=f"Re-entered {target_phase.value} after rollback.",
                payload={"from_phase": current_phase.value},
            )
            return self._to_snapshot(run)

    def request_human_gate(
        self,
        run_id: str,
        *,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> RunStateSnapshot:
        with session_scope(self.session_factory) as session:
            run = self._get_run(session, run_id)
            gate_sequence = session.scalar(
                select(func.count())
                .select_from(ExecutionEvent)
                .where(
                    ExecutionEvent.run_id == run_id,
                    ExecutionEvent.event_type == ExecutionEventType.HUMAN_GATE_REQUESTED,
                )
            )
            run.human_gate_pending = True
            run.status = RunStatus.WAITING_FOR_HUMAN
            self._record_event(
                session=session,
                run=run,
                phase=run.current_phase,
                event_type=ExecutionEventType.HUMAN_GATE_REQUESTED,
                message=message,
                payload={"gate_sequence": int(gate_sequence or 0) + 1, **(payload or {})},
            )
            return self._to_snapshot(run)

    def resolve_human_gate(
        self,
        run_id: str,
        *,
        approved: bool,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> RunStateSnapshot:
        with session_scope(self.session_factory) as session:
            run = self._get_run(session, run_id)
            run.human_gate_pending = False
            run.status = RunStatus.IN_PROGRESS if approved else RunStatus.FAILED
            event_type = (
                ExecutionEventType.HUMAN_GATE_APPROVED
                if approved
                else ExecutionEventType.HUMAN_GATE_REJECTED
            )
            self._record_event(
                session=session,
                run=run,
                phase=run.current_phase,
                event_type=event_type,
                message=message,
                payload=payload,
            )
            return self._to_snapshot(run)

    def mark_phase_failed(
        self,
        run_id: str,
        *,
        message: str,
        error_details: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunStateSnapshot:
        with session_scope(self.session_factory) as session:
            run = self._get_run(session, run_id)
            run.status = RunStatus.FAILED
            self._record_event(
                session=session,
                run=run,
                phase=run.current_phase,
                event_type=ExecutionEventType.PHASE_FAILED,
                message=message,
                payload=payload,
                error_details=error_details,
            )
            return self._to_snapshot(run)

    def schedule_retry(
        self,
        run_id: str,
        *,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> RunStateSnapshot:
        with session_scope(self.session_factory) as session:
            run = self._get_run(session, run_id)
            run.retry_count += 1
            run.status = RunStatus.IN_PROGRESS
            self._record_event(
                session=session,
                run=run,
                phase=run.current_phase,
                event_type=ExecutionEventType.RETRY_SCHEDULED,
                message=message,
                payload={"retry_count": run.retry_count, **(payload or {})},
            )
            return self._to_snapshot(run)

    def complete_run(self, run_id: str, *, summary: str | None = None) -> RunStateSnapshot:
        with session_scope(self.session_factory) as session:
            run = self._get_run(session, run_id)
            if run.current_phase != RunPhase.DELIVER:
                self._validate_forward_transition(run.current_phase, RunPhase.DELIVER)
                previous_phase = run.current_phase
                run.current_phase = RunPhase.DELIVER
                self._record_event(
                    session=session,
                    run=run,
                    phase=previous_phase,
                    event_type=ExecutionEventType.PHASE_COMPLETED,
                    message=f"Completed {previous_phase.value}.",
                    payload={"to_phase": RunPhase.DELIVER.value},
                )
                self._record_event(
                    session=session,
                    run=run,
                    phase=RunPhase.DELIVER,
                    event_type=ExecutionEventType.PHASE_STARTED,
                    message="Entered deliver.",
                    payload={"from_phase": previous_phase.value},
                )
            run.status = RunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
            if summary is not None:
                run.summary = summary
            self._record_event(
                session=session,
                run=run,
                phase=RunPhase.DELIVER,
                event_type=ExecutionEventType.PHASE_COMPLETED,
                message="Run completed.",
            )
            return self._to_snapshot(run)

    def record_event(
        self,
        run_id: str,
        *,
        event_type: ExecutionEventType,
        message: str,
        payload: dict[str, Any] | None = None,
        phase: RunPhase | None = None,
        error_details: str | None = None,
    ) -> None:
        with session_scope(self.session_factory) as session:
            run = self._get_run(session, run_id)
            self._record_event(
                session=session,
                run=run,
                phase=phase or run.current_phase,
                event_type=event_type,
                message=message,
                payload=payload,
                error_details=error_details,
            )

    def _validate_forward_transition(self, current: RunPhase, target: RunPhase) -> None:
        if target == current:
            return
        if PHASE_INDEX[target] != PHASE_INDEX[current] + 1:
            raise InvalidPhaseTransitionError(
                f"Invalid forward transition from {current.value} to {target.value}.",
            )

    def _validate_rollback_transition(self, current: RunPhase, target: RunPhase) -> None:
        if PHASE_INDEX[target] >= PHASE_INDEX[current]:
            raise InvalidPhaseTransitionError(
                f"Rollback target {target.value} must be earlier than {current.value}.",
            )

    def _get_run(self, session: Session, run_id: str) -> Run:
        run = session.get(Run, run_id)
        if run is None:
            raise RunNotFoundError(f"Run {run_id!r} was not found.")
        return run

    def _record_event(
        self,
        *,
        session: Session,
        run: Run,
        phase: RunPhase,
        event_type: ExecutionEventType,
        message: str,
        payload: dict[str, Any] | None = None,
        error_details: str | None = None,
    ) -> None:
        session.add(
            ExecutionEvent(
                run_id=run.id,
                phase=phase,
                event_type=event_type,
                message=message,
                payload=payload or {},
                error_details=error_details,
            )
        )

    def _to_snapshot(self, run: Run) -> RunStateSnapshot:
        return RunStateSnapshot(
            run_id=run.id,
            project_id=run.project_id,
            status=run.status,
            current_phase=run.current_phase,
            mode=run.mode,
            input_prompt=run.input_prompt,
            summary=run.summary,
            retry_count=run.retry_count,
            human_gate_pending=run.human_gate_pending,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
