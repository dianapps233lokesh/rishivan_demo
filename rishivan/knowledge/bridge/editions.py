"""How each edition prints its chapters. One profile per book, three fields each.

Segmentation is the only genuinely book-specific part of the pipeline: the fact
vocabulary, the atom schema, the validator, the prompt and the accounting all work
unchanged on any book. So the variation belongs in data, not in code.

The BPHS-tuned detector hardcoded `Chapter|CHAPTER` with Arabic digits and found **zero**
chapters in Phaladeepika, Brihat Jataka, Jataka Parijata, Prasna Marga and Dharma Sindhu.
Measured across the corpus, four conventions account for every book that has chapters:

    Chapter 26              BPHS vol 1, Saravali, Muhurta Chintamani, numerology
    CHAPTER-48 1-110        BPHS vol 2, Sarvartha Chintamani (also `CHAPTER—2`)
    ADHYAYA 1.              Phaladeepika, Jataka Parijata
    CHAPTER VI.             Brihat Jataka, Prasna Marga, Prashna Tantra, Hindu Predictive

Four books have no numbered chapters at all and say so with `chapter_words=()`, which is
honest: Deva Keralam prints "BOOK I", Vivaha Patalam is unsegmented Devanagari. Filing
their verses under an invented chapter 1 would be a fabricated citation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_ROMAN_TOKEN = re.compile(r"^[IVXLCDM]+$")
MAX_CHAPTER = 120
"""No edition here runs past 100 chapters (BPHS vol 2's own front matter says "100
Chapters."), so a larger reading is a misparse rather than a chapter."""


def roman_to_int(text: str) -> int | None:
    """Roman numeral to int, or None if `text` is not one.

    Rejects anything that is not purely numeral letters, so ordinary words are not read
    as numbers -- `IN`, `INDEX` and `MIX` all begin with valid numeral letters, and
    `CHAPTER INDEX` must not become chapter 1.
    """
    token = (text or "").strip().upper()
    if not token or not _ROMAN_TOKEN.match(token):
        return None
    total = 0
    previous = 0
    for char in reversed(token):
        value = _ROMAN_VALUES[char]
        total += -value if value < previous else value
        previous = max(previous, value)
    # Canonical round-trip: rejects II​II, VX and other letter soup that happens to
    # contain only numeral characters.
    return total if total and _int_to_roman(total) == token else None


def _int_to_roman(number: int) -> str:
    pairs = (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
        (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    )
    out = []
    for value, glyph in pairs:
        while number >= value:
            out.append(glyph)
            number -= value
    return "".join(out)


@dataclass(frozen=True)
class EditionProfile:
    """How one edition prints a chapter heading."""

    title: str = ""
    """The work's own title. `Book.title` is what a citation prints, and derived from the
    slug it reads "Bphs Gcsharma Vol1" -- a filename, not a book."""
    chapter_words: tuple[str, ...] = ("chapter",)
    """Words that introduce a chapter, matched case-insensitively. Empty means this book
    has no numbered chapters."""
    numerals: tuple[str, ...] = ("arabic", "roman")
    """Which numeral systems to accept. Narrow where the edition is consistent: Brihat
    Jataka is Roman throughout, so reading `CHAPTER 6` there would be a contents line."""
    notes: str = ""

    def pattern(self) -> re.Pattern | None:
        """The anchored heading pattern for this edition, or None if it has no chapters.

        Anchored to the start of a line because unanchored it matches prose
        cross-references -- "can be had from Chapter 3 Sloka 65" filed every verse that
        followed under chapter 3.

        The separator class matters as much: vol 1 prints `Chapter 26`, vol 2
        `CHAPTER-48`, Sarvartha Chintamani `CHAPTER—2` with an em dash. Requiring
        whitespace missed all 53 of vol 2's chapters.
        """
        if not self.chapter_words:
            return None
        words = "|".join(re.escape(word) for word in self.chapter_words)
        groups = []
        if "arabic" in self.numerals:
            groups.append(r"(?P<arabic>\d{1,3})")
        if "roman" in self.numerals:
            groups.append(r"(?P<roman>[IVXLCDM]+)")
        return re.compile(
            rf"^[ \t]*(?:{words})S?[ \t]*[-–—:.]?[ \t]*(?:{'|'.join(groups)})\b",
            re.MULTILINE | re.IGNORECASE,
        )


def chapter_number_from(heading: str, profile: EditionProfile) -> int | None:
    """The chapter number a heading declares, or None.

    None covers three different cases on purpose -- the book has no chapters, the text is
    contents-page furniture, or the number is implausible. All three mean "do not open a
    chapter here", and distinguishing them would only tempt a caller to guess.
    """
    pattern = profile.pattern()
    if pattern is None or not heading:
        return None
    for match in pattern.finditer(heading):
        arabic = match.groupdict().get("arabic")
        roman = match.groupdict().get("roman")
        if arabic:
            number = int(arabic)
        elif roman:
            # Case-insensitive matching lets a lowercase word through, so re-check that
            # the numeral itself is upper case: "Chapters i to xvi" is front matter.
            number = roman_to_int(roman) if roman.isupper() else None
        else:
            number = None
        if number and 1 <= number <= MAX_CHAPTER:
            return number
    return None


_ARABIC = ("arabic",)
_ROMAN = ("roman",)

PROFILES: dict[str, EditionProfile] = {
    # ── "Chapter 26" / "CHAPTER-48", Arabic ──────────────────────────────────
    "bphs-gcsharma-vol1": EditionProfile(
        title="Brihat Parasara Hora Shastra, Volume 1",
        numerals=_ARABIC,
    ),
    "bphs-gcsharma-vol2": EditionProfile(
        title="Brihat Parasara Hora Shastra, Volume 2",
        numerals=_ARABIC,
        notes="`CHAPTER-48 1-110` — the trailing range is the verse span, not a number.",
    ),
    "saravali-santhanam-en": EditionProfile(
        title="Saravali",
        numerals=_ARABIC,
        notes="Contents lines read `Chapter 2 19`, where 19 is a page. The number is "
        "read from the word, so the page number is ignored.",
    ),
    "muhurtachintamani": EditionProfile(
        title="Muhurta Chintamani",
        numerals=_ARABIC,
    ),
    "sarvartha-chintamani": EditionProfile(
        title="Sarvartha Chintamani",
        numerals=_ARABIC,
        notes="Prints `CHAPTER-1` and `CHAPTER—2` — hyphen and em dash in one book. "
        "Some headings also carry the Devanagari title above the English.",
    ),
    "the-complete-book-of-numerology": EditionProfile(
        title="The Complete Book of Numerology",
        numerals=_ARABIC,
    ),
    "numerology-key-to-your-inner-self": EditionProfile(
        title="Numerology: Key to Your Inner Self",
        numerals=_ARABIC,
        notes="Also prints `Part I` above chapters; parts are not chapters here.",
    ),
    # ── "ADHYAYA 1.", Arabic ─────────────────────────────────────────────────
    "phaladeepika-sastri-1950": EditionProfile(
        title="Phaladeepika",
        chapter_words=("adhyaya",), numerals=_ARABIC,
        notes="Front matter says `(ADHYAYAS I—XXVIII)` in Roman; the body is Arabic, so "
        "the profile is Arabic-only and the front matter is ignored.",
    ),
    "jatakaparijata-sastri-vol1": EditionProfile(
        title="Jataka Parijata, Volume 1",
        chapter_words=("adhyaya",), numerals=_ARABIC
    ),
    "jatakaparijata-sastri-vol2": EditionProfile(
        title="Jataka Parijata, Volume 2",
        chapter_words=("adhyaya",), numerals=_ARABIC,
        notes="Volume 2 continues the numbering from volume 1 (starts at Adhyaya 10).",
    ),
    # ── "CHAPTER VI.", Roman ─────────────────────────────────────────────────
    "brihatjataka-row-1919": EditionProfile(
        title="Brihat Jataka",
        numerals=_ROMAN,
    ),
    "prasnamarga-raman-part1": EditionProfile(
        title="Prasna Marga, Part 1",
        numerals=_ROMAN,
        notes="`PART I` and `[Chapters I to XVI]` are front matter, not chapters.",
    ),
    "prasnamarga-raman-part2": EditionProfile(
        title="Prasna Marga, Part 2",
        numerals=_ROMAN,
        notes="Continues from part 1 at CHAPTER XVII; titles are parenthesised, as in "
        "`CHAPTER XVII (Vivaha Prasna)`.",
    ),
    "prashna-tantra": EditionProfile(
        title="Prashna Tantra",
        numerals=_ROMAN,
        notes="Two styles in one book: `CHAPTER I` in the body and "
        "`Chapter III : On Special Questions` in the contents.",
    ),
    "hindupredictiveastrology-raman": EditionProfile(
        title="Hindu Predictive Astrology",
        numerals=_ROMAN,
    ),
    "cheiros-book-of-numbers": EditionProfile(
        title="Cheiro's Book of Numbers",
        numerals=_ROMAN,
        notes="`CHAPTER PAGE` contents furniture carries no numeral, so it is rejected.",
    ),
    # ── Mixed numerals in one book ───────────────────────────────────────────
    "bhavartha-ratnakara-by-b-v-raman-text": EditionProfile(
        title="Bhavartha Ratnakara",
        notes="Prints `CHAPTER 1.` for the first chapter and Roman (`CHAPTER II`, "
        "`CHAPTER III`) thereafter, so both systems are accepted.",
    ),
    "numerology-and-the-divine-triangle": EditionProfile(
        title="Numerology and the Divine Triangle",
        notes="Headings are topic names ('The Life Lesson Number'), not numbered "
        "chapters. Both numeral systems are allowed in case any chapter is numbered.",
    ),
    # ── No numbered chapters ─────────────────────────────────────────────────
    "devakeralam-chandrakalanadi-vol1": EditionProfile(
        title="Deva Keralam (Chandra Kala Nadi), Volume 1",
        chapter_words=(),
        notes="Prints `BOOK I (Containing 2718 Slokas)` and no chapters. Nadi texts run "
        "as continuous sloka sequences, so verse numbering is the only structure.",
    ),
    "devakeralam-chandrakalanadi-vol2": EditionProfile(
        title="Deva Keralam (Chandra Kala Nadi), Volume 2",
        chapter_words=(), notes="As volume 1: `BOOK II`, no chapters.",
    ),
    "dharma-sindhu": EditionProfile(
        title="Dharma Sindhu",
        chapter_words=(),
        notes="No chapter headings in the OCR at all. Also the lowest conditional "
        "density measured in the corpus (1.0%), so nearly all of it is destination B.",
    ),
    "vivaha-patalam": EditionProfile(
        title="Vivaha Patalam",
        chapter_words=(),
        notes="Entirely Devanagari with no Latin headings and no numbered divisions; "
        "383 shlokas and zero english_prose elements.",
    ),
    "laghu-parashari": EditionProfile(
        title="Laghu Parashari (Jataka Chandrika)",
        chapter_words=(),
        notes="Sections are NAMED, not numbered: `संज्ञाध्यायः Preliminaries`, "
        "`योगाध्यायः Combinations of Planets`. Detecting those needs a named-section "
        "rule this profile does not model, so the book stays unsegmented for now.",
    ),
}
"""Slug -> profile. Every ingested book has an entry, including the five that have no
chapters, because an absent entry silently means "the permissive default" and that would
read `BOOK I` as chapter 1."""

DEFAULT_PROFILE = EditionProfile()
"""Permissive: both chapter words unknown books usually use, both numeral systems. A new
book is detectable before anyone writes its profile, and narrowing is an improvement
rather than a prerequisite."""


def profile_for(slug: str | None) -> EditionProfile:
    """The profile for a book slug, or the permissive default."""
    if not slug:
        return DEFAULT_PROFILE
    return PROFILES.get(slug.lower().strip(), DEFAULT_PROFILE)
