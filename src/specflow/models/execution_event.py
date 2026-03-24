from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from specflow.models.enums import ExecutionEventType, RunPhase
from specflow.storage.db.base import Base, IdentifierMixin, TimestampMixin

if TYPE_CHECKING:
    from specflow.models.run import Run


class ExecutionEvent(IdentifierMixin, TimestampMixin, Base):
    """Important lifecycle and audit events emitted during execution."""

    __tablename__ = "execution_event"

    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("run.id"), nullable=False)
    phase: Mapped[RunPhase] = mapped_column(
        Enum(RunPhase, name="run_phase", native_enum=False),
        nullable=False,
        index=True,
    )
    event_type: Mapped[ExecutionEventType] = mapped_column(
        Enum(ExecutionEventType, name="execution_event_type", native_enum=False),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False, default=dict)
    error_details: Mapped[str | None] = mapped_column(Text(), nullable=True)

    run: Mapped[Run] = relationship(back_populates="execution_events")
