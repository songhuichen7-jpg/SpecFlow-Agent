from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from specflow.models import ExecutionEvent, ExecutionEventType, RunPhase, RunStatus
from specflow.storage import InvalidPhaseTransitionError, RunStateManager


def test_run_state_manager_handles_transitions_and_events(sprint2_env: dict[str, Any]) -> None:
    manager = sprint2_env["run_state_manager"]
    repository = sprint2_env["artifact_repository"]
    session_factory = sprint2_env["session_factory"]
    project_id = sprint2_env["project_id"]

    assert isinstance(manager, RunStateManager)
    run = manager.create_run(
        project_id=project_id,
        input_prompt="Implement the ticket system flow.",
    )
    layout = repository.get_run_layout(run.run_id)

    assert run.status == RunStatus.IN_PROGRESS
    assert layout.artifacts_dir.exists()
    assert layout.workspace_dir.exists()
    assert layout.reports_dir.exists()

    with pytest.raises(InvalidPhaseTransitionError):
        manager.transition_to_phase(run.run_id, RunPhase.PLAN)

    run = manager.transition_to_phase(run.run_id, RunPhase.SPECIFY)
    run = manager.transition_to_phase(run.run_id, RunPhase.PLAN)
    run = manager.request_human_gate(run.run_id, message="Please freeze the spec.")

    assert run.status == RunStatus.WAITING_FOR_HUMAN
    assert run.human_gate_pending is True

    run = manager.resolve_human_gate(run.run_id, approved=True, message="Spec approved.")
    run = manager.schedule_retry(run.run_id, message="Retry plan synthesis.")
    run = manager.rollback_to_phase(run.run_id, RunPhase.SPECIFY, reason="Need more clarification.")
    run = manager.mark_phase_failed(
        run.run_id, message="Planner crashed.", error_details="stack trace"
    )

    assert run.current_phase == RunPhase.SPECIFY
    assert run.retry_count == 1
    assert run.status == RunStatus.FAILED

    with session_factory() as session:
        events = list(
            session.scalars(select(ExecutionEvent).where(ExecutionEvent.run_id == run.run_id))
        )

    event_types = [event.event_type for event in events]
    assert ExecutionEventType.PHASE_STARTED in event_types
    assert ExecutionEventType.HUMAN_GATE_REQUESTED in event_types
    assert ExecutionEventType.HUMAN_GATE_APPROVED in event_types
    assert ExecutionEventType.RETRY_SCHEDULED in event_types
    assert ExecutionEventType.PHASE_ROLLED_BACK in event_types
    assert ExecutionEventType.PHASE_FAILED in event_types


def test_run_state_manager_completes_from_review(sprint2_env: dict[str, Any]) -> None:
    manager = sprint2_env["run_state_manager"]
    project_id = sprint2_env["project_id"]

    run = manager.create_run(
        project_id=project_id,
        input_prompt="Deliver the final project.",
    )
    for phase in (
        RunPhase.SPECIFY,
        RunPhase.PLAN,
        RunPhase.TASKS,
        RunPhase.IMPLEMENT,
        RunPhase.REVIEW,
    ):
        run = manager.transition_to_phase(run.run_id, phase)

    run = manager.complete_run(run.run_id, summary="Finished successfully.")

    assert run.current_phase == RunPhase.DELIVER
    assert run.status == RunStatus.COMPLETED
    assert run.completed_at is not None
    assert run.summary == "Finished successfully."
