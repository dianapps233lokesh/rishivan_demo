"""The triage verdict — one row per sutra unit, recording where it was routed.

This table exists to make one distinction that the accounting query cannot make
without it: the difference between a unit **awaiting extraction** and a unit that
was **lost**. Both look identical from `rule` and `knowledge_item` alone -- absent
from both -- and one is normal progress while the other is a bug that silently
shrinks the corpus.

With a verdict row per unit:

    triaged as `rule`, no rule row yet  -> awaiting extraction (expected)
    no verdict row at all               -> lost (a defect, and now visible)

It also keeps `sutra_unit` unmutated. The units are the hand-verifiable artefact the
golden set is checked against; writing pipeline state back onto them would make that
artefact a moving target.
"""

from sqlalchemy import Float, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UnitTriage(Base):
    __tablename__ = "unit_triage"

    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("sutra_unit.id"), nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("extraction_run.id"))

    destination: Mapped[str] = mapped_column(String(12), nullable=False)
    """`rule` | `item` | `ambiguous`. `ambiguous` is a lane, not a verdict: it means
    the deterministic pass abstained and an LLM must decide."""

    kind: Mapped[str | None] = mapped_column(String(24))
    """The `ItemKind` when destination is `item`; NULL otherwise."""

    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default=text("0.0")
    )
    method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="deterministic",
        server_default="deterministic",
    )
    """`deterministic` | `chapter_gate` | `llm`. Which pass produced this, so the
    cost of a re-run and the trustworthiness of a verdict are both legible."""

    reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    """Why. A verdict with no reasons cannot be debugged from the row."""

    signals: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    """Hash of the classified text. A unit whose text is unchanged is not
    reclassified, so a re-run is free."""

    __table_args__ = (
        Index(
            "uq_triage_unit",
            "unit_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_triage_book_destination", "book_id", "destination"),
        # The paid lane: what still needs an LLM decision.
        Index(
            "ix_triage_ambiguous",
            "book_id",
            postgresql_where=text(
                "destination = 'ambiguous' AND deleted_at IS NULL"
            ),
        ),
    )
