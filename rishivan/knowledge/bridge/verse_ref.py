"""Read verse numbers as the book prints them.

Two delimiter conventions coexist inside BPHS and both appear in production data:
vol 1 closes a verse with `॥` (U+0965 DOUBLE DANDA), vol 2 with `।।` (U+0964
DANDA, twice, usually but not always spaced). Measured coverage with both handled
is 97.6% of vol 1's 1,065 shloka elements and 96.6% of vol 2's 1,183; handling
only the double danda leaves 671 of vol 2's elements (57%) with no readable
number, and nothing would error — the numbers would simply be counted instead of
read, and only `inferred_verse_no` would hint that anything was lost.

A single element frequently holds several verses — 2,248 shloka elements carry
3,998 verse numbers — so the reference returned here is often a range. It must be
formatted `"12-14"`, because `rishivan.knowledge.reflow.RANGE_RE` parses that form and
the printed translation block covering those verses is labelled `12-14.`. The two
references have to compare equal or reflow opens a second unit and orphans the
verse.
"""

import re

DEVANAGARI_DIGITS = {
    "०": "0",
    "१": "1",
    "२": "2",
    "३": "3",
    "४": "4",
    "५": "5",
    "६": "6",
    "७": "7",
    "८": "8",
    "९": "9",
}

_DANDA_PAIR = r"(?:॥|।\s*।)"
"""U+0965 double danda, or two U+0964 dandas with optional space between."""

VERSE_MARKER_RE = re.compile(rf"{_DANDA_PAIR}\s*([०-९]+)\s*{_DANDA_PAIR}")

_TRANSLATION_MARKER_RE = re.compile(
    r"^\s*(\d+)(?:\s*[-–—]\s*(\d+))?(?:\s*\.|\s+(?=[A-Z]))"
)
"""A leading verse label: `11.`, `12-14.`, or — as BPHS often prints it — with no
period at all: `9-12 Lord Vishnu`, `13-15 The perceptible Lord`.

Anchored, and the period-less form additionally requires the next character to be
an uppercase letter, so ordinary prose is not mistaken for a label:

* `11. Prediction of Effects`  -> matches, ref `11`
* `9-12 Lord Vishnu`           -> matches, ref `9-12`
* `12 planets are benefic`     -> no match (lowercase follows)
* `the 7th house shows`        -> no match (does not start with a digit)
* `7th house shows`            -> no match (no separator after the digit)
"""


def deva_to_int(s: str) -> int | None:
    """Devanagari numerals to an int, or `None` if `s` holds no Devanagari digit."""
    if not s:
        return None
    latin = "".join(DEVANAGARI_DIGITS.get(ch, "") for ch in s)
    return int(latin) if latin else None


def verse_numbers(text: str) -> list[int]:
    """Every verse number marked in `text`, in printed order."""
    found = (deva_to_int(match.group(1)) for match in VERSE_MARKER_RE.finditer(text))
    return [number for number in found if number is not None]


def _format_ref(numbers: list[int]) -> str | None:
    if not numbers:
        return None
    first, last = numbers[0], numbers[-1]
    return str(first) if first == last else f"{first}-{last}"


def verse_ref_from_verse_text(text: str) -> str | None:
    """The reference for a shloka element: `"12"`, or `"12-14"` for a range.

    `None` for an unmarked verse — 26 elements in vol 1 and 40 in vol 2. Reflow
    then counts from the previous verse and flags the unit `inferred_verse_no`,
    which is the honest outcome: the number was not read, and a reviewer can sort
    on that.
    """
    return _format_ref(verse_numbers(text))


def verse_ref_from_translation(text: str) -> str | None:
    """The reference from a numbered translation block's leading label."""
    match = _TRANSLATION_MARKER_RE.match(text)
    if match is None:
        return None
    first, last = match.group(1), match.group(2)
    return f"{first}-{last}" if last and last != first else first
