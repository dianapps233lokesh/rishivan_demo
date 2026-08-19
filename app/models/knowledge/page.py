"""Pages and the elements extracted from them."""

from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import text as sql_text  # aliased: PageElementRow has a `text` column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PageStatus(StrEnum):
    pending = "pending"
    rasterized = "rasterized"
    ocr_done = "ocr_done"
    extracted = "extracted"
    validated = "validated"
    needs_review = "needs_review"
    failed = "failed"


class Page(Base):
    """A single page of a source book.

    Table is `corpus_page`, not `page`: the superseded POC in
    `app/models/document.py` already owns `page`, and the architecture is
    explicit that the POC is superseded rather than extended. Renaming the POC's
    table is out of scope for this plan and would touch live data, so the new
    pipeline takes the namespaced name. `page_element` is likewise `corpus_page_element`
    so the pair reads consistently.
    """

    __tablename__ = "corpus_page"

    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"), nullable=False)
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PageStatus] = mapped_column(
        String(20),
        nullable=False,
        default=PageStatus.pending,
        server_default=PageStatus.pending.value,
    )

    image_uri: Mapped[str | None] = mapped_column(Text)
    image_sha256: Mapped[str | None] = mapped_column(String(64))
    """Over the canonical pixmap, not the PDF bytes — it is what the cache key
    is built from, so it must change exactly when the rendered image changes."""

    dpi: Mapped[int | None] = mapped_column(Integer)
    skew_deg: Mapped[float | None] = mapped_column(Float)
    deskew_applied: Mapped[bool | None] = mapped_column(Boolean)

    ocr_text: Mapped[str | None] = mapped_column(Text)
    ocr_text_sha256: Mapped[str | None] = mapped_column(String(64))
    ocr_mean_confidence: Mapped[float | None] = mapped_column(Float)

    agreement_score: Mapped[float | None] = mapped_column(Float)
    """Normalized Levenshtein between the OCR prior and the VLM reading. The
    calibrated review trigger — VLM self-confidence is not one."""

    media_resolution: Mapped[str | None] = mapped_column(String(20))
    failure_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_page_book_no",
            "book_id",
            "page_no",
            unique=True,
            postgresql_where=sql_text("deleted_at IS NULL"),
        ),
        Index("ix_page_status", "book_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Page book={self.book_id} p{self.page_no} {self.status}>"


class PageElementRow(Base):
    """One extracted element: a verse, a translation, a table, a chart figure."""

    __tablename__ = "corpus_page_element"

    page_id: Mapped[int] = mapped_column(ForeignKey("corpus_page.id"), nullable=False)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    element_type: Mapped[str] = mapped_column(String(30), nullable=False)
    script: Mapped[str] = mapped_column(String(10), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    bbox: Mapped[dict | None] = mapped_column(JSONB)
    """Normalized 0..1 page geometry, when the extractor captured it.

    NULL for rows bridged from the POC ingestion layer: `source_element.bbox`
    holds JSONB null on all 10,052 BPHS rows, so there is no geometry to carry.
    Nullable rather than a synthesized box — a fake bbox would place a
    reviewer's page overlay confidently on the wrong region, which is worse than
    admitting the position is unknown. See `source_element_id`."""

    verse_no: Mapped[str | None] = mapped_column(String(30))
    chapter_hint: Mapped[str | None] = mapped_column(String(60))
    continues_to_next_page: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("false")
    )
    """Set by the extractor when an element runs off the foot of the page. The
    reflow state machine merges on it, which is how a verse keeps its
    translation across a page boundary."""

    source_element_id: Mapped[int | None] = mapped_column(BigInteger)
    """The `source_element.id` this row was bridged from, or NULL for rows this
    pipeline extracted itself.

    Carries two jobs: it keeps provenance back to the immutable POC raw layer,
    and it is the idempotency key for the bridge — a source element already
    bridged is skipped rather than duplicated, which is what makes a re-run
    free and byte-stable."""

    payload: Mapped[dict | None] = mapped_column(JSONB)
    """A table grid or a chart figure's house->planet map."""

    model_confidence: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        Index(
            "uq_element_page_order",
            "page_id",
            "reading_order",
            unique=True,
            postgresql_where=sql_text("deleted_at IS NULL"),
        ),
        Index("ix_element_page", "page_id"),
    )
