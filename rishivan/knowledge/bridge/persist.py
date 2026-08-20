"""Write the bridge's output, idempotently.

Idempotency is keyed on `corpus_page_element.source_element_id`: an element
already bridged is skipped, never duplicated and never updated. That is what
makes a re-run free and byte-stable, which is a release gate — "same version plus
same input equals the same reasoning state" has to be a test, not an aspiration.

Nothing here writes to `document`, `page` or `source_element`. Those are the
immutable raw layer and the one asset in the system that cannot be rebuilt;
everything else, including every row this module creates, is derivable from them
for free.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rishivan.knowledge.bridge.adapt import SourceRow, adapt_rows
from rishivan.knowledge.bridge.chapter_spans import (
    HEADING_LIKE,
    ChapterIndex,
    detect_chapter_starts,
)
from rishivan.knowledge.bridge.toc import build_chapter_tree
from rishivan.knowledge.bridge.verse_ref import verse_ref_from_translation
from rishivan.knowledge.reflow import adjacency_violations, reflow_book
from rishivan.models.document import Document, SourceElement
from rishivan.models.knowledge.affinity import BookRishiAffinity
from rishivan.models.knowledge.book import Book
from rishivan.models.knowledge.chapter import Chapter
from rishivan.models.knowledge.page import Page, PageElementRow, PageStatus
from rishivan.models.knowledge.unit import SutraUnit


@dataclass
class BridgeReport:
    """What one bridge run did. The numbers feed the M1 pilot report."""

    book_id: int
    pages: int
    elements: int
    units: int
    violations: list[str] = field(default_factory=list)
    inserted: int = 0
    skipped: int = 0
    chapters: int = 0
    chapter_starts_detected: int = 0
    chapter_reassigned: int = 0
    chapter_conflicts: list[str] = field(default_factory=list)
    inferred_verse_refs: int = 0
    ref_disagreements: int = 0
    """Units where the Devanagari verse marker and the translation's own English
    label disagree. Two independent readings of the same number, so a mismatch
    means one of them is misread — measured at 29 across BPHS, mostly the OCR
    confusing Devanagari १ with ९."""

    collapsed_duplicates: int = 0
    """Drafts discarded because another draft shared their chapter and verse ref.
    BPHS's table of contents parses into verse-shaped units and the book reprints
    some verses, so this is expected — 178 across the two volumes. The richest
    draft wins, never the first."""

    @property
    def ok(self) -> bool:
        """M1's hard gate: no verse separated from its meaning."""
        return not self.violations


async def _load_source_rows(session: AsyncSession, document_id: int) -> list[SourceRow]:
    result = await session.execute(
        select(
            SourceElement.id,
            SourceElement.page_number,
            SourceElement.element_index,
            SourceElement.type,
            SourceElement.content,
        )
        .where(SourceElement.document_id == document_id)
        .where(SourceElement.deleted_at.is_(None))
        .order_by(SourceElement.page_number, SourceElement.element_index)
    )
    return [SourceRow(*row) for row in result.all()]


async def _upsert_book(
    session: AsyncSession,
    document: Document,
    *,
    book_title: str,
    source_authority_tier: str,
) -> Book:
    existing = await session.scalar(
        select(Book).where(Book.slug == document.slug, Book.deleted_at.is_(None))
    )
    if existing is not None:
        return existing
    book = Book(
        slug=document.slug,
        title=book_title,
        layer="knowledge",
        school="parashari",
        source_authority_tier=source_authority_tier,
        page_count=document.page_count,
        priority=1,
    )
    session.add(book)
    await session.flush()
    return book


