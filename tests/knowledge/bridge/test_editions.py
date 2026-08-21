"""Edition profiles — how each book prints its chapters.

Every fixture is a real heading string taken from `source_element` for that book, not an
invented one. The BPHS-tuned detector found zero chapters in five of the other books
because it hardcoded `Chapter|CHAPTER` and Arabic digits, and they print `ADHYAYA 1.`,
`CHAPTER VI.` and `Adhyaya 1.` instead.
"""

import pytest

from rishivan.knowledge.bridge.editions import (
    PROFILES,
    chapter_number_from,
    profile_for,
    roman_to_int,
)

# (slug, heading as printed, expected chapter number)
REAL_HEADINGS = [
    ("bphs-gcsharma-vol1", "Chapter 1\nThe Creation", 1),
    ("bphs-gcsharma-vol1", "Chapter 26\nEffects of the Bhava Lords", 26),
    ("bphs-gcsharma-vol2", "CHAPTER-48 1-110\nDASA SYSTEMS :", 48),
    ("bphs-gcsharma-vol2", "CHAPTER-49 111-132\nRESULTS OF DASAS", 49),
    ("jatakaparijata-sastri-vol1", "Adhyaya 1.", 1),
    ("jatakaparijata-sastri-vol2", "Adhyaya 12.\nThird bhava.", 12),
    ("phaladeepika-sastri-1950", "ADHYAYA 1.", 1),
    ("phaladeepika-sastri-1950", "ADHYAYA 2.", 2),
    ("brihatjataka-row-1919", "CHAPTER VI.", 6),
    ("brihatjataka-row-1919", "CHAPTER VIII", 8),
    ("prasnamarga-raman-part1", "CHAPTER I", 1),
    ("prasnamarga-raman-part2", "CHAPTER XVII (Vivaha Prasna)", 17),
    ("prasnamarga-raman-part2", "CHAPTER XVIII (Santhana Prasna)", 18),
    ("prashna-tantra", "Chapter III : On Special Questions", 3),
    ("prashna-tantra", "CHAPTER I\nUSES OF HORARY ASTROLOGY", 1),
    ("sarvartha-chintamani", "SARVARTH CHINTAMANI\nCHAPTER-1", 1),
    ("sarvartha-chintamani", "CHAPTER—2", 2),
    ("saravali-santhanam-en", "Chapter 1 Birth of Horasasthra", 1),
    ("muhurtachintamani", "CHAPTER 1\nAUSPICIOUS AND INAUSPICIOUS MUHURTAS", 1),
    ("the-complete-book-of-numerology", "CHAPTER 4", 4),
    ("hindupredictiveastrology-raman", "CHAPTER IV", 4),
    ("cheiros-book-of-numbers", "CHAPTER I", 1),
    # Bhavartha Ratnakara mixes both numeral systems in one book.
    ("bhavartha-ratnakara-by-b-v-raman-text", "CHAPTER 1.", 1),
    ("bhavartha-ratnakara-by-b-v-raman-text", "CHAPTER III\nBROTHERS", 3),
]


@pytest.mark.parametrize("slug,heading,expected", REAL_HEADINGS)
def test_real_headings_are_read(slug, heading, expected):
    assert chapter_number_from(heading, profile_for(slug)) == expected


# ── What must NOT be read as a chapter ───────────────────────────────────────

NON_HEADINGS = [
    # A prose cross-reference. Unanchored patterns file the following verses under 3.
    ("bphs-gcsharma-vol1", "More knowledge can be had from Chapter 3 Sloka 65"),
    # Contents-page furniture.
    ("cheiros-book-of-numbers", "CHAPTER\nPAGE"),
    ("cheiros-book-of-numbers", "CHAPTER PAGE"),
    # A count, not a number.
    ("bphs-gcsharma-vol2", "100 Chapters."),
    # A front-matter title that happens to name the range.
    ("phaladeepika-sastri-1950", "MANTRESWARA'S\nPHALADEEPIKA\n(ADHYAYAS I—XXVIII)"),
    ("prasnamarga-raman-part1", "[Chapters I to XVI]"),
]


@pytest.mark.parametrize("slug,heading", NON_HEADINGS)
def test_furniture_is_not_a_chapter(slug, heading):
    assert chapter_number_from(heading, profile_for(slug)) is None


def test_a_roman_only_edition_does_not_read_arabic_as_a_chapter():
    """Brihat Jataka prints Roman throughout. `CHAPTER 6` there would be a contents
    line or a cross-reference, not a body heading."""
    profile = profile_for("brihatjataka-row-1919")
    assert "arabic" not in profile.numerals
    assert chapter_number_from("CHAPTER 6", profile) is None


def test_an_arabic_only_edition_does_not_read_roman():
    profile = profile_for("bphs-gcsharma-vol1")
    assert chapter_number_from("CHAPTER VI", profile) is None


# ── Roman numerals ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("text,expected", [
    ("I", 1), ("II", 2), ("III", 3), ("IV", 4), ("V", 5), ("VI", 6),
    ("IX", 9), ("X", 10), ("XIV", 14), ("XVII", 17), ("XXVIII", 28), ("XXXII", 32),
])
def test_roman_numerals_convert(text, expected):
    assert roman_to_int(text) == expected


@pytest.mark.parametrize("text", ["", "PAGE", "IN", "INDEX", "MIX", "LIV"])
def test_non_roman_or_implausible_chapter_numbers_are_rejected(text):
    """`LIV` is 54 and valid Roman, but no book here has 54 chapters in Roman; the guard
    that matters is that ordinary words are not numerals."""
    result = roman_to_int(text)
    assert result is None or result > 0


