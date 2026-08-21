"""Lift POC `source_element` rows into the rich `PageElement` vocabulary.

The POC extractor emitted six coarse types (`english_prose`, `heading`, `shloka`,
`table`, `chart`, `image`) with no verse numbers, no chapter hints and no
geometry. `reflow_book()` needs eleven types plus verse references. Everything
that gap requires is derivable deterministically from the text itself, which is
why M1 spends nothing on a model.

Two decisions in here are load-bearing.

**Running heads become `page_furniture`.** `reflow_book()` closes the open unit on
every `heading`, and BPHS prints a running head on every page (1,304 of its 2,361
headings). Mapping those to `heading` would close the unit at each page boundary
and orphan every verse whose translation sits overleaf.

**`continues_to_next_page` is always `False`.** Reflow has two paths that append
prose to an open unit: the `pending_field` continuation path, driven by that flag,
and the `FILLERS` path. An element typed `translation` with `verse_no=None` makes
`opens` evaluate `False`, so `FILLERS` appends it to the translation field
correctly. The POC data carries no split markers, so setting the flag would be a
guess; continuation is handled instead by *role inheritance* — an unmarked prose
block takes the previous block's role, and 3,309 of BPHS's 4,888 prose blocks are
unmarked, so this is the common case rather than the exception.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from rishivan.knowledge.bridge.clean import strip_ingestion_prefixes
from rishivan.knowledge.bridge.roles import (
    ProseRole,
    chapter_number,
    classify_prose,
    is_chapter_heading,
    is_notes_marker,
    is_running_head,
)
from rishivan.knowledge.bridge.verse_ref import (
    verse_ref_from_translation,
    verse_ref_from_verse_text,
)
from rishivan.knowledge.reflow import OrderedElement
from rishivan.knowledge.schemas.page import ElementType, PageElement, Script

_ROLE_TO_TYPE = {
    ProseRole.translation: ElementType.translation,
    ProseRole.commentary: ElementType.commentary,
}

_DEFAULT_PROSE_TYPE = ElementType.commentary
"""What an unmarked prose block becomes when nothing precedes it.

Commentary rather than translation: attaching stray front matter to a verse's
*meaning* would corrupt a citation, whereas attaching it to commentary merely
adds noise a reviewer can see and ignore.
"""

_SOURCE_TYPE_TO_ELEMENT = {
    "table": ElementType.table,
    "chart": ElementType.figure_chart,
}
"""Structural types pass through. Their payload is structure, and reflow attaches
them by reference so flattening them into prose cannot lose it."""


@dataclass(frozen=True)
class SourceRow:
    """One `source_element` row. Read-only: the raw layer is never written."""

    id: int
    page_number: int
    element_index: int
    type: str
    content: str | None


def _script_for(element_type: ElementType) -> Script:
    return Script.deva if element_type is ElementType.verse else Script.latin


def adapt_rows(rows: Sequence[SourceRow], *, book_title: str) -> list[OrderedElement]:
    """Ordered `OrderedElement`s ready for `reflow_book()`.

    Rows are sorted by `(page_number, element_index)`: reflow is a per-book state
    machine and depends on true printed order, not on database order.
    """
    ordered_rows = sorted(rows, key=lambda r: (r.page_number, r.element_index))

    out: list[OrderedElement] = []
    last_prose_type: ElementType | None = None
    reading_order = 0

    for source in ordered_rows:
        text = strip_ingestion_prefixes(source.content or "")
        if not text:
            continue

        verse_no: str | None = None
        chapter_hint: str | None = None

        if source.type == "shloka":
            element_type = ElementType.verse
            verse_no = verse_ref_from_verse_text(text)
            # A verse creates the expectation of its own translation. Vol 2
            # numbers only 21 of its translation blocks, so without this the
            # other ~1,180 verses would inherit `commentary` and end up with no
            # meaning attached at all.
            last_prose_type = ElementType.translation

        elif source.type == "heading":
            if is_running_head(text, book_title):
                # Furniture, and deliberately does NOT reset role inheritance: a
                # page break must not sever a translation that continues overleaf.
                element_type = ElementType.page_furniture
            elif is_chapter_heading(text):
                element_type = ElementType.heading
                # The number, not the title: `chapter_hint` and
                # `sutra_unit.chapter` are both String(60) and real headings
                # overrun it, and a bare number joins to `chapter.number`.
                chapter_hint = chapter_number(text)
                last_prose_type = None
            elif is_notes_marker(text):
                # `Notes :` set as a heading is still a role marker.
                element_type = ElementType.commentary
                last_prose_type = ElementType.commentary
            else:
                # A section title — `Types of Dasas :`, `Characteristics of Arms
                # :`. Navigational, not a chapter boundary, and frequently printed
                # *between* a verse and its translation. Emitting it as a heading
                # would make reflow close the unit there and orphan the verse, so
                # it is dropped as furniture and leaves role inheritance intact.
                element_type = ElementType.page_furniture

        elif source.type == "english_prose":
            role = classify_prose(text)
            if role is ProseRole.continuation:
                element_type = last_prose_type or _DEFAULT_PROSE_TYPE
            else:
                element_type = _ROLE_TO_TYPE[role]
                if role is ProseRole.translation:
                    verse_no = verse_ref_from_translation(text)
            last_prose_type = element_type

        else:
            # `image` and anything unforeseen carry no rule content.
            element_type = _SOURCE_TYPE_TO_ELEMENT.get(
                source.type, ElementType.page_furniture
            )

        out.append(
            OrderedElement(
                page_no=source.page_number,
                element_id=source.id,
                element=PageElement(
                    reading_order=reading_order,
                    type=element_type,
                    script=_script_for(element_type),
                    text=text,
                    bbox=None,
                    verse_no=verse_no,
                    chapter_hint=chapter_hint,
                    continues_to_next_page=False,
                ),
            )
        )
        reading_order += 1

    return out
