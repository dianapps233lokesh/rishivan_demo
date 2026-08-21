"""The rule base, its denormalized atoms, and the reviewer queue.

The gate that matters most in this file is `ix_rule_matchable`: only
`status='parsed' AND approved_at IS NOT NULL` may reach a user, and that is
expressed as a partial index plus a SQL predicate rather than an application-side
`if`. A missed rule degrades to passage retrieval; a *wrong* rule produces a
confidently wrong prediction.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rishivan.db.base import Base

MATCHABLE_PREDICATE = (
    "status = 'parsed' AND approved_at IS NOT NULL AND deleted_at IS NULL"
)
"""The one definition of "may reach a user". Shared by the model, the migration
and the CRUD query so the three cannot drift apart."""


class Rule(Base):
    __tablename__ = "rule"

    rule_key: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    run_id: Mapped[int | None] = mapped_column(ForeignKey("extraction_run.id"))
    book_id: Mapped[int] = mapped_column(ForeignKey("book.id"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("sutra_unit.id"), nullable=False)

    condition: Mapped[dict | None] = mapped_column(JSONB)
    raw_condition_text: Mapped[str | None] = mapped_column(Text)
    effect: Mapped[dict] = mapped_column(JSONB, nullable=False)
    life_domains: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    school: Mapped[str] = mapped_column(
        String(40), nullable=False, default="parashari", server_default="parashari"
    )
    tradition_tag: Mapped[str] = mapped_column(
        String(40), nullable=False, default="classical", server_default="classical"
    )
    source: Mapped[dict] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default=text("0.5")
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    atom_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))

    __table_args__ = (
        Index(
            "uq_rule_key_version",
            "rule_key",
            "version",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # THE gate for K5: the only index the matcher's hot query uses.
        Index(
            "ix_rule_matchable",
            "school",
            "status",
            postgresql_where=text(MATCHABLE_PREDICATE),
        ),
    )


class RuleAtom(Base):
    """Denormalized atoms — the SQL prefilter the matcher uses instead of
    loading every rule and evaluating it in Python."""

    __tablename__ = "rule_atom"

    rule_id: Mapped[int] = mapped_column(ForeignKey("rule.id"), nullable=False)
    condition_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(24), nullable=False)
    """Planet code, or `"house:7"` for house-subject atoms."""

    object_int: Mapped[int | None] = mapped_column(Integer)
    object_str: Mapped[str | None] = mapped_column(String(32))
    from_reference: Mapped[str] = mapped_column(
        String(16), nullable=False, default="lagna", server_default="lagna"
    )
    varga: Mapped[str] = mapped_column(
        String(4), nullable=False, default="D1", server_default="D1"
    )
    negate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    fact_token: Mapped[str] = mapped_column(String(120), nullable=False)
    """The astro fact token this atom resolves to. Contract-tested against the
    engine's real vocabulary, so a rule can never bind to a token nothing emits."""

    __table_args__ = (
        Index(
            "ix_atom_lookup",
            "condition_type",
            "subject",
            "object_int",
            "from_reference",
            "varga",
        ),
        Index("ix_atom_fact_token", "fact_token"),
        Index("ix_atom_rule", "rule_id"),
    )


class ReviewTask(Base):
    __tablename__ = "review_task"

    lane: Mapped[str] = mapped_column(String(10), nullable=False)  # page | unit | rule
    page_id: Mapped[int | None] = mapped_column(ForeignKey("corpus_page.id"))
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("sutra_unit.id"))
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rule.id"))
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default=text("100")
    )
    reason: Mapped[str | None] = mapped_column(Text)

    is_blind_sample: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    """True for the 2% of auto-accepted items injected blind. Without them the
    measured precision is only over items we already doubted."""

    resolution: Mapped[str | None] = mapped_column(
        String(16)
    )  # accept | fix | reject | escalate
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"))

    __table_args__ = (Index("ix_review_queue", "lane", "resolution", "priority"),)
