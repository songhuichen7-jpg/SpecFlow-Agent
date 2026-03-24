from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Boolean, Enum, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from specflow.models.enums import TemplateType
from specflow.storage.db.base import Base, IdentifierMixin, TimestampMixin


class TemplateProfile(IdentifierMixin, TimestampMixin, Base):
    """Stored template metadata and defaults."""

    __tablename__ = "template_profile"
    __table_args__ = (UniqueConstraint("slug", "version"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    template_type: Mapped[TemplateType] = mapped_column(
        Enum(TemplateType, name="template_type", native_enum=False),
        nullable=False,
        index=True,
    )
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    default_stack: Mapped[str] = mapped_column(String(255), nullable=False)
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False, default=dict)
    defaults: Mapped[dict[str, Any]] = mapped_column(JSON(), nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
