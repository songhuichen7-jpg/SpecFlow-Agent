from __future__ import annotations

from typing import Any

from sqlalchemy import select

from specflow.agents import ReviewerFinding, ReviewFixLoopResult, ReviewRunResult
from specflow.models import (
    ExecutionEvent,
    ExecutionMode,
    ReviewSeverity,
    RunPhase,
    RunStatus,
)
from specflow.orchestrator import (
    PendingHumanGate,
    ProjectConfig,
    QueueHumanGate,
    SupervisorOrchestrator,
)


def test_supervisor_debug_mode_runs_to_completion(sprint2_env: dict[str, Any]) -> None:
    orchestrator = _build_supervisor(sprint2_env, gate=PendingHumanGate())
    session_factory = sprint2_env["session_factory"]

    result = orchestrator.start_run(
        input_prompt="帮我做一个内部工单管理系统，支持员工提交工单、管理员处理、附件和仪表盘。",
        mode=ExecutionMode.DEBUG,
        project_config=ProjectConfig(
            slug="supervisor-debug",
            name="Supervisor Debug Project",
        ),
        supplemental_inputs=[
            (
                "需要部门维度、状态从 open -> in_progress -> resolved -> closed，"
                "角色包括员工、处理人、管理员，并且要保留评论时间线。"
            )
        ],
    )

    assert result.status == RunStatus.COMPLETED
    assert result.current_phase == RunPhase.DELIVER
    assert result.review_approved is True
    assert "review-report.md" in result.artifact_names
    assert "quality-report.json" in result.artifact_names
    assert result.pending_gate is None

    with session_factory() as session:
        events = list(
            session.scalars(select(ExecutionEvent).where(ExecutionEvent.run_id == result.run_id))
        )

    log_types = {
        str(event.payload.get("log_type"))
        for event in events
        if event.payload.get("log_type") is not None
    }
    assert "agent_started" in log_types
    assert "agent_completed" in log_types
    assert "quality_summary" in log_types
    assert "review_summary" in log_types
    assert "run_summary" in log_types


def test_supervisor_standard_mode_pauses_and_resumes_through_gates(
    sprint2_env: dict[str, Any],
) -> None:
    orchestrator = _build_supervisor(sprint2_env, gate=PendingHumanGate())

    started = orchestrator.start_run(
        input_prompt="帮我做一个内部工单管理系统。",
        mode=ExecutionMode.STANDARD,
        project_config=ProjectConfig(
            slug="supervisor-standard",
            name="Supervisor Standard Project",
        ),
        supplemental_inputs=[
            (
                "需要部门维度、状态从 open -> in_progress -> resolved -> closed，"
                "角色包括员工、处理人、管理员。"
            )
        ],
    )
    assert started.status == RunStatus.WAITING_FOR_HUMAN
    assert started.pending_gate is not None
    assert started.pending_gate.gate_name == "freeze_spec"

    after_freeze = orchestrator.resume_run(started.run_id, decision=True)
    assert after_freeze.status == RunStatus.WAITING_FOR_HUMAN
    assert after_freeze.current_phase == RunPhase.REVIEW
    assert after_freeze.pending_gate is not None
    assert after_freeze.pending_gate.gate_name == "deliver"

    completed = orchestrator.resume_run(started.run_id, decision=True)
    assert completed.status == RunStatus.COMPLETED
    assert completed.current_phase == RunPhase.DELIVER
    assert completed.pending_gate is None


def test_supervisor_debug_mode_auto_approves_review_arbitration(
    sprint2_env: dict[str, Any],
) -> None:
    orchestrator = _build_supervisor(
        sprint2_env,
        gate=PendingHumanGate(),
        review_loop=EscalatingReviewLoop(sprint2_env["run_state_manager"]),
    )

    result = orchestrator.start_run(
        input_prompt="帮我做一个内部工单管理系统。",
        mode=ExecutionMode.DEBUG,
        project_config=ProjectConfig(
            slug="supervisor-debug-review-arbitration",
            name="Supervisor Debug Review Arbitration Project",
        ),
        supplemental_inputs=["需要部门维度和标准工单流转。"],
    )

    assert result.status == RunStatus.COMPLETED
    assert result.current_phase == RunPhase.DELIVER
    assert result.review_approved is False
    assert result.pending_gate is None


