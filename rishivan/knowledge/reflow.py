"""S5 — stream a book's elements into Sutra Units.

Per-BOOK, not per-page. A verse at the foot of page 40 has its translation at
the head of page 41; any per-page transform orphans it. The open unit survives
the page boundary — page boundaries are invisible to this state machine by
design, and the single most common way to break it is to close the open unit
when the page number changes.
"""

import re
from collections.abc import Iterable

from pydantic import BaseModel

from rishivan.knowledge.schemas.page import ElementType, PageElement
from rishivan.knowledge.schemas.unit import SutraUnitDraft

RANGE_RE = re.compile(r"^\s*(\d+)\s*[-–]\s*(\d+)\s*$")
LEADING_INT_RE = re.compile(r"^\s*(\d+)")
CHAPTER_RE = re.compile(r"(\d+)")

FIELD_OF: dict[ElementType, str] = {
    ElementType.verse: "verse_devanagari",
    ElementType.iast: "verse_iast",
    ElementType.translation: "translation",
    ElementType.commentary: "commentary",
    ElementType.prose: "commentary",
    ElementType.footnote: "commentary",
}
"""Which unit field each element type feeds. `verse` is here because a verse can
continue across a page break, but it is excluded from FILLERS below: a verse
otherwise *opens* a unit rather than filling one."""

FILLERS = {
    kind: field for kind, field in FIELD_OF.items() if kind is not ElementType.verse
}

TEXT_ONLY_ATTACHMENTS = (ElementType.table, ElementType.figure_chart)


class OrderedElement(BaseModel):
    page_no: int
    element_id: int
    element: PageElement


def _parse_verse_no(raw: str | None) -> tuple[str | None, tuple[int, int] | None]:
    if not raw or not raw.strip():
        return None, None
    if match := RANGE_RE.match(raw):
        return raw.strip(), (int(match.group(1)), int(match.group(2)))
    return raw.strip(), None


def _numeric_tail(ref: str, span: tuple[int, int] | None) -> int | None:
    """The number to count from for the next unnumbered verse.

    `None` for a non-numeric ref (front matter carries 'iv', appendices 'A'):
    counting from those would invent a number that looks read rather than
    inferred, so we decline and let the next verse start over.
    """
    if span is not None:
        return span[1]
    match = LEADING_INT_RE.match(ref)
    return int(match.group(1)) if match else None


def _merge_refs(
    current_ref: str | None, new_ref: str | None, new_span: tuple[int, int] | None
) -> tuple[str, tuple[int, int]] | None:
    """Span two grouped verse references into one, or `None` if either is unusable.

    `"13-14"` grouped with `"15"` becomes `("13-15", (13, 15))`. Declines when
    either side is non-numeric — front matter carries 'iv' and appendices 'A', and
    inventing a range across those would fabricate a citation.
    """
    if current_ref is None or new_ref is None:
        return None
    start_match = LEADING_INT_RE.match(current_ref)
    if start_match is None:
        return None
    end = new_span[1] if new_span is not None else None
    if end is None:
        end_match = LEADING_INT_RE.match(new_ref)
        if end_match is None:
            return None
        end = int(end_match.group(1))
    start = int(start_match.group(1))
    if end < start:
        return None
    return (str(start) if start == end else f"{start}-{end}"), (start, end)


