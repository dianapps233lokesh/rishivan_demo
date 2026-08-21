"""Destination B — everything a book states that is *not* a matchable rule.

A Koonji rule needs a condition testable against chart facts. Much of the corpus states
something else and states it importantly: BPHS 20.5 defines how to compute Shubha
Rashmi, 54.63 prescribes a remedy. Forcing those into `rule` would put rows in the
matcher that can never match, corrupting the precision metric the go/no-go gate uses.

The design rule is **account for everything, skip nothing**:

* Every `sutra_unit` produces at least one `rule` or one `knowledge_item` row.
  `unaccounted_units()` is the reconciliation and a test asserts it is empty, so "we
  dropped it" can only happen as a visible failure.
* A statement we cannot make machine-usable is still captured, with
  `status='out_of_scope'` and a reason. Degrade, never drop.
* `vocabulary_gap` records the tokens a statement needed and the engine cannot emit —
  a ranked backlog instead of a silent loss.
"""

from enum import StrEnum

from sqlalchemy import Float, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rishivan.db.base import Base


class ItemKind(StrEnum):
    """What kind of statement this is. Exhaustive by construction: anything the
    classifier cannot place becomes `unclassified`, which is a review lane rather
    than a wastebasket."""

    definition = "definition"
    formula = "formula"
    reference_table = "reference_table"
    classification = "classification"
    enumeration = "enumeration"
    remedy = "remedy"
    prescription = "prescription"
    narrative = "narrative"
    invocation = "invocation"
    out_of_domain = "out_of_domain"
    unclassified = "unclassified"


class ItemStatus(StrEnum):
    captured = "captured"
    """Text and provenance recorded; no machine-usable payload yet."""

    structured = "structured"
    """`payload` holds a machine-usable form — a compiled formula, parsed table
    rows, or an enumeration expanded into items."""

    out_of_scope = "out_of_scope"
    """Deliberately not machine-usable. `status_reason` says why, and
    `vocabulary_gap` says what would be needed. Never a silent drop."""

    needs_review = "needs_review"


NON_RULE_BEARING = frozenset(
    {ItemKind.narrative, ItemKind.invocation, ItemKind.out_of_domain}
)
"""Kinds that genuinely carry no knowledge. Everything else is content a later
milestone may need, so `importance` is what orders it — not this set."""


class KnowledgeItem(Base):
    __tablename__ = "knowledge_item"

    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("sutra_unit.id"), nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("extraction_run.id"))

    chapter: Mapped[str | None] = mapped_column(String(60))
    verse_ref_local: Mapped[str | None] = mapped_column(String(30))
    """Denormalised so a citation renders without joining `sutra_unit`."""

    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text)

    title: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default=""
    )
    """Short label — "Shubha Rashmi", "visible-half results"."""

    statement: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )

    defines_terms: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    uses_terms: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    fact_tokens: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    vocabulary_gap: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    """Fact tokens this statement needs that the engine cannot emit today. The
    pilot's ranked vocabulary backlog is `group by` over this column."""

    payload: Mapped[dict | None] = mapped_column(JSONB)
    """Structured form when `status='structured'`: formula AST, table rows,
    expanded enumeration."""

    applies_to_rule_id: Mapped[int | None] = mapped_column(ForeignKey("rule.id"))
    """Set when the statement modifies a rule rather than standing alone — a
    remedy for the effect that rule predicts, for instance."""

    importance: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default=text("0.0")
    )
    importance_reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    """Why the score is what it is, so a reviewer can audit it. Importance is
    computed deterministically and is never an LLM's unexplained opinion."""

    source_authority_tier: Mapped[str] = mapped_column(
        String(2), nullable=False, default="S0", server_default="S0"
    )

    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    """Idempotency key. Re-running a completed book inserts nothing."""

    __table_args__ = (
        Index(
            "uq_item_unit_hash",
            "unit_id",
            "content_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_item_book", "book_id"),
        Index("ix_item_unit", "unit_id"),
        # The backlog queue: what is worth a human's attention, most first.
        Index(
            "ix_item_triage_queue",
            "kind",
            text("importance DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # The vocabulary-gap report, which is the pilot's ranked backlog.
        Index(
            "ix_item_vocabulary_gap",
            "book_id",
            postgresql_where=text(
                "vocabulary_gap <> '[]'::jsonb AND deleted_at IS NULL"
            ),
        ),
    )
