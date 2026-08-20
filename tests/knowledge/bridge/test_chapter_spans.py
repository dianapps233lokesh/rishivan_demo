"""Chapter boundaries from body headings.

Every case here corresponds to a defect measured on the real corpus, where chapter
assignment was wrong for 891 of 2,063 units (43.2%).
"""

from rishivan.knowledge.bridge.chapter_spans import (
    ChapterIndex,
    detect_chapter_starts,
    devanagari_to_int,
    title_from_heading,
)


def test_devanagari_number_is_read():
    assert devanagari_to_int("५४") == 54
    assert devanagari_to_int("२६") == 26
    assert devanagari_to_int("not digits") is None


def test_both_volume_heading_formats_are_detected():
    """Vol 1 prints `Chapter 26`, vol 2 prints `Chapter - 54`. A whitespace-only
    separator missed all 53 of vol 2's chapters."""
    report = detect_chapter_starts(
        [
            (283, 2, "Chapter 26 | Effects of the Bhava Lords"),
            (400, 1, "Chapter - 54 | VIMSHOTTARI DASA SYSTEM"),
        ]
    )
    assert report.numbers() == [26, 54]


def test_prose_cross_reference_is_not_a_chapter_start():
    """"can be had from Chapter 3 Sloka 65" filed following verses under chapter 3."""
    report = detect_chapter_starts(
        [(19, 4, "More knowledge about this can be had from Chapter 3 Sloka 65")]
    )
    assert report.numbers() == []


def test_devanagari_disagreement_is_recorded_not_guessed():
    report = detect_chapter_starts([(283, 2, "Chapter 26 ॥२७॥ Effects")])
    assert report.numbers() == []
    assert report.conflicts


def test_front_matter_is_excluded():
    """The contents pages look exactly like chapter headings and produced 21 phantom
    starts hundreds of pages before the real ones."""
    report = detect_chapter_starts(
        [(6, 1, "Chapter 26 EFFECTS OF NON-LUMINOUS PLANETS 275")],
        body_starts_at=100,
    )
    assert report.numbers() == []


def test_out_of_order_heading_is_rejected():
    """Vol 2 has a mid-book listing yielding `Chapter 96` six hundred pages early. Kept,
    it made the genuine chapters 81-95 look like duplicates."""
    report = detect_chapter_starts(
        [
            (100, 1, "Chapter 80 A"),
            (473, 1, "Chapter 96 spurious"),
            (680, 1, "Chapter 81 B"),
            (700, 1, "Chapter 82 C"),
            (792, 1, "Chapter 96 D"),
        ]
    )
    assert report.numbers() == [80, 81, 82, 96]
    assert report.rejected


def test_a_single_stray_heading_cannot_outvote_the_real_sequence():
    """Greedy filtering would reject everything after an early false positive; the
    longest increasing subsequence keeps whichever set is larger."""
    headings = [(10, 1, "Chapter 99 stray")] + [
        (20 + i, 1, f"Chapter {i + 1} real") for i in range(30)
    ]
    report = detect_chapter_starts(headings)
    assert report.numbers() == list(range(1, 31))


def test_chapter_lookup_is_positional():
    report = detect_chapter_starts(
        [(283, 2, "Chapter 26 A"), (348, 2, "Chapter 27 B")]
    )
    index = ChapterIndex(report.starts)
    assert index.chapter_at(283, 5) == 26
    assert index.chapter_at(300, 0) == 26
    assert index.chapter_at(348, 5) == 27
    assert index.chapter_at(400, 0) == 27


def test_content_before_the_first_chapter_has_no_chapter():
    """Front matter has no chapter, and inventing one is how contents pages ended up
    stored as scripture."""
    index = ChapterIndex(detect_chapter_starts([(283, 2, "Chapter 26 A")]).starts)
    assert index.chapter_at(10, 0) is None


def test_a_missed_heading_costs_only_one_chapter_not_the_rest():
    """The defect being replaced: a sticky variable propagated one miss across every
    following chapter. Positionally, chapter 28 still resolves correctly even though 27
    was never detected."""
    index = ChapterIndex(
        detect_chapter_starts(
            [(100, 1, "Chapter 26 A"), (300, 1, "Chapter 28 C")]
        ).starts
    )
    assert index.chapter_at(200, 0) == 26  # chapter 27's pages fold into 26
    assert index.chapter_at(310, 0) == 28  # but 28 is unaffected


def test_title_is_taken_from_the_body_heading():
    """The printed TOC transposes vol 1's chapters 26 and 27."""
    assert (
        title_from_heading("Chapter 26 | Effects of the Bhava Lords")
        == "Effects of the Bhava Lords"
    )
    assert title_from_heading("Chapter - 54 | VIMSHOTTARI DASA SYSTEM") == (
        "VIMSHOTTARI DASA SYSTEM"
    )
    assert title_from_heading("Brihat Parasara Hora Shastra 341") is None
