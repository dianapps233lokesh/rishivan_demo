"""Prose roles, and the running-head test that protects the adjacency gate."""

from app.knowledge.bridge.roles import (
    ProseRole,
    chapter_number,
    classify_prose,
    is_running_head,
)

BOOK = "Brihat Parasara Hora Shastra"


def test_numbered_block_is_translation():
    assert (
        classify_prose("11. Prediction of Effects should be made")
        is ProseRole.translation
    )
    assert classify_prose("12-14. Head, eyes, ears, nose") is ProseRole.translation


def test_notes_block_is_commentary():
    assert (
        classify_prose("Notes: The Sun and the Moon falling together")
        is ProseRole.commentary
    )
    assert classify_prose("Note : As the effects are studied") is ProseRole.commentary
    assert classify_prose("NOTES. Something") is ProseRole.commentary


def test_parenthetical_is_commentary():
    assert (
        classify_prose("(i.e. taking the Moon as the Ascendant)")
        is ProseRole.commentary
    )


def test_unmarked_is_continuation():
    assert (
        classify_prose("basis of the Drekkanas or Decanates") is ProseRole.continuation
    )
    assert (
        classify_prose("in the sign show the right side of the neck")
        is ProseRole.continuation
    )


def test_running_head_with_trailing_folio():
    assert is_running_head("Brihat Parasara Hora Shastra 197", BOOK) is True


def test_running_head_with_leading_folio():
    assert is_running_head("198 Effects of The First House", BOOK) is True


def test_toc_style_chapter_title_is_not_a_running_head():
    # A TOC line carries a chapter number AND a page number. Misclassifying it as
    # furniture would empty the chapter tree.
    assert is_running_head("14. EFFECTS OF THE 1st HOUSE 194", BOOK) is False


def test_bare_chapter_title_is_not_a_running_head():
    assert is_running_head("EFFECTS OF THE FIRST HOUSE", BOOK) is False


def test_blank_heading_is_not_a_running_head():
    assert is_running_head("", BOOK) is False
    assert is_running_head("   ", BOOK) is False


def test_chapter_number_extracted_not_the_title():
    """chapter_hint and sutra_unit.chapter are String(60); real headings overrun
    it, and a bare number joins to chapter.number."""
    assert chapter_number("Chapter 3\nPlanetary Characters And Description") == "3"
    assert (
        chapter_number(
            "CHAPTER-50 133-143\nRESULTS OF THE DASAS OF THE LORDS OF THE HOUSES:"
        )
        == "50"
    )
    assert chapter_number("14. EFFECTS OF THE 1st HOUSE 194") == "14"
    assert chapter_number("Adhyaya 7") == "7"


def test_chapter_number_none_for_a_non_chapter_heading():
    assert chapter_number("Characteristics of Arms :") is None
    assert chapter_number("") is None
