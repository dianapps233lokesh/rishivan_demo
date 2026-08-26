"""Load Koonji-extracted URF rules into the Postgres rule base.

    uv run python -m scripts.load_extracted --dry-run
    uv run python -m scripts.load_extracted --book phaladeepika
    uv run python -m scripts.load_extracted

The extractor writes URF YAML under `rishivan/koonji/rules/extracted/<book>/`,
which the Koonji engine loads directly. That is enough to answer with, and not
enough to review: approval is a database act (`approved_at`), and
`scripts/embed_rules.py` publishes to Qdrant from the database, not from disk.
So the rules have to land here before a reviewer can see them or the runtime's
rule search can reach them.

Nothing is approved by this script. Every row arrives with `approved_at = NULL`,
which `MATCHABLE_PREDICATE` excludes, so loading a book cannot put an unreviewed
rule in front of a user.

**The URF document is stored whole under `effect["urf"]`.** The columns beside
it are a projection for the existing consumers -- `embed_rules` reads
`effect["effects"]` and `source["translation"]`, the reviewer reads
`life_domains` and `source` -- and a projection loses things: URF carries
modality, corroboration requirements, restriction and timing that the older
column layout has nowhere to put. Keeping the original means the projection can
be improved later without re-running extraction.

**What this does NOT make work.** `knowledge.match.engine.satisfies` reads the
old atom vocabulary (`{"type": "planet_in_sign", ...}`) and a URF condition
(`{"occupies_rashi": {...}}`) is not that. It returns False for an atom type it
does not know -- inert, by design, not an error -- so once approved these rules
will embed into Qdrant and never fire in the legacy matcher. That matcher is
not on the serving path (`match_chart` has no caller outside tests); the Koonji
engine matches these rules from YAML today. Fixing it means either teaching
`satisfies` the URF shape or reverse-mapping the twelve predicates in use, and
both are separate work from getting the rules stored.
"""

from __future__ import annotations

import argparse
import asyncio
import re
from pathlib import Path

import yaml
from sqlalchemy import select

from rishivan.db.session import async_session_factory
from rishivan.models.knowledge.book import Book
from rishivan.models.knowledge.rule import Rule
from rishivan.models.knowledge.unit import SutraUnit

EXTRACTED = Path(__file__).resolve().parents[1] / "rishivan/koonji/rules/extracted"

LOCATOR = re.compile(r"^ch(?P<chapter>.+?)\.v(?P<verse>.+)$")

BOOK_SLUG = {
    "prasna-marga": "prasnamarga-raman-part1",
    "bhavartha-ratnakara": "bhavartha-ratnakara-by-b-v-raman-text",
    "brihat-jataka": "brihatjataka-row-1919",
    "phaladeepika": "phaladeepika-sastri-1950",
    "jataka-parijata": "jatakaparijata-sastri-vol1",
    "hindu-predictive": "hindupredictiveastrology-raman",
    "prashna-tantra": "prashna-tantra",
    "muhurta-chintamani": "muhurtachintamani",
    "saravali": "saravali-santhanam-en",
    "sarvartha-chintamani": "sarvartha-chintamani",
}
"""Koonji book id -> Postgres book slug.

The two disagree for every multi-volume work and for Bhavartha Ratnakara, whose
citation id and slug were never the same string. Explicit rather than derived:
a wrong guess here files a rule against the wrong book and the citation is
wrong forever after.
"""

CONSEQUENT_BLOCKS = ("indicates", "derives", "defines", "remedy",
                     "computes", "guidance", "example")


def effects_of(rule: dict) -> list[dict]:
    """The URF consequent as the `effects` list `embed_rules` embeds.

    Only `assert_claim` has a real outcome statement; the other six kinds say
    something about vocabulary or method rather than about a person. They still
    get an entry, because an empty `effects` list makes `embedding_text`
    fall back to the verse alone and the rule becomes unfindable by outcome.
    """
    domains = list((rule.get("domains") or {}))
    domain = domains[0].removeprefix("domain.") if domains else "general"

    block = rule.get("indicates")
    if isinstance(block, dict):
        return [{
            "statement": block.get("text") or block.get("claim", ""),
            "claim": block.get("claim", ""),
            "polarity": block.get("polarity", "positive"),
            "strength": block.get("magnitude", "moderate"),
            "life_domain": domain,
        }]

    for name in CONSEQUENT_BLOCKS:
        block = rule.get(name)
        if isinstance(block, dict):
            text = (block.get("text") or block.get("action")
                    or block.get("attribute") or block.get("name")
                    or block.get("fact") or block.get("reading") or name)
            return [{"statement": str(text), "claim": "", "polarity": "neutral",
                     "strength": "moderate", "life_domain": domain}]
    return []


