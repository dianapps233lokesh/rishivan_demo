"""Approved Postgres rules into Koonji YAML, so the engine can fire them.

    uv run python -m scripts.convert_db_rules --report
    uv run python -m scripts.convert_db_rules --book bphs-gcsharma-vol1
    uv run python -m scripts.convert_db_rules

No model calls and no spend: this is the same deterministic converter that
produced `rules/converted/`, pointed at the database instead of at the JSONL
files on disk.

**It found nothing, and that is the useful result.** The two sources looked out
of sync -- the YAML covers 244 BPHS verse locations against Postgres's 394 --
and the obvious reading was that a hundred-odd reviewed verses had never
reached the engine. They had. Run against all 1,046 approved rules this
produces two documents not already on disk, and the compiler drops both.

The verses that appear only in Postgres are missing from the YAML because the
converter REFUSES them, not because nobody converted them:

    35  effect 1: life_domain '(none)' has no claim
    13  effect 1: life_domain 'family' has no claim
    11  formation: '3' is not a graha or a house lord

Those refusals applied when `rules/converted/` was first built and they apply
now. Comparing verse locations between the two stores measures the wrong thing;
comparing rule ids after conversion measures the right one. Kept as an audit:
`--report` answers "has the database drifted ahead of the YAML" in about a
minute, and the answer today is no.

The recoverable share is in `convert.CLAIM_MAP`, not here. Teaching it `family`
would convert 13 more rules for free, and `(none)` is 35 rules whose extraction
never recorded a domain at all -- a data problem upstream of this script.

Only approved rules are converted. `approved_at IS NOT NULL` is the reviewer's
signature, and a script that quietly promoted unreviewed rows into the serving
path would make that signature worthless.

**Ids that already exist are skipped, not renumbered.** `convert.rule_id_for`
derives an id from the citation, so a verse present in both sources produces the
same id twice -- and the compiler refuses a duplicate id outright, taking the
whole bundle down with it. `rules/converted/` stays authoritative for the
overlap and this only adds what is genuinely missing.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from pathlib import Path

import yaml
from sqlalchemy import select

from rishivan.db.session import async_session_factory
from rishivan.koonji.convert import convert_corpus
from rishivan.koonji.corpus import BOOKS, Unit
from rishivan.koonji.emit import write_grouped
from rishivan.koonji.pipeline import gate
from rishivan.koonji.registry import seed_registry
from rishivan.models.knowledge.book import Book
from rishivan.models.knowledge.rule import MATCHABLE_PREDICATE, Rule

RULES_DIR = Path(__file__).resolve().parents[1] / "rishivan/koonji/rules"
OUT_DIR = RULES_DIR / "from_db"

IDS_BY_SLUG: dict[str, tuple[str, str]] = {
    edition: (book_id, edition) for book_id, edition in BOOKS.values()
}
"""Postgres book slug -> the (book_id, edition_id) a citation is built from.

Taken from `koonji.corpus.BOOKS` rather than restated, so a book cannot be
cited one way by the extractor and another way by this script.
"""

HEADER = (
    "GENERATED - do not edit by hand.\n"
    "  python -m scripts.convert_db_rules\n"
    "\n"
    "Converted from APPROVED rules in Postgres by the same deterministic\n"
    "converter that produced ../converted/. These verses had reviewed rules in\n"
    "the database that no YAML file covered, so the engine could not fire them.\n"
    "Status is `candidate` here regardless: approval in Postgres is approval of\n"
    "the old-format rule, and the frame it has been mapped into is new.\n"
)


def existing_rule_ids() -> set[str]:
    """Every rule id already on disk, from every source directory."""
    found: set[str] = set()
    for path in RULES_DIR.rglob("*.yaml"):
        if OUT_DIR in path.parents:
            continue
        for rule in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            if isinstance(rule, dict) and rule.get("id"):
                found.add(rule["id"])
    return found


def unit_for(rule: Rule, slug: str) -> Unit | None:
    """A Postgres rule rebuilt as the corpus Unit the converter reads.

    The database stores the old extractor's shape verbatim -- `condition` is the
    `formation` block, `effect["effects"]` the effects list -- so this is a
    re-labelling rather than a translation. Anything the converter cannot map it
    will refuse on its own; that judgement is not duplicated here.
    """
    source = rule.source or {}
    chapter, verse = source.get("chapter"), source.get("verse_ref")
    if not chapter or not verse:
        return None
    book_id, edition_id = IDS_BY_SLUG.get(slug, (slug, slug))
    effect = rule.effect or {}
    return Unit(
        unit_id=str(rule.unit_id),
        book_id=book_id,
        edition_id=edition_id,
        chapter=str(chapter),
        verse_ref=str(verse),
        translation=source.get("translation", "") or "",
        extracted={
            "expressible": True,
            "rule_key": rule.rule_key.split(":", 1)[-1],
            "formation": rule.condition or {},
            "effects": effect.get("effects") or [],
            "rule_category": effect.get("rule_category") or "formation",
            "timing": effect.get("timing") or {},
            "modifiers": effect.get("modifiers") or [],
            "exceptions": effect.get("exceptions") or [],
        },
    )


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="approved Postgres rules -> Koonji YAML")
    parser.add_argument("--book", action="append", help="book slug; repeatable")
    parser.add_argument("--report", action="store_true", help="counts only, write nothing")
    args = parser.parse_args(argv)

    already = existing_rule_ids()
    print(f"{len(already)} rule ids already on disk")

    async with async_session_factory() as session:
        query = (
            select(Book.slug, Rule)
            .join(Book, Book.id == Rule.book_id)
            .where(Rule.approved_at.isnot(None))
        )
        if args.book:
            query = query.where(Book.slug.in_(args.book))
        rows = (await session.execute(query)).all()

    print(f"{len(rows)} approved rules in Postgres")
    if not rows:
        return 0

    by_slug: dict[str, list[Unit]] = {}
    unusable = Counter()
    for slug, rule in rows:
        unit = unit_for(rule, slug)
        if unit is None:
            unusable[slug] += 1
            continue
        by_slug.setdefault(slug, []).append(unit)

    registry = seed_registry()
    total_new = 0
    for slug, units in sorted(by_slug.items()):
        conversion = convert_corpus(units)
        fresh = [doc for doc in conversion.docs if doc["id"] not in already]
        overlap = len(conversion.docs) - len(fresh)
        rules, report, _ = gate(fresh, registry)
        # Within this batch too: two Postgres rows for one verse and one claim
        # converge on the same id, and the compiler refuses the bundle for it.
        seen: set[str] = set()
        unique = [r for r in rules if not (r.rule_id in seen or seen.add(r.rule_id))]
        already.update(r.rule_id for r in unique)
        total_new += len(unique)

        print(f"\n  {slug}")
        print(f"    {len(units)} rules -> {len(conversion.docs)} documents "
              f"({overlap} already on disk, {len(fresh)} new)")
        print(f"    {report.kept} compiled, {len(report.dropped)} dropped, "
              f"{len(rules) - len(unique)} duplicate ids within the batch")
        if unusable[slug]:
            print(f"    {unusable[slug]} had no chapter/verse and cannot be cited")

        if unique and not args.report:
            written = write_grouped(unique, OUT_DIR / slug, header=HEADER)
            for path in written:
                print(f"    wrote {path.relative_to(RULES_DIR.parent.parent)}")

    print(f"\n{total_new} new rules"
          + (" (report only, nothing written)" if args.report else " written"))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
