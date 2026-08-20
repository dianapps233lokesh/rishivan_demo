"""Bridge and triage every ingested book, so extraction can run over the whole corpus.

    uv run python -m scripts.prepare_corpus --report
    uv run python -m scripts.prepare_corpus --dry-run
    uv run python -m scripts.prepare_corpus --book phaladeepika-sastri-1950
    uv run python -m scripts.prepare_corpus

Deterministic and idempotent: no LLM call anywhere, and a second run inserts nothing.

Each book brings three pieces of data rather than code -- its `EditionProfile` (how it
prints chapters), its Eight Rishis §15 row (what it is relevant to) and its Blueprint §12
tier (how authoritative it is). Everything downstream is book-agnostic.

Books whose profile declares no chapter words are SKIPPED with the reason printed. That
is deliberate: Deva Keralam prints "BOOK I" and no chapters, and filing its slokas under
an invented chapter 1 would fabricate every citation in the book.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from rishivan.council.source_matrix import (
    SOURCE_RISHI_WEIGHTS,
    authority_tier,
    source_family_for_slug,
)
from rishivan.db.session import async_session_factory
from rishivan.knowledge.bridge.editions import profile_for
from rishivan.knowledge.bridge.persist import bridge_book
from rishivan.knowledge.triage.persist import triage_book
from rishivan.models.document import Document
from rishivan.models.knowledge.affinity import RISHI_KEYS, WEIGHT_MEDIUM

MAX_VIOLATIONS_SHOWN = 5


def rishi_weights_for(slug: str) -> dict[str, float]:
    """The book's §15 row, as the affinity weights the bridge stores.

    Falls back to uniform MEDIUM for a book §15 does not rate, which is the honest
    default: neither claiming High coverage nobody granted, nor excluding the book.
    """
    family = source_family_for_slug(slug)
    if family is None:
        return dict.fromkeys(RISHI_KEYS, WEIGHT_MEDIUM)
    return dict(SOURCE_RISHI_WEIGHTS[family])


def book_title_for(document: Document) -> str:
    """The work's title, from its edition profile.

    `document.title` is derived from the uploaded filename ("Bphs Gcsharma Vol1"), and
    it becomes `Book.title`, which is what a citation prints.
    """
    return profile_for(document.slug).title or document.title or document.slug


async def prepare_one(session, document: Document, *, triage: bool) -> dict:
    """Bridge then triage one book. Returns a row for the report."""
    slug = document.slug
    profile = profile_for(slug)
    row = {
        "slug": slug,
        "tier": authority_tier(slug),
        "family": source_family_for_slug(slug) or "-",
        "skipped": "",
        "chapters": 0,
        "units": 0,
        "rule_units": 0,
        "violations": 0,
    }

    if not profile.chapter_words:
        row["skipped"] = profile.notes.split(".")[0] or "no numbered chapters"
        return row

    report = await bridge_book(
        session,
        document_slug=slug,
        book_title=book_title_for(document),
        rishi_weights=rishi_weights_for(slug),
        source_authority_tier=authority_tier(slug),
    )
    row["chapters"] = report.chapters
    row["units"] = report.units
    row["violations"] = len(report.violations)
    row["_violations"] = report.violations[:MAX_VIOLATIONS_SHOWN]

    if triage and report.units:
        triage_report = await triage_book(session, book_id=report.book_id)
        row["rule_units"] = triage_report.rule
    return row


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bridge and triage the whole corpus (deterministic, no LLM)"
    )
    parser.add_argument("--book", help="prepare only this document slug")
    parser.add_argument(
        "--dry-run", action="store_true", help="report what would be written, then roll back"
    )
    parser.add_argument(
        "--no-triage", action="store_true", help="bridge only, skip the triage pass"
    )
    args = parser.parse_args(argv)

    async with async_session_factory() as session:
        documents = (
            await session.execute(
                select(Document)
                .where(Document.deleted_at.is_(None))
                .order_by(Document.slug)
            )
        ).scalars().all()
        if args.book:
            documents = [d for d in documents if d.slug == args.book]
            if not documents:
                print(f"no ingested document with slug {args.book!r}", file=sys.stderr)
                return 2

        rows = []
        for document in documents:
            row = await prepare_one(session, document, triage=not args.no_triage)
            rows.append(row)
            print(
                f"{row['slug']:<40}{row['tier']:>4}"
                f"{row['chapters']:>6}{row['units']:>7}{row['rule_units']:>7}"
                f"  {row['skipped']}"
            )
            for violation in row.get("_violations", []):
                print(f"    orphan {violation}".replace("\n", " / "), file=sys.stderr)

        if args.dry_run:
            await session.rollback()
            print("\ndry run — rolled back")
        else:
            await session.commit()

    prepared = [r for r in rows if not r["skipped"]]
    skipped = [r for r in rows if r["skipped"]]
    print(
        f"\n{len(prepared)} books prepared, {len(skipped)} skipped | "
        f"chapters={sum(r['chapters'] for r in prepared)} "
        f"units={sum(r['units'] for r in prepared)} "
        f"rule_units={sum(r['rule_units'] for r in prepared)}"
    )
    for row in skipped:
        print(f"  skipped {row['slug']}: {row['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
