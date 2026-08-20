"""Persist triage verdicts, and the destination-B rows that follow from them.

Idempotent by content hash: a unit whose translation is unchanged keeps its existing
verdict and costs nothing to re-run. That is a client release gate ("same version +
same input = same reasoning state"), so it is enforced here rather than assumed.
"""

import hashlib
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.triage.classify import Destination, Verdict, classify
from app.knowledge.triage.signals import detect
from app.models.knowledge.chapter import Chapter
from app.models.knowledge.item import ItemStatus, KnowledgeItem
from app.models.knowledge.triage import UnitTriage
from app.models.knowledge.unit import SutraUnit


CLASSIFIER_VERSION = "4"
"""Bump whenever the classifier's *decisions* can change.

This is part of the content hash, and it has to be: hashing only the verse text made
a logic change invisible. When chapter-title gating and the timing-as-antecedent rule
were added, every verdict in the database was stale and every re-run reported
`verdicts(+0/=1008)` -- correctly skipping work whose inputs were unchanged, while
silently serving decisions the current code would never make.

Idempotency must be keyed on everything that determines the output, not just the
input document. History:
    1 -- initial deterministic classifier
    2 -- chapter-title gating; dasha-as-antecedent (Signal.timing_condition)
    3 -- chapter included in the hash (see `content_hash`)
    4 -- inexpressible-subject chapter gate; vocabulary_gap recorded
"""


def content_hash(text: str, *, chapter: str | None = None) -> str:
    """Hash every input the verdict depends on: version, chapter, and text.

    The chapter has to be in here. Chapter-title gating means a unit's verdict depends
    on which chapter it belongs to, and the chapter repair moved 768 units -- yet every
    re-run reported `verdicts(+0/~0/=998)` and served the old verdicts, because the
    translation text was untouched. An idempotency key must cover everything that
    determines the output, not just the most obvious input. This is the second time that
    lesson cost a silent stale run.
    """
    payload = f"v{CLASSIFIER_VERSION}\x00{chapter or ''}\x00{text or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class TriageReport:
    book_id: int
    units: int = 0
    rule: int = 0
    item: int = 0
    ambiguous: int = 0
    verdicts_written: int = 0
    verdicts_updated: int = 0
    verdicts_skipped: int = 0
    items_written: int = 0
    items_skipped: int = 0
    items_retired: int = 0

    @property
    def deterministic_share(self) -> float:
        """Fraction settled without spending anything."""
        return (self.rule + self.item) / self.units if self.units else 0.0

    def line(self) -> str:
        return (
            f"book {self.book_id}: units={self.units} rule={self.rule} "
            f"item={self.item} ambiguous={self.ambiguous} "
            f"free={self.deterministic_share:.1%} "
            f"verdicts(+{self.verdicts_written}/~{self.verdicts_updated}"
            f"/={self.verdicts_skipped}) "
            f"items(+{self.items_written}/={self.items_skipped}"
            f"/-{self.items_retired})"
        )


async def _chapter_gates(session: AsyncSession, book_id: int) -> dict:
    rows = (
        await session.execute(
            select(
                Chapter.number,
                Chapter.is_rule_bearing,
                Chapter.gating_reason,
                Chapter.title,
            ).where(Chapter.book_id == book_id, Chapter.deleted_at.is_(None))
        )
    ).all()
    return {number: (rb, reason, title) for number, rb, reason, title in rows}


def _chapter_number(unit: SutraUnit) -> int | None:
    try:
        return int(str(unit.chapter))
    except (TypeError, ValueError):
        return None


def verdict_for(unit: SutraUnit, gates: dict) -> Verdict:
    """The pure part: unit + chapter gates -> verdict. No I/O, so it is testable."""
    is_rule_bearing, reason, title = gates.get(
        _chapter_number(unit), (True, None, None)
    )
    return classify(
        unit.translation,
        commentary=unit.commentary,
        chapter_is_rule_bearing=is_rule_bearing,
        chapter_gating_reason=reason,
        chapter_title=title,
    )


