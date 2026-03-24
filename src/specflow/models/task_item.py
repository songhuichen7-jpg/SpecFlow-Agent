from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from specflow.models.enums import TaskStatus
from specflow.storage.db.base import Base, IdentifierMixin, TimestampMixin

if TYPE_CHECKING:
    from specflow.models.run import Run


class TaskItem(IdentifierMixin, TimestampMixin, Base):
    """Tracked task derived from planning or implementation steps."""

    __tablename__ = "task_item"
    __table_args__ = (UniqueConstraint("run_id", "task_key"),)

    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("run.id"), nullable=False)
    task_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status", native_enum=False),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    sequence: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    details: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    run: Mapped[Run] = relationship(back_populates="task_items")
