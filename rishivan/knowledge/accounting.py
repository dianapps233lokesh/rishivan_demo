"""The reconciliation that makes "skip nothing" checkable.

Extraction routes every sutra unit to one of two destinations: `rule` when the
statement has a condition testable against chart facts, `knowledge_item` when it
states something else (a definition, a formula, a remedy, a classification).

The failure mode worth engineering against is neither of those — it is a unit that
reaches *neither* table because a classifier returned nothing, an LLM call failed,
or a stage crashed midway. That loss is invisible: the rule count still looks
healthy, the precision metric still looks fine, and a chapter has quietly vanished
from the corpus.

So the invariant is explicit and asserted, not assumed:

    every live sutra_unit has >= 1 rule row OR >= 1 knowledge_item row

`unaccounted_units()` returns the violations. A test asserts it is empty after a
run, and `coverage_report()` is what you read to see where the corpus went.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rishivan.models.knowledge.item import NON_RULE_BEARING, KnowledgeItem
from rishivan.models.knowledge.rule import Rule
from rishivan.models.knowledge.unit import SutraUnit


@dataclass(frozen=True)
class UnaccountedUnit:
    unit_id: int
    chapter: str | None
    verse_ref_local: str | None

    def __str__(self) -> str:
        return f"unit {self.unit_id} (ch{self.chapter}:v{self.verse_ref_local})"


@dataclass(frozen=True)
class CoverageReport:
    """Where a book's units ended up. `units` must equal
    `rule_bearing + item_only + unaccounted`, so the arithmetic itself is a check."""

    book_id: int
    units: int
    rule_bearing: int
    item_only: int
    unaccounted: int
    knowledge_carrying_items: int
    vocabulary_gaps: int

    @property
    def ok(self) -> bool:
        return self.unaccounted == 0

    @property
    def accounted(self) -> int:
        return self.rule_bearing + self.item_only


def _unit_ids_with_rules(book_id: int):
    return select(Rule.unit_id).where(
        Rule.book_id == book_id, Rule.deleted_at.is_(None)
    )


def _unit_ids_with_items(book_id: int):
    return select(KnowledgeItem.unit_id).where(
        KnowledgeItem.book_id == book_id, KnowledgeItem.deleted_at.is_(None)
    )


async def unaccounted_units(
    session: AsyncSession, *, book_id: int, limit: int | None = None
) -> list[UnaccountedUnit]:
    """Units that produced neither a rule nor a knowledge item — i.e. content
    that was silently lost. Should always be empty after a completed run."""
    stmt = (
        select(SutraUnit.id, SutraUnit.chapter, SutraUnit.verse_ref_local)
        .where(
            SutraUnit.book_id == book_id,
            SutraUnit.deleted_at.is_(None),
            SutraUnit.id.not_in(_unit_ids_with_rules(book_id)),
            SutraUnit.id.not_in(_unit_ids_with_items(book_id)),
        )
        .order_by(SutraUnit.id)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).all()
    return [UnaccountedUnit(*row) for row in rows]


async def coverage_report(session: AsyncSession, *, book_id: int) -> CoverageReport:
    """The one report that answers "did we lose any of this book?"."""

    async def count(stmt) -> int:
        return await session.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0

    units = await count(
        select(SutraUnit.id).where(
            SutraUnit.book_id == book_id, SutraUnit.deleted_at.is_(None)
        )
    )
    with_rules = await count(_unit_ids_with_rules(book_id).distinct())
    with_items_only = await count(
        _unit_ids_with_items(book_id)
        .distinct()
        .where(KnowledgeItem.unit_id.not_in(_unit_ids_with_rules(book_id)))
    )
    knowledge_carrying = await count(
        select(KnowledgeItem.id).where(
            KnowledgeItem.book_id == book_id,
            KnowledgeItem.deleted_at.is_(None),
            KnowledgeItem.kind.not_in([k.value for k in NON_RULE_BEARING]),
        )
    )
    gaps = await count(
        select(KnowledgeItem.id).where(
            KnowledgeItem.book_id == book_id,
            KnowledgeItem.deleted_at.is_(None),
            KnowledgeItem.vocabulary_gap != [],
        )
    )
    return CoverageReport(
        book_id=book_id,
        units=units,
        rule_bearing=with_rules,
        item_only=with_items_only,
        unaccounted=units - with_rules - with_items_only,
        knowledge_carrying_items=knowledge_carrying,
        vocabulary_gaps=gaps,
    )