async def triage_book(session: AsyncSession, *, book_id: int) -> TriageReport:
    """Classify every unit of a book and reconcile the stored state to match.

    Reconciliation, not append. A verdict is one row per unit (enforced by
    `uq_triage_unit`), so a changed decision **updates** that row -- an insert would
    violate the constraint, which is how the missing update path was found. And when a
    unit is reclassified away from destination B, its now-wrong `knowledge_item` is
    soft-deleted; leaving it behind would let a verse be simultaneously a rule and a
    non-rule, and would inflate the coverage report into looking complete.
    """
    report = TriageReport(book_id=book_id)
    gates = await _chapter_gates(session, book_id)

    units = list(
        (
            await session.execute(
                select(SutraUnit).where(
                    SutraUnit.book_id == book_id, SutraUnit.deleted_at.is_(None)
                )
            )
        ).scalars()
    )
    verdict_rows = {
        row.unit_id: row
        for row in (
            await session.execute(
                select(UnitTriage).where(
                    UnitTriage.book_id == book_id, UnitTriage.deleted_at.is_(None)
                )
            )
        ).scalars()
    }
    item_rows: dict[int, list[KnowledgeItem]] = {}
    for row in (
        await session.execute(
            select(KnowledgeItem).where(
                KnowledgeItem.book_id == book_id, KnowledgeItem.deleted_at.is_(None)
            )
        )
    ).scalars():
        item_rows.setdefault(row.unit_id, []).append(row)

    # Retire items whose unit no longer exists. The chapter repair soft-deleted 63
    # duplicate units; their items stayed live and inflated the coverage report above
    # the verdict count, which is exactly the kind of drift the report exists to catch.
    live_unit_ids = {unit.id for unit in units}
    for unit_id, rows_for_unit in item_rows.items():
        if unit_id in live_unit_ids:
            continue
        for row in rows_for_unit:
            row.delete()
            report.items_retired += 1

    for unit in units:
        report.units += 1
        verdict = verdict_for(unit, gates)
        digest = content_hash(unit.translation, chapter=unit.chapter)

        if verdict.destination is Destination.rule:
            report.rule += 1
        elif verdict.destination is Destination.item:
            report.item += 1
        else:
            report.ambiguous += 1

        signals = sorted(sig.value for sig in detect(unit.translation))
        existing = verdict_rows.get(unit.id)
        if existing is not None and existing.content_hash == digest:
            report.verdicts_skipped += 1
        elif existing is not None:
            existing.destination = verdict.destination.value
            existing.kind = verdict.kind.value if verdict.kind else None
            existing.confidence = verdict.confidence
            existing.method = verdict.method
            existing.reasons = list(verdict.reasons)
            existing.signals = signals
            existing.content_hash = digest
            report.verdicts_updated += 1
        else:
            session.add(
                UnitTriage(
                    book_id=book_id,
                    unit_id=unit.id,
                    destination=verdict.destination.value,
                    kind=verdict.kind.value if verdict.kind else None,
                    confidence=verdict.confidence,
                    method=verdict.method,
                    reasons=list(verdict.reasons),
                    signals=signals,
                    content_hash=digest,
                )
            )
            report.verdicts_written += 1

        stale = item_rows.get(unit.id, [])
        if verdict.destination is not Destination.item:
            # Reclassified away from destination B: the item is now wrong.
            for row in stale:
                row.delete()
                report.items_retired += 1
            continue

        matching = [row for row in stale if row.content_hash == digest]
        if matching:
            report.items_skipped += 1
            for row in stale:
                if row not in matching:
                    row.delete()
                    report.items_retired += 1
            continue
        for row in stale:
            row.delete()
            report.items_retired += 1

        session.add(
            KnowledgeItem(
                book_id=book_id,
                unit_id=unit.id,
                chapter=unit.chapter,
                verse_ref_local=unit.verse_ref_local,
                kind=verdict.kind.value,
                status=(
                    ItemStatus.needs_review.value
                    if verdict.confidence < 0.5
                    else ItemStatus.captured.value
                ),
                status_reason="; ".join(verdict.reasons) or None,
                statement=unit.translation,
                content_hash=digest,
                importance_reasons=list(verdict.reasons),
                vocabulary_gap=[verdict.vocabulary_gap]
                if verdict.vocabulary_gap
                else [],
            )
        )
        report.items_written += 1

    await session.flush()
    return report
