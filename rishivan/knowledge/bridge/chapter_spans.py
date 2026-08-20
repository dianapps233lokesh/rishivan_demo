"""Chapter boundaries taken from the body, not from the table of contents.

Chapter assignment was the pipeline's largest silent defect. `reflow.py` carried
`chapter` as a sticky variable updated only when a heading yielded a number, so one
missed heading filed every following verse under the previous chapter. Against the TOC's
own page ranges the two methods disagreed on 891 of 2,063 units (43.2%).

Neither source is trustworthy alone. The sticky value propagates one miss across a whole
chapter. The printed TOC is simply wrong in this edition: its page numbers drift 0 to 3
pages, and for vol 1 it has chapters 26 and 27 *transposed* against the body headings.

The body heading is authoritative and self-verifying — each prints its number twice,
`Chapter - 54` and `।। ५४ ।।`, the same two-readings technique used for verse numbers.
Measured: 47/47 chapters in vol 1, 52/53 in vol 2, zero disagreements between readings.
"""

import re
from bisect import bisect_right
from dataclasses import dataclass, field

from rishivan.knowledge.bridge.editions import (
    DEFAULT_PROFILE,
    EditionProfile,
    chapter_number_from,
)

DEVANAGARI_DIGITS = "०१२३४५६७८९"

CHAPTER_EN = re.compile(
    r"^\s*(?:Chapter|CHAPTER)\s*[-–—:.]?\s*(\d{1,3})\b", re.MULTILINE
)
"""BPHS's own heading form, kept for callers that predate edition profiles.

New code should go through `editions.chapter_number_from`, which handles the other three
conventions in the corpus -- `ADHYAYA 1.`, `CHAPTER VI.` and `Adhyaya 1.` -- and which
this pattern silently missed in five books.
"""

CHAPTER_DEV = re.compile(r"[।॥]{1,2}\s*([०-९]{1,3})\s*[।॥]{1,2}")
"""The chapter number as printed in the Devanagari title line, between dandas."""


def devanagari_to_int(text: str) -> int | None:
    try:
        return int("".join(str(DEVANAGARI_DIGITS.index(ch)) for ch in text))
    except ValueError:
        return None


def _title_pattern(profile: EditionProfile) -> re.Pattern | None:
    """The title group for this edition, after its own chapter word and numeral."""
    if not profile.chapter_words:
        return None
    words = "|".join(re.escape(word) for word in profile.chapter_words)
    numerals = []
    if "arabic" in profile.numerals:
        numerals.append(r"\d{1,3}(?!\d)")
    if "roman" in profile.numerals:
        numerals.append(r"[IVXLCDM]+")
    return re.compile(
        # `[ \t]` up to the numeral keeps the heading anchored to one line; `\s` after
        # it must cross newlines, because most editions print the title on the next
        # line -- `Chapter 1\nThe Creation`.
        rf"^[ \t]*(?:{words})S?[ \t]*[-–—:.]?[ \t]*(?:{'|'.join(numerals)})"
        rf"\s*[|:.\-–—()]?\s*(\S.*)$",
        re.MULTILINE | re.IGNORECASE,
    )


TITLE_AFTER_NUMBER = re.compile(
    r"^\s*(?:Chapter|CHAPTER)\s*[-–—:.]?\s*\d{1,3}(?!\d)\s*[|:.\-–—]?\s*(\S.*)$",
    re.MULTILINE,
)
r"""The chapter's own title, as the body page prints it.

`(?!\d)` is load-bearing. Without it the digit group backtracks to satisfy the
title group: `Chapter - 55` carries no title at all, but `\d{1,3}` gave up its last
digit so `(.+)` could match, yielding the title `"5"`. That silently overwrote 72 real
chapter titles with single digits.
"""

_HAS_LETTER = re.compile(r"[A-Za-z]")


def title_from_heading(
    text: str, profile: EditionProfile = DEFAULT_PROFILE
) -> str | None:
    """The title a body chapter heading declares, cleaned of separators.

    Needed because the printed TOC is unreliable: for vol 1 it lists chapter 26 as
    "EFFECTS OF NON-LUMINOUS PLANETS" while the body page reads `Chapter 26 | Effects of
    the Bhava Lords` -- the two titles are transposed in the contents. Content follows
    the body, so the title must too, or a correctly-assigned verse still cites the wrong
    chapter name.
    """
    pattern = _title_pattern(profile)
    if pattern is None:
        return None
    match = pattern.search(text or "")
    if not match:
        return None
    title = match.group(1).replace("|", " ").strip(" :.-–—()\t")
    title = re.sub(r"\s{2,}", " ", title)
    # Many body headings are bare (`Chapter - 55`). Returning something title-shaped for
    # those would replace a good TOC title with noise, so require actual words.
    if not title or not _HAS_LETTER.search(title):
        return None
    return title


@dataclass(frozen=True)
class ChapterStart:
    """Where a chapter begins, in reading order."""

    number: int
    page_no: int
    element_index: int
    devanagari_number: int | None = None
    title: str | None = None

    @property
    def position(self) -> tuple[int, int]:
        return (self.page_no, self.element_index)

    @property
    def cross_checked(self) -> bool:
        """Both readings present and in agreement."""
        return self.devanagari_number == self.number


@dataclass
class SpanReport:
    starts: list[ChapterStart]
    conflicts: list[str]
    """Headings whose English and Devanagari numbers disagree -- one is misread, and
    picking a winner silently would overwrite the book."""

    duplicates: list[str]
    """A chapter number claimed by more than one heading; the first wins and the rest
    are recorded rather than dropped."""

    rejected: list[str] = field(default_factory=list)
    """Candidates dropped for breaking chapter order -- see `_longest_increasing`."""

    def numbers(self) -> list[int]:
        return [start.number for start in self.starts]


