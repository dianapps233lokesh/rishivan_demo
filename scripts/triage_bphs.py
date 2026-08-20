"""S4 Triage — route every BPHS verse to destination A (rule) or B (knowledge_item).

Deterministic and free: no LLM call is made here at all. Units the pattern pass
cannot settle are recorded as `ambiguous`, which is the queue a later paid pass
reads. Nothing is discarded, so `--report` should show unaccounted trending to zero
as extraction proceeds.

    uv run python -m scripts.triage_bphs --dry-run
    uv run python -m scripts.triage_bphs
    uv run python -m scripts.triage_bphs --report
"""

import argparse
import asyncio

from sqlalchemy import select

from rishivan.db.session import async_session_factory
from rishivan.knowledge.accounting import coverage_report, unaccounted_units
from rishivan.knowledge.triage.persist import triage_book
from rishivan.models.knowledge.book import Book

BPHS_SLUGS = ("bphs-gcsharma-vol1", "bphs-gcsharma-vol2")


async def _book_ids(session, slugs) -> list[tuple[str, int]]:
    rows = (
        await session.execute(
            select(Book.slug, Book.id).where(
                Book.slug.in_(slugs), Book.deleted_at.is_(None)
            )
        )
    ).all()
    return sorted(rows, key=lambda r: r[0])


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="triage BPHS units (no LLM)")
    parser.add_argument("--dry-run", action="store_true", help="report, then roll back")
    parser.add_argument(
        "--report", action="store_true", help="only print coverage, write nothing"
    )
    args = parser.parse_args(argv)

    async with async_session_factory() as session:
        books = await _book_ids(session, BPHS_SLUGS)
        if not books:
            print("no BPHS books found; run scripts.bridge_bphs first")
            return 2

        if not args.report:
            for slug, book_id in books:
                report = await triage_book(session, book_id=book_id)
                print(f"{slug}: {report.line()}")

        print()
        for slug, book_id in books:
            cov = await coverage_report(session, book_id=book_id)
            print(
                f"{slug}: units={cov.units} rules={cov.rule_bearing} "
                f"item_only={cov.item_only} unaccounted={cov.unaccounted} "
                f"knowledge_items={cov.knowledge_carrying_items} "
                f"vocab_gaps={cov.vocabulary_gaps} ok={cov.ok}"
            )
            if not cov.ok:
                sample = await unaccounted_units(session, book_id=book_id, limit=3)
                print(f"   awaiting extraction, e.g. {[str(x) for x in sample]}")

        if args.report or args.dry_run:
            await session.rollback()
            print("\nrolled back (nothing written)" if args.dry_run else "")
            return 0
        await session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
