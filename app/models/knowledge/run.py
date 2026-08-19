"""Extraction runs and the content-addressed cache that makes a re-run free."""

from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RunStage(StrEnum):
    triage = "triage"
    rasterize = "rasterize"
    ocr = "ocr"
    extract = "extract"
    validate = "validate"
    reflow = "reflow"
    rules = "rules"
    index = "index"
    done = "done"


class ExtractionRun(Base):
    """The single source of truth for what a pipeline run did and what it cost."""

    __tablename__ = "extraction_run"

    book_id: Mapped[int | None] = mapped_column(ForeignKey("book.id"))
    stage: Mapped[RunStage] = mapped_column(
        String(20),
        nullable=False,
        default=RunStage.triage,
        server_default=RunStage.triage.value,
    )

    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    page_schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_dsl_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ocr_model_id: Mapped[str | None] = mapped_column(String(120))
    vlm_model_id: Mapped[str | None] = mapped_column(String(120))

    budget_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    spent_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    """Numeric, not float: this is money, and a run refuses its next shard on it."""

    pricing_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    """Frozen price table, so a Google price change cannot rewrite history."""

    counters: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_run_book_stage", "book_id", "stage"),)


class ExtractionCache(Base):
    """Content-addressed page extraction. The reason a re-run costs $0.

    Keyed on every input that can change the answer — the page image, the model,
    the prompt, the schema, the resolution tier and the OCR prior. Anything left
    out of that key is a way to serve a stale extraction; anything spurious put
    into it is a way to re-pay for an unchanged page.
    """

    __tablename__ = "extraction_cache"

    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # ocr | vlm | rules
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index(
            "uq_extraction_cache_key",
            "cache_key",
            "kind",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
