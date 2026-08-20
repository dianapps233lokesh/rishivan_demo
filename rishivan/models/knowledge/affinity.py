"""Weighted book x Rishi prior, seeded from the client's source-family matrix.

This is a *prior only*. The client's matrix rates whole source families against
each Rishi (BPHS is High for all eight, which is what makes it the pilot book),
but the client is equally explicit that the production matrix must be generated
rule by rule. So each rule refines its own affinity from its extracted concepts,
and a book-level weight must never be the final answer to "does this Rishi need
this rule?".
"""

from sqlalchemy import Float, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from rishivan.db.base import Base

RISHI_KEYS: tuple[str, ...] = (
    "atma",
    "prema",
    "artha",
    "karma",
    "vansh",
    "aarogya",
    "yatra",
    "dharma",
)
"""The client's eight life-domain Rishis, in a fixed order.

Order is part of the contract: a vector built by iterating this tuple is
positionally comparable across rows and across releases. Never reorder it —
append only, and only alongside a migration.
"""

WEIGHT_HIGH = 1.0
WEIGHT_MEDIUM = 0.6
WEIGHT_LOW = 0.3
"""The client's matrix is expressed as High/Medium/Low, so the numeric weights
live here rather than being written out at each call site."""


class BookRishiAffinity(Base):
    __tablename__ = "book_rishi_affinity"

    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"), nullable=False)
    rishi: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index(
            "uq_affinity_book_rishi",
            "book_id",
            "rishi",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_affinity_book", "book_id"),
    )

    def __repr__(self) -> str:
        return f"<BookRishiAffinity {self.book_id}:{self.rishi}={self.weight}>"