def test_supervisor_standard_mode_can_resume_after_review_arbitration(
    sprint2_env: dict[str, Any],
) -> None:
    orchestrator = _build_supervisor(
        sprint2_env,
        gate=PendingHumanGate(),
        review_loop=EscalatingReviewLoop(sprint2_env["run_state_manager"]),
    )

    started = orchestrator.start_run(
        input_prompt="帮我做一个内部工单管理系统。",
        mode=ExecutionMode.STANDARD,
        project_config=ProjectConfig(
            slug="supervisor-standard-review-arbitration",
            name="Supervisor Standard Review Arbitration Project",
        ),
        supplemental_inputs=["需要部门维度和标准工单流转。"],
    )
    assert started.pending_gate is not None
    assert started.pending_gate.gate_name == "freeze_spec"

    after_freeze = orchestrator.resume_run(started.run_id, decision=True)
    assert after_freeze.status == RunStatus.WAITING_FOR_HUMAN
    assert after_freeze.pending_gate is not None
    assert after_freeze.pending_gate.gate_name == "review_arbitration"

    after_arbitration = orchestrator.resume_run(started.run_id, decision=True)
    assert after_arbitration.status == RunStatus.WAITING_FOR_HUMAN
    assert after_arbitration.pending_gate is not None
    assert after_arbitration.pending_gate.gate_name == "deliver"

    completed = orchestrator.resume_run(started.run_id, decision=True)
    assert completed.status == RunStatus.COMPLETED
    assert completed.current_phase == RunPhase.DELIVER
    assert completed.review_approved is False
    assert completed.pending_gate is None


def test_supervisor_rejected_gate_marks_run_failed(sprint2_env: dict[str, Any]) -> None:
    orchestrator = _build_supervisor(sprint2_env, gate=PendingHumanGate())

    started = orchestrator.start_run(
        input_prompt="帮我做一个内部工单管理系统。",
        mode=ExecutionMode.STANDARD,
        project_config=ProjectConfig(
            slug="supervisor-reject",
            name="Supervisor Reject Project",
        ),
        supplemental_inputs=["需要部门维度和标准工单流转。"],
    )

    rejected = orchestrator.resume_run(started.run_id, decision=False)

    assert rejected.status == RunStatus.FAILED
    assert rejected.pending_gate is None


def test_supervisor_harness_uses_deep_agents_factory(
    monkeypatch: Any,
    sprint2_env: dict[str, Any],
) -> None:
    captured: dict[str, Any] = {}

    def fake_create_deep_agent(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"ok": True}

    monkeypatch.setattr("specflow.orchestrator.harness.create_deep_agent", fake_create_deep_agent)
    orchestrator = _build_supervisor(sprint2_env, gate=QueueHumanGate([True, True]))

    from specflow.orchestrator import build_supervisor_harness

    harness = build_supervisor_harness(orchestrator, model="dummy-model", debug=True)

    assert harness == {"ok": True}
    assert captured["kwargs"]["model"] == "dummy-model"
    assert captured["kwargs"]["name"] == "specflow-supervisor"
    assert len(captured["kwargs"]["tools"]) == 3


def _build_supervisor(
    sprint2_env: dict[str, Any],
    *,
    gate: Any,
    review_loop: Any | None = None,
) -> SupervisorOrchestrator:
    return SupervisorOrchestrator(
        settings=sprint2_env["settings"],
        session_factory=sprint2_env["session_factory"],
        artifact_repository=sprint2_env["artifact_repository"],
        run_state_manager=sprint2_env["run_state_manager"],
        checkpoint_manager=sprint2_env["checkpoint_manager"],
        human_gate=gate,
        review_loop=review_loop,
    )


class EscalatingReviewLoop:
    def __init__(self, run_state_manager: Any) -> None:
        self.run_state_manager = run_state_manager

    def run(self, run_id: str, *, max_iterations: int = 1) -> ReviewFixLoopResult:
        snapshot = self.run_state_manager.load_run(run_id)
        if snapshot.current_phase == RunPhase.IMPLEMENT:
            self.run_state_manager.transition_to_phase(
                run_id,
                RunPhase.REVIEW,
                message="Reviewer started spec compliance review.",
                summary="Reviewer is validating workspace output against the frozen spec.",
            )
        issue = ReviewerFinding(
            title="Quality gate failed: backend_tests",
            description="Generated backend tests are still failing after retries.",
            severity=ReviewSeverity.HIGH,
            suggested_fix="Inspect the generated backend workspace before final delivery.",
        )
        self.run_state_manager.request_human_gate(
            run_id,
            message="Review-fix loop exhausted its retry budget. Remaining issues: backend_tests",
            payload={
                "gate_name": "review_arbitration",
                "issues": [issue.model_dump(mode="python")],
                "max_iterations": max_iterations,
            },
        )
        review = ReviewRunResult(
            run_id=run_id,
            current_phase=RunPhase.REVIEW,
            approved=False,
            blocking=True,
            report_version=1,
            issues=[issue],
            quality_checks={"backend_tests": False},
        )
        return ReviewFixLoopResult(
            run_id=run_id,
            approved=False,
            blocking=True,
            iterations=max_iterations,
            requires_human_arbitration=True,
            reviews=[review],
            fixes=[],
        )
