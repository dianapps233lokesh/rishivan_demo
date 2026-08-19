"""The chapter tree, read from the book's own printed table of contents.

Two page numberings coexist and must never be conflated. `printed_page_*` is
what the book prints and what its table of contents cites; `pdf_page_*` is the
scan's page index, which is what `source_element.page_number` holds. For BPHS
vol 1 the offset between them is 8, derived from running heads rather than
assumed — and left NULL when it cannot be derived, because a guessed offset
would point a citation at the wrong page.
"""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Chapter(Base):
    __tablename__ = "chapter"

    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)

    printed_page_from: Mapped[int | None] = mapped_column(Integer)
    printed_page_to: Mapped[int | None] = mapped_column(Integer)
    pdf_page_from: Mapped[int | None] = mapped_column(Integer)
    pdf_page_to: Mapped[int | None] = mapped_column(Integer)

    is_rule_bearing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    gating_reason: Mapped[str | None] = mapped_column(Text)
    """Why a chapter carries no extractable rules — 'cosmology', 'calculation
    method'. Recorded so that skipping a chapter is reviewable rather than
    invisible: a chapter wrongly kept costs a few extraction calls, while a
    chapter wrongly skipped loses its rules with no trace that it happened."""

    __table_args__ = (
        Index(
            "uq_chapter_book_number",
            "book_id",
            "number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_chapter_book", "book_id"),
    )

    def __repr__(self) -> str:
        return f"<Chapter {self.book_id}:{self.number} {self.title!r}>"
