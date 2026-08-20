"""The persisted Sutra Unit — the smallest thing retrieval is allowed to return."""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rishivan.db.base import Base


class SutraUnit(Base):
    __tablename__ = "sutra_unit"

    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"), nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("extraction_run.id"))

    chapter: Mapped[str | None] = mapped_column(String(60))
    verse_ref_local: Mapped[str | None] = mapped_column(String(30))
    """The reference as printed in *this* edition."""

    canonical_ref: Mapped[str | None] = mapped_column(String(120))
    """The cross-edition reference, once reconciled. Two translations of BPHS
    number the same verse differently, so the local ref cannot be the join key."""

    verse_devanagari: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    verse_iast: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    translation: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    commentary: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )

    topic_tags: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    element_ids: Mapped[list[int]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    """Provenance back to `corpus_page_element`. Every citation is traceable to
    the pixels it came from."""

    page_from: Mapped[int | None] = mapped_column(Integer)
    page_to: Mapped[int | None] = mapped_column(Integer)
    inferred_verse_no: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    __table_args__ = (
        Index(
            "uq_unit_book_chapter_verse",
            "book_id",
            "chapter",
            "verse_ref_local",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_unit_book", "book_id"),
    )
