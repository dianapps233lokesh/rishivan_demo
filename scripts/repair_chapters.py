"""Re-derive `sutra_unit.chapter` from body chapter headings.

Why a repair script and not just a re-run: the bridge is idempotent on
`(chapter, verse_ref_local)`, so re-running it leaves existing rows exactly as they
are -- including the 43.2% whose chapter was wrong. The rows have to be corrected in
place.

Collisions are expected and are not errors. Two units previously kept apart by
*different wrong* chapter numbers can land on the same `(chapter, verse_ref_local)`
once both are corrected, which the `uq_unit_book_chapter_verse` index forbids. That
happens where the book genuinely reprints a verse. The resolution matches the bridge's
own `_best_per_key` rule -- keep the richest row, soft-delete the rest -- so nothing is
destroyed and the decision is reversible.

    uv run python -m scripts.repair_chapters --dry-run
    uv run python -m scripts.repair_chapters
"""

import argparse
import asyncio
from collections import Counter

from sqlalchemy import func, select

from rishivan.db.session import async_session_factory
from rishivan.knowledge.bridge.adapt import adapt_rows
from rishivan.knowledge.bridge.chapter_spans import (
    HEADING_LIKE,
    ChapterIndex,
    detect_chapter_starts,
)
from rishivan.knowledge.bridge.persist import _load_source_rows
from rishivan.knowledge.bridge.toc import build_chapter_tree
from rishivan.models.document import Document
from rishivan.models.knowledge.book import Book
from rishivan.models.knowledge.chapter import Chapter
from rishivan.models.knowledge.unit import SutraUnit

BOOKS = ("bphs-gcsharma-vol1", "bphs-gcsharma-vol2")
BOOK_TITLE = "Brihat Parasara Hora Shastra"


def richness(unit: SutraUnit) -> tuple[int, int, int]:
    """How much real content a row carries -- the bridge's tie-break, reused."""
    return (
        len(unit.verse_devanagari or ""),
        len(unit.translation or ""),
        len(unit.commentary or ""),
    )


