"""What role a prose block plays, and which headings are merely page furniture.

The running-head test carries more weight than anything else in this package.
`reflow_book()` calls `close()` on every `ElementType.heading`, and BPHS prints a
running head on every single page. Classify those as headings and the open Sutra
Unit dies at each page boundary, orphaning every verse whose translation sits
overleaf — which manufactures precisely the failure the adjacency gate exists to
catch, at scale, while looking like a data problem rather than a code one.

Measured distribution over BPHS's 4,888 `english_prose` elements:
947 numbered (translation), 586 `Notes:` (commentary), 39 parenthetical,
3,316 unmarked (continuation). The continuation case is the majority, which is
why the adapter resolves it by inheritance rather than guessing per block.
"""

import re
from enum import StrEnum

from app.knowledge.bridge.verse_ref import verse_ref_from_translation

_NOTES_RE = re.compile(r"^\s*Notes?\s*[:.]", re.IGNORECASE)
_PAREN_RE = re.compile(r"^\s*\(")
_TOC_LINE_RE = re.compile(r"^\s*\d+\s*\.\s+\S")
_LEADING_FOLIO_RE = re.compile(r"^\s*(\d+)\s+\S")
_TRAILING_FOLIO_RE = re.compile(r"\s(\d+)\s*$")

_CHAPTER_RE = re.compile(r"(?im)^\s*(?:chapter|adhyaya)\b[-\s]*(\d+)")
"""An in-body chapter marker: `Chapter 1`, `CHAPTER-48`, `Adhyaya 3`.

Only these may close an open Sutra Unit. Measured on BPHS, treating *every*
non-furniture heading as a chapter boundary produced 148 orphaned verses in vol 1
and 1,180 in vol 2, because section titles like `Types of Dasas :` are printed
between a verse and its translation.
"""

_MAX_RUNNING_HEAD_WORDS = 8
"""A running head is a short title plus a folio. Body text that happens to end in
a number is longer than this, so the bound keeps prose out of the furniture bin.
"""


class ProseRole(StrEnum):
    translation = "translation"
    commentary = "commentary"
    continuation = "continuation"
    """Neither numbered nor marked, so it continues whatever block preceded it.
    The adapter resolves this by inheriting the previous element's role — it is
    not a role the adapter ever emits as an element type."""


def classify_prose(text: str) -> ProseRole:
    """Which part of a Sutra Unit this prose block belongs to."""
    if verse_ref_from_translation(text) is not None:
        return ProseRole.translation
    if _NOTES_RE.match(text) or _PAREN_RE.match(text):
        return ProseRole.commentary
    return ProseRole.continuation


def is_notes_marker(text: str) -> bool:
    """True for a `Notes :` line, wherever it was typeset.

    BPHS sometimes sets this as a heading rather than as body prose, and it is a
    role marker either way: everything after it is the editor's exposition, not
    Parashara's verse.
    """
    return bool(_NOTES_RE.match(text.strip()))


def chapter_number(text: str) -> str | None:
    """The chapter number a heading declares, as a string, or `None`.

    Returned rather than the heading itself because `chapter_hint` and
    `sutra_unit.chapter` are both `String(60)` and real headings overrun it —
    `CHAPTER-50 133-143\\nRESULTS OF THE DASAS OF THE LORDS OF THE HOUSES:` is 68
    characters. A bare number also makes `sutra_unit.chapter` join directly to
    `chapter.number`, which the title never could.
    """
    stripped = text.strip()
    if match := _CHAPTER_RE.search(stripped):
        return match.group(1)
    if match := _TOC_LINE_RE.match(stripped):
        leading = re.match(r"^\s*(\d+)", stripped)
        return leading.group(1) if leading else None
    return None


def is_chapter_heading(text: str) -> bool:
    """True only for a real chapter boundary — the one heading kind allowed to
    close an open Sutra Unit.

    A table-of-contents line (`14. EFFECTS OF THE 1st HOUSE 194`) also counts,
    because the TOC is where the chapter tree is read from.
    """
    stripped = text.strip()
    if not stripped:
        return False
    return bool(_CHAPTER_RE.search(stripped) or _TOC_LINE_RE.match(stripped))


def _title_words(title: str) -> set[str]:
    """Words long enough to be distinctive, lowercased."""
    return {word for word in re.findall(r"[A-Za-z]+", title.lower()) if len(word) > 3}


def is_running_head(text: str, book_title: str) -> bool:
    """True when this heading is a page's running title/folio, not a chapter.

    A running head carries a folio number and no chapter number. A table-of-
    contents line carries *both* (`14. EFFECTS OF THE 1st HOUSE 194`), so the TOC
    check runs first — otherwise every TOC line would be discarded as furniture
    and the chapter tree would come out empty.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if _TOC_LINE_RE.match(stripped):
        return False

    has_folio = bool(
        _TRAILING_FOLIO_RE.search(stripped) or _LEADING_FOLIO_RE.match(stripped)
    )
    if not has_folio:
        return False

    # Either it repeats the book's title, or it is a short title-plus-folio line
    # of the kind printed at the head of every page.
    if _title_words(book_title) & _title_words(stripped):
        return True
    return len(stripped.split()) <= _MAX_RUNNING_HEAD_WORDS
