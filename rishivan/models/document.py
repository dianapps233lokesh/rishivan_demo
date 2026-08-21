"""ORM models for the extraction docstore: Document, Page, SourceElement."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from rishivan.db.base import Base


class Document(Base):
    """One row per book. id/created_at/updated_at come from Base."""

    __tablename__ = "document"

    external_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid.uuid4, nullable=False
    )
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    source_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    language: Mapped[str] = mapped_column(String(20), default="mixed")
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)


class Page(Base):
    """One row per page — the unit of resume."""

    __tablename__ = "page"
    __table_args__ = (UniqueConstraint("document_id", "page_number"),)

    external_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid.uuid4, nullable=False
    )
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_image_s3_key: Mapped[str | None] = mapped_column(String(600))
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    flash_model: Mapped[str | None] = mapped_column(String(100))
    pro_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SourceElement(Base):
    """One row per extracted element. external_id is the vector-DB join key."""

    __tablename__ = "source_element"
    __table_args__ = (UniqueConstraint("document_id", "page_number", "element_index"),)

    external_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, default=uuid.uuid4, nullable=False
    )
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    element_index: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(20), default="unknown")
    bbox: Mapped[list | None] = mapped_column(JSONB)
    asset_s3_key: Mapped[str | None] = mapped_column(String(600))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    model: Mapped[str] = mapped_column(String(20), nullable=False)
    meta: Mapped[dict | None] = mapped_column(JSONB)
