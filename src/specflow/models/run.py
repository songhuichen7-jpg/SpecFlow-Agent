from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from specflow.models.enums import ExecutionMode, RunPhase, RunStatus
from specflow.storage.db.base import Base, IdentifierMixin, TimestampMixin

if TYPE_CHECKING:
    from specflow.models.artifact import Artifact
    from specflow.models.execution_event import ExecutionEvent
    from specflow.models.project import Project
    from specflow.models.review_issue import ReviewIssue
    from specflow.models.task_item import TaskItem


class Run(IdentifierMixin, TimestampMixin, Base):
    """A single execution instance of the SpecFlow pipeline."""

    __tablename__ = "run"

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project.id"),
        nullable=False,
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status", native_enum=False),
        nullable=False,
        default=RunStatus.PENDING,
        index=True,
    )
    current_phase: Mapped[RunPhase] = mapped_column(
        Enum(RunPhase, name="run_phase", native_enum=False),
        nullable=False,
        default=RunPhase.CLARIFY,
        index=True,
    )
    mode: Mapped[ExecutionMode] = mapped_column(
        Enum(ExecutionMode, name="execution_mode", native_enum=False),
        nullable=False,
        default=ExecutionMode.STANDARD,
    )
    input_prompt: Mapped[str] = mapped_column(Text(), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text(), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    human_gate_pending: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    project: Mapped[Project] = relationship(back_populates="runs")
    artifacts: Mapped[list[Artifact]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    task_items: Mapped[list[TaskItem]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    review_issues: Mapped[list[ReviewIssue]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    execution_events: Mapped[list[ExecutionEvent]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
