from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from specflow.agents.coder import CoderRunResult
from specflow.agents.reviewer import ReviewRunResult
from specflow.models import ExecutionEvent, ExecutionEventType
from specflow.storage import RunStateManager
from specflow.storage.db import get_session_factory, session_scope


class ExecutionLogger:
    """Write orchestration summaries into the existing execution_event table."""

    def __init__(
        self,
        *,
        run_state_manager: RunStateManager,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.run_state_manager = run_state_manager
        self.session_factory = (
            session_factory or run_state_manager.session_factory or get_session_factory()
        )

    def log_agent_started(
        self,
        run_id: str,
        *,
        agent: str,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._record(
            run_id,
            message=f"Agent started: {agent}.",
            payload={
                "log_type": "agent_started",
                "agent": agent,
                "summary": summary,
                **(payload or {}),
            },
        )

    def log_agent_completed(
        self,
        run_id: str,
        *,
        agent: str,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._record(
            run_id,
            message=f"Agent completed: {agent}.",
            payload={
                "log_type": "agent_completed",
                "agent": agent,
                "summary": summary,
                **(payload or {}),
            },
        )

    def log_quality_summary(self, run_id: str, *, result: CoderRunResult) -> None:
        self._record(
            run_id,
            message="Recorded coder quality summary.",
            payload={
                "log_type": "quality_summary",
                "checks": {name: gate.success for name, gate in result.quality_gates.items()},
                "written_files": len(result.written_files),
            },
        )

    def log_review_summary(self, run_id: str, *, result: ReviewRunResult) -> None:
        self._record(
            run_id,
            message="Recorded reviewer summary.",
            payload={
                "log_type": "review_summary",
                "approved": result.approved,
                "blocking": result.blocking,
                "issues": [issue.model_dump(mode="python") for issue in result.issues],
                "quality_checks": result.quality_checks,
            },
        )

    def log_run_summary(
        self,
        run_id: str,
        *,
        summary: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self._record(
            run_id,
            message="Recorded supervisor run summary.",
            payload={"log_type": "run_summary", "summary": summary, **(payload or {})},
        )

    def load_events(self, run_id: str) -> list[ExecutionEvent]:
        with session_scope(self.session_factory) as session:
            statement = (
                select(ExecutionEvent)
                .where(ExecutionEvent.run_id == run_id)
                .order_by(ExecutionEvent.created_at.asc())
            )
            return list(session.scalars(statement))

    def _record(
        self,
        run_id: str,
        *,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        self.run_state_manager.record_event(
            run_id,
            event_type=ExecutionEventType.TOOL_CALLED,
            message=message,
            payload=payload,
        )
