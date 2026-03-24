from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from specflow.models.enums import TemplateType
from specflow.storage.db.base import Base, IdentifierMixin, TimestampMixin

if TYPE_CHECKING:
    from specflow.models.run import Run


class Project(IdentifierMixin, TimestampMixin, Base):
    """Logical project definition shared across runs."""

    __tablename__ = "project"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    template_type: Mapped[TemplateType] = mapped_column(
        Enum(TemplateType, name="template_type", native_enum=False),
        nullable=False,
        index=True,
    )
    target_stack: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)

    runs: Mapped[list[Run]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
