"""Export bridged Sutra Units to the JSONL the Koonji extractor reads.

    uv run python -m scripts.export_corpus --report
    uv run python -m scripts.export_corpus --book sarvartha-chintamani
    uv run python -m scripts.export_corpus            # every mapped book

`prepare_corpus` bridges a book into Postgres; `koonji.corpus` reads JSONL off
disk. Nothing joined the two, so the extraction corpus was whatever the OLD
extractor happened to have written months ago -- for Jataka Parijata vol 1 that
is 392 rows against 1,274 bridged units, so two thirds of the book was
unreachable and nothing said so.

Deterministic and free: no LLM call, no network beyond Postgres.

**Every unit is exported, not just the rule-bearing ones.** `to_passages` builds
each passage's context from the verses immediately before it, and triage's
`destination='rule'` units are scattered through a chapter rather than
contiguous. Exporting only those would hand the extractor a "preceding verse"
that is fifteen verses back and about something else, which is precisely the
anaphora failure the context window exists to prevent. The extractor's first
call is a cheap classifier that drops non-rule passages for one flash call, so
the cost of honest context is small and the cost of dishonest context is a
wrong rule with a real citation.

**Existing files are backed up, never overwritten in place.** The legacy JSONL
carries the old extractor's `rule` key, which `koonji/convert.py` still reads to
produce `rules/converted/`. Overwriting it would silently remove the input to a
pipeline nobody is thinking about at the time.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

from sqlalchemy import select

from rishivan.db.session import async_session_factory
from rishivan.koonji.corpus import BOOKS
from rishivan.models.knowledge.book import Book
from rishivan.models.knowledge.triage import UnitTriage
from rishivan.models.knowledge.unit import SutraUnit

CORPUS_DIR = Path(__file__).resolve().parents[1] / "koonji"
LEGACY_DIR = CORPUS_DIR / "legacy"

SLUG_BY_STEM: dict[str, str] = {stem: edition for stem, (_, edition) in BOOKS.items()}
"""File stem -> the citation's edition id. `koonji.corpus.BOOKS` is the
authority, so a book absent there cannot be exported: `load_units` would not
know what book_id to stamp on its citations."""

STEM_BY_SLUG: dict[str, str] = {slug: stem for stem, slug in SLUG_BY_STEM.items()}


async def units_for(session, slug: str, stem: str) -> tuple[list[dict], str]:
    """Every bridged unit of one book, in reading order, as corpus rows.

    Looks the book up by edition id and then by file stem, because the two
    disagree for Bhavartha Ratnakara: the citation says
    `bhavartha-ratnakara-raman` while Postgres knows it as
    `bhavartha-ratnakara-by-b-v-raman-text`. Trying only the first reported the
    book as unbridged when it was bridged and sitting right there.
    """
    book_id = (
        await session.execute(
            select(Book.id)
            .where(Book.slug.in_({slug, stem}), Book.deleted_at.is_(None))
            .limit(1)
        )
    ).scalar_one_or_none()
    if book_id is None:
        return [], "not bridged - run scripts.prepare_corpus first"

    rows = (
        await session.execute(
            select(SutraUnit, UnitTriage.destination)
            .outerjoin(
                UnitTriage,
                (UnitTriage.unit_id == SutraUnit.id)
                & (UnitTriage.deleted_at.is_(None)),
            )
            .where(SutraUnit.book_id == book_id, SutraUnit.deleted_at.is_(None))
            .order_by(SutraUnit.id)
        )
    ).all()
    if not rows:
        return [], "bridged but has no units"

    out: list[dict] = []
    for unit, destination in rows:
        out.append({
            "unit_id": unit.id,
            "chapter": unit.chapter or "",
            "verse_ref": unit.verse_ref_local or "",
            "translation": unit.translation or "",
            # `needs_review` is the bridge's own doubt about the pairing. It is
            # reported rather than filtered: a book dropping from 950 usable
            # units to 12 is a bridge regression, and a loader that hides it
            # makes that invisible.
            "valid": not unit.needs_review,
            "problems": ["needs_review"] if unit.needs_review else [],
            # Triage's verdict travels with the row so a later pass can measure
            # the classifier against it. The extractor does not read it.
            "destination": destination or "unclassified",
        })
    return out, ""


def write_book(stem: str, rows: list[dict], *, dry_run: bool) -> str:
    """One row per verse, and deliberately no `rule` key.

    The old extractor's output is NOT merged in here. It is one row per
    extracted rule -- eighteen for a single Jataka Parijata unit -- so folding
    it into a verse-keyed corpus either duplicates passages the new extractor
    would then pay to re-read, or collapses eighteen rules into one and loses
    seventeen. It stays in `koonji/legacy/`, where `convert.py` now reads it.
    """
    path = CORPUS_DIR / f"{stem}.jsonl"
    rule_bearing = sum(1 for r in rows if r["destination"] == "rule")
    citable = sum(1 for r in rows if r["chapter"] and r["verse_ref"] and r["translation"].strip())
    note = f"{len(rows):5d} units  {citable:5d} citable  {rule_bearing:5d} rule-bearing"

    if dry_run:
        return f"{note}  (dry run)"

    # Only the FIRST export archives the original. A later run would otherwise
    # move its own output over the backup and destroy the only copy of the old
    # extractor's work -- an idempotent-looking command that is destructive on
    # its second invocation.
    if path.exists() and not (LEGACY_DIR / path.name).exists():
        LEGACY_DIR.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(LEGACY_DIR / path.name))
        note += f"  (original -> legacy/{path.name})"

    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return note


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="export bridged units to corpus JSONL")
    parser.add_argument("--book", action="append", help="book slug; repeatable")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", action="store_true", help="counts only, write nothing")
    args = parser.parse_args(argv)

    wanted = args.book or sorted(STEM_BY_SLUG)
    unknown = [s for s in wanted if s not in STEM_BY_SLUG]
    if unknown:
        print(f"not in koonji.corpus.BOOKS: {', '.join(unknown)}", file=sys.stderr)
        print("Add them there first - a book with no book_id cannot be cited.", file=sys.stderr)
        return 2

    dry = args.dry_run or args.report
    total_units = total_rules = 0
    async with async_session_factory() as session:
        for slug in wanted:
            rows, problem = await units_for(session, slug, STEM_BY_SLUG[slug])
            if problem:
                print(f"  {slug:45s} SKIPPED - {problem}")
                continue
            total_units += len(rows)
            total_rules += sum(1 for r in rows if r["destination"] == "rule")
            print(f"  {slug:45s} {write_book(STEM_BY_SLUG[slug], rows, dry_run=dry)}")

    print(f"\n{total_units} units exported, {total_rules} rule-bearing")
    if dry:
        print("nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
