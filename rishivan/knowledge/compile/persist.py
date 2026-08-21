"""Load extracted rules into `rule` + `rule_atom`, idempotently.

The decision logic is a pure function (`load_decision`) over one extraction row, so the
rules about what may enter the rule base are testable without a database. Three of them
matter more than the rest:

**Nothing is auto-approved.** `MATCHABLE_PREDICATE` requires `approved_at IS NOT NULL`,
and this loader never sets it. Every rule enters visible to a reviewer and invisible to
a user. That is the whole reason it is safe to load 376 machine-checked but
human-unverified rules at once.

**Declines are not rules.** 581 of vol 1's 999 extractions declined, correctly, because
the vocabulary cannot express the verse. Those belong in `knowledge_item` with their
`out_of_scope_reason`; loading them here would fill the matcher with conditionless rows.

**Invalid extractions are kept, not dropped.** They load as `status='unparsed'` with
their faults recorded, which keeps them out of the matchable index while leaving a
reviewer something to fix. What is refused instead is a rule whose atoms will not
compile: a rule with an empty prefilter is invisible to the matcher while looking
perfectly present in the table, and that specific kind of silence is what this whole
pipeline is built to avoid.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hashlib import sha256

from rishivan.council.source_matrix import school_for
from rishivan.knowledge.compile.atoms import CompiledAtom, compile_condition
from rishivan.models.knowledge.book import Book
from rishivan.models.knowledge.rule import Rule, RuleAtom


DESTINATION_RULE = "rule"
DESTINATION_ITEM = "item"


@dataclass
class Decision:
    load: bool
    status: str = "parsed"
    approved_at: datetime | None = None
    reason: str = ""
    atoms: list[CompiledAtom] = field(default_factory=list)
    destination: str = DESTINATION_RULE
    """Where this row belongs. `item` means destination B -- a `knowledge_item` with its
    reason, not a discard. `models/knowledge/item.py` states the invariant: every
    `sutra_unit` must produce at least one `rule` row or one `knowledge_item` row."""
    vocabulary_gap: list[str] = field(default_factory=list)
    """What the engine would need to express this. Matches the column's list type.

    This is the ranked backlog -- 195 benefic/malefic and 150 avastha declines in BPHS
    vol 1 -- and it existed only in terminal output until the loader wrote it."""


@dataclass
class LoadReport:
    rules: int = 0
    items: int = 0
    """Declines written to destination B. Every decline must produce one, or the unit is
    unaccounted -- `models/knowledge/item.py` asserts that cannot happen quietly."""
    updated: int = 0
    atoms: int = 0
    refused: int = 0
    declined: int = 0
    unparsed: int = 0
    failures: list[str] = field(default_factory=list)

    def line(self) -> str:
        return (
            f"inserted={self.rules} updated={self.updated} atoms={self.atoms} "
            f"unparsed={self.unparsed} declined={self.declined} items={self.items} "
            f"refused={self.refused}"
        )


def effect_for(payload: dict) -> dict:
    """The `rule.effect` JSONB for one extracted rule.

    Pure, so the payload shape is testable without a database -- and it needed to be:
    `rule_category` was silently dropped here, which is Blueprint §4's level 5. Without
    it a "when will I marry" question retrieves the same rules as "will I marry",
    though §8 rule 2 calls them different reasoning problems.
    """
    return {
        "effects": payload.get("effects") or [],
        "timing": payload.get("timing") or {},
        "modifiers": payload.get("modifiers") or [],
        "exceptions": payload.get("exceptions") or [],
        "remedies": payload.get("remedies") or [],
        "rishi_affinity": payload.get("rishi_affinity") or {},
        "rule_family": payload.get("rule_family"),
        # A natal promise is the common case and the extractor omits the field for it.
        "rule_category": payload.get("rule_category") or "formation",
    }


def rule_key_for(row: dict, *, book_slug: str) -> str:
    """A stable, book-namespaced identity for one extracted rule.

    `uq_rule_key_version` is unique across the whole table and two books both have a
    chapter 12 verse 2, so the slug is part of the key. The extractor's own `rule_key`
    distinguishes siblings from one verse -- BPHS 26.1 produced six, one per outcome.
    """
    inner = str(row["rule"].get("rule_key") or f"{row['chapter']}.{row['verse_ref']}")
    return f"{book_slug}:{inner}"


def load_decision(row: dict) -> Decision:
    """Whether this extraction row may enter the rule base, and how."""
    rule = row.get("rule") or {}
    if rule.get("expressible") is False or str(row.get("verdict", "")).startswith(
        "DECLINED"
    ):
        gap = rule.get("out_of_scope_reason") or ""
        return Decision(
            load=False,
            destination=DESTINATION_ITEM,
            reason=f"declined by the extractor: {gap or 'no reason given'}",
            vocabulary_gap=[gap] if gap else [],
        )

    formation = rule.get("formation") or {}
    timing = (rule.get("timing") or {}).get("activation_factors") or {}
    try:
        atoms = compile_condition(formation)
    except ValueError as exc:
        # Loaded, not discarded. These rows are already INVALID -- validation caught
        # them -- and the only thing separating them from their `unparsed` siblings is
        # whether their malformed atoms happened to compile. Of BPHS vol 2's 66 invalid
        # rules, 36 loaded and 30 vanished on exactly that distinction. `unparsed` is
        # invisible to the matcher, so keeping them costs nothing and gives a reviewer
        # the fault.
        return Decision(
            load=True,
            status="unparsed",
            reason=f"atoms will not compile: {exc}",
        )

    if not atoms:
        # A legitimate timing rule carries its condition in `timing`, not `formation`,
        # and BPHS 46.15-21 is one. It has no prefilterable natal atom, so it loads with
        # no atoms -- the matcher reaches it by dasha, not by placement. A rule with
        # neither is kept as `unparsed` for the same reason as above.
        if timing.get("atoms"):
            return Decision(load=True, status="parsed" if row.get("valid") else "unparsed")
        return Decision(
            load=True,
            status="unparsed",
            reason="no atoms in formation or timing, so nothing to prefilter on",
        )

    return Decision(
        load=True,
        status="parsed" if row.get("valid") else "unparsed",
        approved_at=None,
        atoms=atoms,
    )


async def _upsert_declined_item(session, *, row: dict, book, decision: Decision) -> bool:
    """Record a decline in destination B. Returns True when a row was inserted.

    The extractor's refusal is knowledge: it names a concept the vocabulary cannot
    express, and 195 benefic/malefic plus 150 avastha declines in BPHS vol 1 are a ranked
    list of what the engine needs next. Until this existed the reason was printed to a
    terminal and discarded, so `unaccounted_units()` counted the verse as lost.

    Idempotent on `content_hash`, so re-loading the same artefact inserts nothing.
    """
    from rishivan.models.knowledge.item import ItemKind, ItemStatus, KnowledgeItem

    rule = row.get("rule") or {}
    statement = (
        (rule.get("effects") or [{}])[0].get("statement")
        or row.get("translation")
        or ""
    )
    digest = sha256(
        f"{book.id}|{row.get('unit_id')}|{rule.get('rule_key')}".encode()
    ).hexdigest()

    existing = await session.scalar(
        select(KnowledgeItem).where(
            KnowledgeItem.content_hash == digest,
            KnowledgeItem.deleted_at.is_(None),
        )
    )
    if existing is not None:
        return False

    session.add(
        KnowledgeItem(
            book_id=book.id,
            unit_id=row["unit_id"],
            chapter=row.get("chapter"),
            verse_ref_local=row.get("verse_ref"),
            # The verse IS a rule; what is missing is a way to express it. Every other
            # kind would misdescribe it, and `unclassified` is documented as "a review
            # lane rather than a wastebasket", which is exactly the intent here.
            kind=ItemKind.unclassified,
            status=ItemStatus.out_of_scope,
            status_reason=decision.reason,
            statement=statement,
            vocabulary_gap=decision.vocabulary_gap,
            source_authority_tier=book.source_authority_tier,
            content_hash=digest,
        )
    )
    return True


async def load_rules(
    session: AsyncSession, *, rows: list[dict], book_slug: str
) -> LoadReport:
    """Write rules and their atoms. Re-running replaces a rule's atoms rather than
    appending, so a second load is a no-op rather than a duplication."""
    report = LoadReport()
    book = (
        await session.execute(select(Book).where(Book.slug == book_slug))
    ).scalar_one()

    for row in rows:
        decision = load_decision(row)
        key = rule_key_for(row, book_slug=book_slug)
        if not decision.load:
            report.refused += 1
            if decision.destination == DESTINATION_ITEM:
                report.declined += 1
                if await _upsert_declined_item(
                    session, row=row, book=book, decision=decision
                ):
                    report.items += 1
            else:
                report.failures.append(f"{key}: {decision.reason}")
            continue

        rule = (
            await session.execute(select(Rule).where(Rule.rule_key == key))
        ).scalar_one_or_none()
        payload = row["rule"]
        if rule is None:
            rule = Rule(
                rule_key=key, version=1, book_id=book.id, unit_id=row["unit_id"]
            )
            session.add(rule)
            report.rules += 1
        else:
            report.updated += 1
            # Replace the prefilter wholesale: a stale atom is a rule matching charts
            # its current condition no longer describes.
            for existing in (
                await session.execute(
                    select(RuleAtom).where(RuleAtom.rule_id == rule.id)
                )
            ).scalars():
                await session.delete(existing)

        rule.condition = payload.get("formation")
        rule.raw_condition_text = payload.get("raw_condition_text")
        rule.effect = effect_for(payload)
        # Blueprint §4 level 2. The column defaults to `parashari`, so leaving it unset
        # stored every Prashna Marga and Deva Keralam rule as Parashari -- exactly the
        # silent doctrine-mixing §8 rule 5 forbids, and invisible once written.
        rule.school = school_for(book_slug)
        rule.life_domains = payload.get("life_domains") or []
        rule.source = {
            "book_slug": book_slug,
            "chapter": row["chapter"],
            "verse_ref": row["verse_ref"],
            "unit_id": row["unit_id"],
            "translation": row.get("translation", ""),
            "problems": row.get("problems") or [],
        }
        rule.status = decision.status
        rule.atom_count = len(decision.atoms)
        rule.approved_at = None
        if decision.status == "unparsed":
            report.unparsed += 1

        await session.flush()
        for atom in decision.atoms:
            session.add(
                RuleAtom(
                    rule_id=rule.id,
                    condition_type=atom.condition_type,
                    subject=atom.subject,
                    object_int=atom.object_int,
                    object_str=atom.object_str,
                    from_reference=atom.from_reference,
                    varga=atom.varga,
                    negate=atom.negate,
                    fact_token=atom.fact_token,
                )
            )
            report.atoms += 1
    return report