HEADING_LIKE = frozenset({"heading", "page_furniture"})
"""Element types a chapter heading can end up as.

`page_furniture` has to be included: the adapter classifies 12 of vol 1's
chapter-opening headings as running heads, and excluding them dropped detection from
47 chapters to 31. Prose types are excluded for the opposite reason -- a commentary that
cites "Chapter 3" is not a chapter start.
"""


def detect_chapter_starts(
    headings: list[tuple[int, int, str]],
    *,
    body_starts_at: int = 0,
    profile: EditionProfile = DEFAULT_PROFILE,
) -> SpanReport:
    """Find every chapter start from body headings.

    `headings` is `(page_no, element_index, text)` in reading order, already filtered to
    heading-like elements. `body_starts_at` excludes the front-matter contents pages,
    whose lines look exactly like chapter headings -- without it, vol 2's TOC produced
    21 phantom starts hundreds of pages before the real ones.

    `profile` is the book's `EditionProfile`. A book whose profile declares no chapter
    words yields no starts, which is the honest answer for Deva Keralam and Vivaha
    Patalam: inventing a chapter 1 would fabricate every citation in the book.
    """
    candidates: list[ChapterStart] = []
    conflicts: list[str] = []
    duplicates: list[str] = []

    for page_no, element_index, text in headings:
        if page_no < body_starts_at:
            continue
        number = chapter_number_from(text or "", profile)
        if number is None:
            continue
        devanagari = None
        if found := CHAPTER_DEV.search(text or ""):
            devanagari = devanagari_to_int(found.group(1))
        if devanagari is not None and devanagari != number:
            conflicts.append(
                f"p{page_no}: heading reads Chapter {number} but Devanagari says "
                f"{devanagari}"
            )
            continue
        # Every candidate is kept, duplicates included. Deduplicating to the first
        # occurrence here was wrong: vol 2 has a mid-book listing that produces a
        # `Chapter 96` at page 473, and taking the first meant the bogus one won while
        # the genuine chapters 90-96 were discarded as repeats. `_longest_increasing`
        # settles it instead, and it cannot keep two candidates with the same number
        # because it requires strictly increasing numbers.
        candidates.append(
            ChapterStart(
                number,
                page_no,
                element_index,
                devanagari,
                title_from_heading(text, profile),
            )
        )

    seen: set[int] = set()
    for candidate in candidates:
        if candidate.number in seen:
            duplicates.append(
                f"chapter {candidate.number} also appears on p{candidate.page_no}"
            )
        seen.add(candidate.number)

    ordered = sorted(candidates, key=lambda start: start.position)
    kept, rejected = _longest_increasing(ordered)
    return SpanReport(
        starts=kept,
        conflicts=conflicts,
        duplicates=duplicates,
        rejected=rejected,
    )


def _longest_increasing(
    candidates: list[ChapterStart],
) -> tuple[list[ChapterStart], list[str]]:
    """Keep the largest subset whose numbers increase with position.

    Chapters appear in order, so a number going backwards is a false positive rather than
    evidence the book is out of order. Vol 2 has a mid-book listing yielding a `Chapter 96`
    heading six hundred pages early, which made the genuine chapters 81-95 look like
    out-of-order duplicates.

    Greedy filtering would be wrong in exactly that case — the bogus 96 comes first, so it
    would reject every real chapter after it. The longest increasing subsequence keeps the
    larger set, which is always the real one: a stray heading cannot outnumber fifty.
    """
    if not candidates:
        return [], []
    # tails[i] = index into `candidates` of the smallest tail of an increasing
    # subsequence of length i+1; predecessor[] reconstructs the chosen chain.
    tails: list[int] = []
    predecessor: list[int | None] = [None] * len(candidates)
    for index, candidate in enumerate(candidates):
        low, high = 0, len(tails)
        while low < high:
            middle = (low + high) // 2
            if candidates[tails[middle]].number < candidate.number:
                low = middle + 1
            else:
                high = middle
        predecessor[index] = tails[low - 1] if low else None
        if low == len(tails):
            tails.append(index)
        else:
            tails[low] = index

    chain: list[int] = []
    cursor: int | None = tails[-1] if tails else None
    while cursor is not None:
        chain.append(cursor)
        cursor = predecessor[cursor]
    chain.reverse()

    keep = set(chain)
    kept = [candidates[i] for i in chain]
    rejected = [
        f"chapter {candidates[i].number} at p{candidates[i].page_no} breaks chapter "
        f"order"
        for i in range(len(candidates))
        if i not in keep
    ]
    return kept, rejected


class ChapterIndex:
    """Maps a position in reading order to the chapter containing it."""

    def __init__(self, starts: list[ChapterStart]) -> None:
        self._starts = sorted(starts, key=lambda start: start.position)
        self._positions = [start.position for start in self._starts]

    def __len__(self) -> int:
        return len(self._starts)

    def chapter_at(self, page_no: int, element_index: int) -> int | None:
        """The chapter containing this position, or None if it precedes chapter 1.

        Positional rather than sticky: a missed heading now costs only the chapters
        between two detected ones, instead of silently absorbing everything after it.
        Content before the first detected heading returns None -- front matter has no
        chapter, and inventing one is how the contents pages ended up cited as
        scripture.
        """
        index = bisect_right(self._positions, (page_no, element_index)) - 1
        if index < 0:
            return None
        return self._starts[index].number