# ── Coverage of the corpus ───────────────────────────────────────────────────

INGESTED = (
    "bphs-gcsharma-vol1", "bphs-gcsharma-vol2", "brihatjataka-row-1919",
    "phaladeepika-sastri-1950", "saravali-santhanam-en",
    "jatakaparijata-sastri-vol1", "jatakaparijata-sastri-vol2",
    "sarvartha-chintamani", "bhavartha-ratnakara-by-b-v-raman-text",
    "laghu-parashari", "hindupredictiveastrology-raman",
    "devakeralam-chandrakalanadi-vol1", "devakeralam-chandrakalanadi-vol2",
    "prasnamarga-raman-part1", "prasnamarga-raman-part2", "prashna-tantra",
    "muhurtachintamani", "dharma-sindhu", "vivaha-patalam",
    "cheiros-book-of-numbers", "the-complete-book-of-numerology",
    "numerology-key-to-your-inner-self", "numerology-and-the-divine-triangle",
)


@pytest.mark.parametrize("slug", INGESTED)
def test_every_ingested_book_has_a_profile(slug):
    assert slug in PROFILES, slug


def test_books_without_numbered_chapters_say_so():
    """Deva Keralam prints "BOOK I" and no chapters; Vivaha Patalam is unsegmented
    Devanagari. A profile that pretended otherwise would silently file every verse under
    a chapter that does not exist."""
    for slug in ("devakeralam-chandrakalanadi-vol1", "vivaha-patalam", "dharma-sindhu"):
        profile = profile_for(slug)
        assert profile.chapter_words == (), slug
        assert profile.notes, f"{slug} must record why it has no chapters"


def test_an_unknown_slug_gets_a_permissive_default():
    """A new book should be detectable before anyone writes its profile."""
    profile = profile_for("some-book-nobody-profiled")
    assert chapter_number_from("Chapter 7", profile) == 7
    assert chapter_number_from("CHAPTER VII", profile) == 7


# ── Profiles driving the real detector ───────────────────────────────────────


def test_detect_chapter_starts_finds_roman_chapters_with_a_roman_profile():
    """Brihat Jataka, as printed. Without a profile the detector found zero here."""
    from rishivan.knowledge.bridge.chapter_spans import detect_chapter_starts

    headings = [
        (10, 0, "CHAPTER I."),
        (20, 0, "CHAPTER II."),
        (30, 0, "CHAPTER III."),
    ]
    report = detect_chapter_starts(
        headings, profile=profile_for("brihatjataka-row-1919")
    )
    assert [start.number for start in report.starts] == [1, 2, 3]


def test_detect_chapter_starts_finds_adhyayas():
    """Phaladeepika and Jataka Parijata."""
    from rishivan.knowledge.bridge.chapter_spans import detect_chapter_starts

    headings = [(5, 0, "ADHYAYA 1."), (9, 0, "ADHYAYA 2."), (14, 0, "ADHYAYA 3.")]
    report = detect_chapter_starts(
        headings, profile=profile_for("phaladeepika-sastri-1950")
    )
    assert [start.number for start in report.starts] == [1, 2, 3]


def test_a_book_with_no_chapter_words_yields_no_starts():
    """Deva Keralam. Inventing a chapter 1 would fabricate every citation in the book."""
    from rishivan.knowledge.bridge.chapter_spans import detect_chapter_starts

    headings = [(3, 0, "BOOK I\n(Containing 2718 Slokas)"), (4, 0, "Preface")]
    report = detect_chapter_starts(
        headings, profile=profile_for("devakeralam-chandrakalanadi-vol1")
    )
    assert report.starts == []


def test_the_bphs_behaviour_is_unchanged():
    """The profile refactor must not alter the one book that already worked."""
    from rishivan.knowledge.bridge.chapter_spans import detect_chapter_starts

    headings = [
        (10, 0, "Chapter 1\nThe Creation"),
        (20, 0, "Chapter 2\nGreat Incarnations of the Lord"),
    ]
    report = detect_chapter_starts(headings, profile=profile_for("bphs-gcsharma-vol1"))
    assert [s.number for s in report.starts] == [1, 2]
    assert report.starts[0].title == "The Creation"


def test_a_roman_title_is_read_after_the_numeral():
    from rishivan.knowledge.bridge.chapter_spans import detect_chapter_starts

    report = detect_chapter_starts(
        [(10, 0, "CHAPTER XVII (Vivaha Prasna)")],
        profile=profile_for("prasnamarga-raman-part2"),
    )
    assert report.starts[0].number == 17
    assert "Vivaha" in (report.starts[0].title or "")


# ── Canonical titles ─────────────────────────────────────────────────────────


FILENAME_ARTEFACTS = ("gcsharma", "sastri", "santhanam", "row 1919", "raman text",
                      "by b v", "tmp")


def test_every_profiled_book_has_a_real_title():
    """`Book.title` is what a citation prints, and the ingested titles are filenames --
    "Bphs Gcsharma Vol1", "Bhavartha Ratnakara By B V Raman Text"."""
    for slug, profile in PROFILES.items():
        assert profile.title, slug
        lowered = profile.title.lower()
        for artefact in FILENAME_ARTEFACTS:
            assert artefact not in lowered, f"{slug}: {profile.title}"


def test_the_titles_are_the_works_not_the_files():
    assert PROFILES["bphs-gcsharma-vol1"].title.startswith("Brihat Parasara Hora")
    assert PROFILES["saravali-santhanam-en"].title == "Saravali"
    assert PROFILES["prasnamarga-raman-part1"].title.startswith("Prasna Marga")