def row_for(rule: dict, book_slug: str, verse: str = "") -> dict:
    """One URF rule projected onto the `rule` table's columns.

    `verse` is the unit's full translation. It matters more than it looks:
    `embed_rules.embedding_text` builds the vector from `source["translation"]`,
    and URF has no such field -- only `quote`, the verbatim fragment the
    fabrication tripwire checks. One Brihat Jataka rule's quote is the single
    word "ambassador", and a vector built from that matches nothing a seeker
    would ever type. The quote is kept alongside, because it is what the
    citation displays and what the tripwire verified.
    """
    source = dict(rule.get("source") or {})
    qualifiers = dict(rule.get("qualifiers") or {})
    return {
        "rule_key": f"{book_slug}:{rule['id']}",
        "condition": rule.get("when") or {},
        "raw_condition_text": source.get("quote", "")[:2000] or None,
        "effect": {
            "effects": effects_of(rule),
            "assertion": rule.get("assertion", ""),
            "modifiers": [],
            "exceptions": [],
            "remedies": [],
            "rule_category": "timing" if qualifiers.get("timing") else "formation",
            # The original, unprojected. Everything above is a lossy view of it.
            "urf": rule,
        },
        # `general` when the extraction tagged no domain at all, which happens
        # for about one rule in seven and is not new -- 100 of the 903 BPHS
        # rules predating this are the same. An empty list derives no Rishi
        # affinity, and a rule no Rishi can cite is a rule nobody ever sees, so
        # the choice is between a visible default and silent invisibility.
        # `general` is already a bucket the corpus uses and ATMA already claims
        # it, so this routes them somewhere a reviewer will actually look.
        # `effects_of` has always defaulted the same way; this only stops the
        # column and the effect disagreeing.
        "life_domains": ([d.removeprefix("domain.") for d in (rule.get("domains") or {})]
                         or ["general"]),
        "school": str(rule.get("school", "school.parashari")).removeprefix("school."),
        # `translation` is the key `embedding_text` reads; URF has only `quote`.
        "source": {**source, "translation": verse or source.get("quote", "")},
        "confidence": float(qualifiers.get("confidence", 0.5) or 0.5),
        "status": "parsed",
        "atom_count": 0,
    }


def load_yaml(books: list[str] | None) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for directory in sorted(p for p in EXTRACTED.iterdir() if p.is_dir()):
        if books and directory.name not in books:
            continue
        for path in sorted(directory.glob("*.yaml")):
            for rule in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
                out.append((directory.name, rule))
    return out


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="load extracted URF rules")
    parser.add_argument("--book", action="append", help="koonji book id; repeatable")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    rules = load_yaml(args.book)
    print(f"{len(rules)} extracted rules on disk")
    if not rules:
        return 0

    inserted = updated = skipped = 0
    problems: list[str] = []

    async with async_session_factory() as session:
        book_ids: dict[str, int] = {}
        for book, rule in rules:
            slug = BOOK_SLUG.get(book)
            if slug is None:
                problems.append(f"{book}: no slug mapping"); skipped += 1; continue
            if book not in book_ids:
                found = (await session.execute(select(Book.id).where(
                    Book.slug == slug, Book.deleted_at.is_(None)))).scalar_one_or_none()
                if found is None:
                    problems.append(f"{book}: not bridged"); skipped += 1; continue
                book_ids[book] = found

            locator = (rule.get("source") or {}).get("locator", "")
            match = LOCATOR.match(locator or "")
            if not match:
                problems.append(f"{rule['id']}: unparseable locator {locator!r}")
                skipped += 1
                continue
            unit = (await session.execute(select(
                SutraUnit.id, SutraUnit.translation).where(
                SutraUnit.book_id == book_ids[book],
                SutraUnit.chapter == match["chapter"],
                SutraUnit.verse_ref_local == match["verse"],
                SutraUnit.deleted_at.is_(None)))).first()
            if unit is None:
                # NOT NULL on the table, and rightly: a rule that cannot be
                # traced to the verse it came from cannot be cited.
                problems.append(f"{rule['id']}: no unit for {locator}")
                skipped += 1
                continue

            unit_id, verse = unit
            values = row_for(rule, slug, verse or "")
            existing = (await session.execute(select(Rule).where(
                Rule.rule_key == values["rule_key"]))).scalar_one_or_none()
            if existing is None:
                session.add(Rule(book_id=book_ids[book], unit_id=unit_id,
                                 version=1, **values))
                inserted += 1
            else:
                # Re-running must not approve anything, so `approved_at` is
                # untouched: a reviewer's decision outlives a re-extraction.
                for key, value in values.items():
                    setattr(existing, key, value)
                updated += 1

        print(f"  {inserted} inserted · {updated} updated · {skipped} skipped")
        for problem in problems[:15]:
            print(f"    {problem}")
        if len(problems) > 15:
            print(f"    ... and {len(problems) - 15} more")

        if args.dry_run:
            await session.rollback()
            print("dry run - rolled back")
        else:
            await session.commit()
            print("committed. approved_at is NULL on every row, so nothing is "
                  "matchable yet - review, approve, then scripts.embed_rules")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