async def repair_book(session, slug: str, *, apply: bool) -> dict:
    document = (
        await session.execute(select(Document).where(Document.slug == slug))
    ).scalar_one()
    book = (await session.execute(select(Book).where(Book.slug == slug))).scalar_one()

    rows = await _load_source_rows(session, document.id)
    ordered = adapt_rows(rows, book_title=BOOK_TITLE)
    body_starts_at = (
        await session.scalar(
            select(func.min(Chapter.pdf_page_from)).where(
                Chapter.book_id == book.id, Chapter.deleted_at.is_(None)
            )
        )
    ) or 0
    headings = [
        (item.page_no, item.element.reading_order, item.element.text)
        for item in ordered
        if item.element.type.value in HEADING_LIKE
    ]
    report = detect_chapter_starts(headings, body_starts_at=body_starts_at)
    index = ChapterIndex(report.starts)
    positions = {
        item.element_id: (item.page_no, item.element.reading_order) for item in ordered
    }

    units = list(
        (
            await session.execute(
                select(SutraUnit).where(
                    SutraUnit.book_id == book.id, SutraUnit.deleted_at.is_(None)
                )
            )
        ).scalars()
    )

    # Titles follow the body too. The TOC has vol 1's chapters 26 and 27 transposed,
    # so a verse can be assigned the right chapter number and still be cited under the
    # wrong chapter name.
    retitled: list[str] = []
    chapter_rows = {
        row.number: row
        for row in (
            await session.execute(
                select(Chapter).where(
                    Chapter.book_id == book.id, Chapter.deleted_at.is_(None)
                )
            )
        ).scalars()
    }
    # The TOC supplies the baseline title; the body overrides it only where the body
    # actually prints one. Most vol 2 headings are bare (`Chapter - 55`), and an earlier
    # version replaced their perfectly good TOC titles with a single digit.
    toc_titles = {
        draft.number: draft.title
        for draft in build_chapter_tree(
            rows, book_title=BOOK_TITLE, total_pdf_pages=document.page_count
        )
    }
    body_titles = {
        start.number: start.title for start in report.starts if start.title
    }
    for number, row in chapter_rows.items():
        wanted = body_titles.get(number) or toc_titles.get(number)
        if not wanted or row.title.strip() == wanted.strip():
            continue
        source = "body" if number in body_titles else "toc"
        retitled.append(f"ch{number} ({source}): {row.title!r} -> {wanted!r}")
        if apply:
            row.title = wanted[:300]

    moves: Counter = Counter()
    resolved: dict[int, str] = {}
    unresolved = 0
    for unit in units:
        first = next(
            (positions[e] for e in (unit.element_ids or []) if e in positions), None
        )
        chapter = index.chapter_at(*first) if first else None
        if chapter is None:
            unresolved += 1
            continue
        resolved[unit.id] = str(chapter)
        if str(chapter) != unit.chapter:
            moves[(unit.chapter, str(chapter))] += 1

    # Group by the post-repair key so collisions are settled before writing.
    #
    # Unresolved units are included, keyed on the chapter they keep. Excluding them
    # missed a real collision -- a unit whose position falls before the first detected
    # heading stays on ch47 v1, and a mover targeting ch47 v1 then hit
    # `Key (book_id, chapter, verse_ref_local)=(11, 47, 1) already exists`. Every row
    # that will occupy a key has to be in the map, whether or not it moved.
    by_key: dict[tuple[str | None, str | None], list[SutraUnit]] = {}
    for unit in units:
        key = (resolved.get(unit.id, unit.chapter), unit.verse_ref_local)
        by_key.setdefault(key, []).append(unit)

    retired = 0
    winners: list[SutraUnit] = []
    for group in by_key.values():
        winner = max(group, key=richness)
        winners.append(winner)
        for unit in group:
            if unit is winner:
                continue
            retired += 1
            if apply:
                unit.delete()

    if apply:
        # Three phases, because `uq_unit_book_chapter_verse` is enforced per statement,
        # not at commit. Writing the new chapters directly fails with
        # `Key (book_id, chapter, verse_ref_local)=(11, 11, 1) already exists`: a unit
        # moving INTO ch11 v1 collides with the unit that is itself about to move OUT of
        # it. A rename cycle needs somewhere to stand.
        #
        # 1. retire the duplicates, so the keys they hold are freed
        await session.flush()
        # 2. park every mover on a value nothing can collide with
        movers = [
            u for u in winners if u.id in resolved and u.chapter != resolved[u.id]
        ]
        for unit in movers:
            unit.chapter = f"~{unit.id}"
        await session.flush()
        # 3. write the real chapters into now-vacant keys
        for unit in movers:
            unit.chapter = resolved[unit.id]
        await session.flush()

    return {
        "slug": slug,
        "starts": len(index),
        "units": len(units),
        "reassigned": sum(moves.values()),
        "unresolved": unresolved,
        "retired_duplicates": retired,
        "rejected_headings": len(report.rejected),
        "conflicts": report.conflicts,
        "retitled": retitled,
        "top_moves": moves.most_common(5),
    }


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="repair sutra_unit.chapter")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    async with async_session_factory() as session:
        for slug in BOOKS:
            result = await repair_book(session, slug, apply=not args.dry_run)
            print(
                f"{result['slug']}: starts={result['starts']} units={result['units']} "
                f"reassigned={result['reassigned']} unresolved={result['unresolved']} "
                f"retired_dupes={result['retired_duplicates']} "
                f"rejected_headings={result['rejected_headings']}"
            )
            for (old, new), count in result["top_moves"]:
                print(f"    ch{old} -> ch{new}: {count} units")
            print(f"    titles corrected from body headings: {len(result['retitled'])}")
            for change in result["retitled"][:4]:
                print(f"      {change}")
            for conflict in result["conflicts"]:
                print(f"    CONFLICT {conflict}")
        if args.dry_run:
            await session.rollback()
            print("\ndry run: rolled back")
        else:
            await session.commit()
            print("\ncommitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