def reflow_book(elements: Iterable[OrderedElement]) -> list[SutraUnitDraft]:
    units: list[SutraUnitDraft] = []
    current: SutraUnitDraft | None = None
    chapter: str | None = None
    last_verse_no: int | None = None
    pending_field: str | None = None  # field left open by continues_to_next_page

    def close() -> None:
        nonlocal current
        if current is None:
            return
        for field in ("verse_devanagari", "verse_iast", "translation", "commentary"):
            setattr(current, field, getattr(current, field).strip())
        units.append(current)
        current = None

    def append(unit: SutraUnitDraft, field: str, text: str) -> None:
        existing = getattr(unit, field)
        setattr(unit, field, f"{existing} {text}".strip() if existing else text)

    for ordered in elements:
        element = ordered.element
        kind = element.type
        field = FIELD_OF.get(kind)

        if kind is ElementType.page_furniture:
            continue

        if kind is ElementType.heading:
            close()
            if element.chapter_hint:
                chapter = element.chapter_hint
            elif match := CHAPTER_RE.search(element.text):
                chapter = match.group(1)
            last_verse_no = None
            pending_field = None
            continue

        # --- continuation of an element split across a page boundary ----------
        # Checked BEFORE `opens`, so a half-verse at the foot of a page rejoins
        # its other half instead of opening a second, translation-less unit.
        # Matched on field, so a `continues` commentary cannot swallow the next
        # page's verse.
        if current is not None and pending_field is not None and field == pending_field:
            append(current, pending_field, element.text)
            current.element_ids.append(ordered.element_id)
            current.page_to = ordered.page_no
            pending_field = pending_field if element.continues_to_next_page else None
            continue
        pending_field = None

        # --- anchors: open a new unit -----------------------------------------
        # A numbered translation anchors a unit in editions that print no
        # Devanagari at all. It opens only when it cannot belong to the unit
        # already open, so a translation printed in two blocks stays one unit.
        ref, span = _parse_verse_no(element.verse_no)
        opens = kind is ElementType.verse or (
            kind is ElementType.translation
            and ref is not None
            and (
                current is None
                or (current.translation.strip() and ref != current.verse_ref_local)
            )
        )

        if opens:
            # A verse arriving while the open unit still has no translation means
            # this edition groups several printed verses under one shared
            # translation — BPHS does exactly that: verses 13-14 and 15 are set as
            # separate blocks with a single "13-15" rendering beneath them.
            # Closing here would orphan the earlier verse from a meaning that is
            # about to arrive, so the group becomes one unit and its reference
            # spans the range. Measured on BPHS, this recovers 106 units that
            # would otherwise fail the adjacency gate.
            if (
                kind is ElementType.verse
                and current is not None
                and current.verse_devanagari.strip()
                and not current.has_translation
            ):
                append(current, "verse_devanagari", element.text)
                current.element_ids.append(ordered.element_id)
                current.page_to = ordered.page_no
                merged = _merge_refs(current.verse_ref_local, ref, span)
                if merged is not None:
                    current.verse_ref_local, current.verse_range = merged
                    last_verse_no = _numeric_tail(
                        current.verse_ref_local, current.verse_range
                    )
                pending_field = (
                    "verse_devanagari" if element.continues_to_next_page else None
                )
                continue

            close()
            inferred = False
            if ref is None:
                ref = str(last_verse_no + 1) if last_verse_no is not None else "1"
                inferred = True
            current = SutraUnitDraft(
                chapter=chapter,
                verse_ref_local=ref,
                verse_range=span,
                inferred_verse_no=inferred,
                page_from=ordered.page_no,
                page_to=ordered.page_no,
                element_ids=[ordered.element_id],
            )
            setattr(
                current,
                "verse_devanagari" if kind is ElementType.verse else "translation",
                element.text,
            )
            last_verse_no = _numeric_tail(ref, span)
            pending_field = field if element.continues_to_next_page else None
            continue

        if current is None:
            # Front matter, index pages, orphan prose. Nothing to attach it to,
            # and inventing a unit for it would pollute retrieval.
            continue

        if fill := FILLERS.get(kind):
            append(current, fill, element.text)
            current.element_ids.append(ordered.element_id)
            current.page_to = ordered.page_no
            pending_field = fill if element.continues_to_next_page else None
            continue

        # Tables and chart figures attach by reference only: their payload is
        # structure, and flattening it into commentary prose would lose it.
        if kind in TEXT_ONLY_ATTACHMENTS:
            current.element_ids.append(ordered.element_id)
            current.page_to = ordered.page_no

    close()
    return units


def adjacency_violations(units: list[SutraUnitDraft]) -> list[str]:
    """A unit carrying a verse but no translation is an orphan. K3 requires zero.

    This is the check that catches the pipeline's most dangerous silent failure:
    a verse attached to the wrong meaning still retrieves, still cites, and
    still reads fluently.
    """
    return [
        f"ch{unit.chapter}:v{unit.verse_ref_local} has a verse but no translation"
        for unit in units
        if unit.verse_devanagari.strip() and not unit.has_translation
    ]
