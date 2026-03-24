from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from specflow.models.enums import ArtifactFormat, ArtifactKind
from specflow.storage.db.base import Base, IdentifierMixin, TimestampMixin

if TYPE_CHECKING:
    from specflow.models.review_issue import ReviewIssue
    from specflow.models.run import Run


class Artifact(IdentifierMixin, TimestampMixin, Base):
    """Persisted artifact generated during a run."""

    __tablename__ = "artifact"

    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("run.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[ArtifactKind] = mapped_column(
        Enum(ArtifactKind, name="artifact_kind", native_enum=False),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    artifact_format: Mapped[ArtifactFormat] = mapped_column(
        Enum(ArtifactFormat, name="artifact_format", native_enum=False),
        nullable=False,
    )
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    is_frozen: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False, default=dict)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    run: Mapped[Run] = relationship(back_populates="artifacts")
    review_issues: Mapped[list[ReviewIssue]] = relationship(back_populates="artifact")
