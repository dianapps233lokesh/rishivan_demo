"""Declarative base shared by all ORM models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(self) -> None:
        self.deleted_at = datetime.now(UTC)

    def restore(self) -> None:
        self.deleted_at = None


class Base(SoftDeleteMixin, DeclarativeBase):
    """Base for all models: surrogate id + external_id + is_active + timestamps."""

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, sort_order=-100)

    external_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        server_default=text("gen_random_uuid()"),
        nullable=False,
        sort_order=-99,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        nullable=False,
        sort_order=90,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        sort_order=100,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        sort_order=101,
    )
