from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from specflow.models.enums import ReviewIssueStatus, ReviewSeverity
from specflow.storage.db.base import Base, IdentifierMixin, TimestampMixin

if TYPE_CHECKING:
    from specflow.models.artifact import Artifact
    from specflow.models.run import Run


class ReviewIssue(IdentifierMixin, TimestampMixin, Base):
    """A reviewer-detected gap or defect against the frozen spec."""

    __tablename__ = "review_issue"

    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("run.id"), nullable=False)
    artifact_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("artifact.id"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    severity: Mapped[ReviewSeverity] = mapped_column(
        Enum(ReviewSeverity, name="review_severity", native_enum=False),
        nullable=False,
        index=True,
    )
    status: Mapped[ReviewIssueStatus] = mapped_column(
        Enum(ReviewIssueStatus, name="review_issue_status", native_enum=False),
        nullable=False,
        default=ReviewIssueStatus.OPEN,
        index=True,
    )
    spec_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    code_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    suggested_fix: Mapped[str | None] = mapped_column(Text(), nullable=True)

    run: Mapped[Run] = relationship(back_populates="review_issues")
    artifact: Mapped[Artifact | None] = relationship(back_populates="review_issues")