async def _seed_affinity(
    session: AsyncSession, book_id: int, weights: Mapping[str, float]
) -> None:
    present = set(
        (
            await session.execute(
                select(BookRishiAffinity.rishi).where(
                    BookRishiAffinity.book_id == book_id,
                    BookRishiAffinity.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    for rishi, weight in weights.items():
        if rishi not in present:
            session.add(BookRishiAffinity(book_id=book_id, rishi=rishi, weight=weight))


async def _sync_chapters(
    session: AsyncSession,
    book_id: int,
    rows: Sequence[SourceRow],
    *,
    book_title: str,
    total_pdf_pages: int,
) -> int:
    present = set(
        (
            await session.execute(
                select(Chapter.number).where(
                    Chapter.book_id == book_id, Chapter.deleted_at.is_(None)
                )
            )
        ).scalars()
    )
    drafts = build_chapter_tree(
        rows, book_title=book_title, total_pdf_pages=total_pdf_pages
    )
    for draft in drafts:
        if draft.number in present:
            continue
        session.add(
            Chapter(
                book_id=book_id,
                number=draft.number,
                title=draft.title,
                printed_page_from=draft.printed_page_from,
                printed_page_to=draft.printed_page_to,
                pdf_page_from=draft.pdf_page_from,
                pdf_page_to=draft.pdf_page_to,
                is_rule_bearing=draft.is_rule_bearing,
                gating_reason=draft.gating_reason,
            )
        )
    return len(drafts)


async def _page_for(
    session: AsyncSession, book_id: int, page_no: int, cache: dict[int, Page]
) -> Page:
    if page_no in cache:
        return cache[page_no]
    page = await session.scalar(
        select(Page).where(
            Page.book_id == book_id,
            Page.page_no == page_no,
            Page.deleted_at.is_(None),
        )
    )
    if page is None:
        page = Page(book_id=book_id, page_no=page_no, status=PageStatus.extracted)
        session.add(page)
        await session.flush()
    cache[page_no] = page
    return page


def _draft_richness(draft) -> tuple[bool, bool, int]:
    """How much real content a draft carries. Higher is better."""
    return (
        bool(draft.verse_devanagari.strip()),
        bool(draft.translation.strip()),
        len(draft.verse_devanagari) + len(draft.translation) + len(draft.commentary),
    )


def _best_per_key(drafts: Sequence) -> list:
    """One draft per `(chapter, verse_ref)`, keeping the richest.

    `uq_unit_book_chapter_verse` permits one unit per chapter and verse, and BPHS
    produces several: its table of contents parses into verse-shaped units, and the
    book reprints some verses outright. Measured, chapter 48 verse 1 yields four
    drafts — a 2,352-character TOC listing, a front-matter example, the real verse
    on page 25, and the book's own reprint of it on page 725.

    Order alone is the wrong tiebreak: taking the first would persist the table of
    contents as Parashara's verse. Presence of Devanagari dominates the ranking,
    since front matter never carries it.
    """
    best: dict[tuple[str | None, str | None], object] = {}
    for draft in drafts:
        key = (draft.chapter, draft.verse_ref_local)
        incumbent = best.get(key)
        if incumbent is None or _draft_richness(draft) > _draft_richness(incumbent):
            best[key] = draft
    return list(best.values())


async def bridge_book(
    session: AsyncSession,
    *,
    document_slug: str,
    book_title: str,
    rishi_weights: Mapping[str, float],
    source_authority_tier: str = "S0",
) -> BridgeReport:
    """Bridge one already-ingested document into the knowledge layer.

    Deterministic and re-runnable: no LLM call, and a second run over the same
    document inserts nothing.
    """
    document = await session.scalar(
        select(Document).where(
            Document.slug == document_slug, Document.deleted_at.is_(None)
        )
    )
    if document is None:
        raise LookupError(f"no document with slug {document_slug!r}")

    rows = await _load_source_rows(session, document.id)
    book = await _upsert_book(
        session,
        document,
        book_title=book_title,
        source_authority_tier=source_authority_tier,
    )
    await _seed_affinity(session, book.id, rishi_weights)
    chapters = await _sync_chapters(
        session,
        book.id,
        rows,
        book_title=book_title,
        total_pdf_pages=document.page_count,
    )

    already = set(
        (
            await session.execute(
                select(PageElementRow.source_element_id)
                .join(Page, Page.id == PageElementRow.page_id)
                .where(
                    Page.book_id == book.id,
                    PageElementRow.source_element_id.is_not(None),
                )
            )
        ).scalars()
    )

    ordered = adapt_rows(rows, book_title=book_title)

    # Chapter boundaries come from the body, positionally. `chapter_spans` records why
    # neither the sticky heading value nor the printed TOC could be trusted on its own:
    # they disagreed on 891 of 2,063 units. The TOC is still used for one thing -- where
    # the body begins -- because the front-matter contents lines are indistinguishable
    # from chapter headings and produced 21 phantom starts in vol 2.
    body_starts_at = (
        await session.scalar(
            select(func.min(Chapter.pdf_page_from)).where(
                Chapter.book_id == book.id, Chapter.deleted_at.is_(None)
            )
        )
    ) or 0
    heading_rows = [
        (item.page_no, item.element.reading_order, item.element.text)
        for item in ordered
        if item.element.type.value in HEADING_LIKE
    ]
    span_report = detect_chapter_starts(heading_rows, body_starts_at=body_starts_at)
    chapter_index = ChapterIndex(span_report.starts)
    reassigned_chapters: list[tuple[str | None, str]] = []

    pages: dict[int, Page] = {}
    inserted = skipped = 0
    for item in ordered:
        if item.element_id in already:
            skipped += 1
            continue
        page = await _page_for(session, book.id, item.page_no, pages)
        session.add(
            PageElementRow(
                page_id=page.id,
                reading_order=item.element.reading_order,
                element_type=item.element.type.value,
                script=item.element.script.value,
                text=item.element.text,
                bbox=None,
                verse_no=item.element.verse_no,
                chapter_hint=item.element.chapter_hint,
                continues_to_next_page=False,
                source_element_id=item.element_id,
            )
        )
        inserted += 1

    units = reflow_book(ordered)

    # Reflow's own chapter value is now only a hint. Overwrite it from position, and
    # count how often the two differ -- that count is the size of the defect this
    # replaces, and it belongs in the report rather than in a comment.
    element_positions = {
        item.element_id: (item.page_no, item.element.reading_order) for item in ordered
    }
    for draft in units:
        first = next(
            (
                element_positions[element_id]
                for element_id in draft.element_ids
                if element_id in element_positions
            ),
            None,
        )
        if first is None:
            continue
        resolved = chapter_index.chapter_at(*first)
        if resolved is None:
            continue
        if draft.chapter != str(resolved):
            reassigned_chapters.append((draft.chapter, str(resolved)))
        draft.chapter = str(resolved)

    violations = adjacency_violations(units)

    existing_units = set(
        (
            await session.execute(
                select(SutraUnit.chapter, SutraUnit.verse_ref_local).where(
                    SutraUnit.book_id == book.id, SutraUnit.deleted_at.is_(None)
                )
            )
        ).all()
    )
    ref_disagreements = 0
    deduped = _best_per_key(units)
    for draft in deduped:
        key = (draft.chapter, draft.verse_ref_local)
        if key in existing_units:
            continue
        existing_units.add(key)

        # Cross-check the Devanagari marker against the translation's own English
        # label. They are independent readings of the same number, so disagreement
        # means one is misread — and it is flagged rather than resolved, because
        # picking a winner would silently overwrite the book. Vol 1 labels most of
        # its translations; vol 2 almost never does, so most units have no second
        # opinion available and this check stays silent for them.
        english_ref = verse_ref_from_translation(draft.translation)
        disagrees = english_ref is not None and english_ref != draft.verse_ref_local
        if disagrees:
            ref_disagreements += 1

        session.add(
            SutraUnit(
                book_id=book.id,
                chapter=draft.chapter,
                verse_ref_local=draft.verse_ref_local,
                verse_devanagari=draft.verse_devanagari,
                verse_iast=draft.verse_iast,
                translation=draft.translation,
                commentary=draft.commentary,
                element_ids=draft.element_ids,
                page_from=draft.page_from,
                page_to=draft.page_to,
                inferred_verse_no=draft.inferred_verse_no,
                # A verse whose number was counted rather than read, one with no
                # translation attached, or one whose two readings of its own number
                # disagree — exactly what a reviewer should see first.
                needs_review=(
                    draft.inferred_verse_no or not draft.has_translation or disagrees
                ),
            )
        )

    await session.flush()
    return BridgeReport(
        book_id=book.id,
        pages=len(pages),
        elements=len(ordered),
        units=len(units),
        violations=violations,
        inserted=inserted,
        skipped=skipped,
        chapters=chapters,
        chapter_starts_detected=len(chapter_index),
        chapter_reassigned=len(reassigned_chapters),
        chapter_conflicts=span_report.conflicts + span_report.duplicates,
        inferred_verse_refs=sum(unit.inferred_verse_no for unit in units),
        ref_disagreements=ref_disagreements,
        collapsed_duplicates=len(units) - len(deduped),
    )
