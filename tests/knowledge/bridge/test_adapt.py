"""The adapter: POC source rows into the vocabulary reflow_book() understands."""

from rishivan.knowledge.bridge.adapt import SourceRow, adapt_rows
from rishivan.knowledge.reflow import adjacency_violations, reflow_book
from rishivan.knowledge.schemas.page import ElementType

BOOK = "Brihat Parasara Hora Shastra"


def row(id_, pg, ix, type_, content):
    return SourceRow(
        id=id_, page_number=pg, element_index=ix, type=type_, content=content
    )


def test_running_head_becomes_page_furniture():
    out = adapt_rows(
        [row(1, 205, 0, "heading", "Brihat Parasara Hora Shastra 197")],
        book_title=BOOK,
    )
    assert out[0].element.type is ElementType.page_furniture


def test_shloka_becomes_verse_with_range_ref():
    out = adapt_rows(
        [row(1, 205, 5, "shloka", "Original Content:\na ॥१२॥\nb ॥१३॥\nc ॥१४॥")],
        book_title=BOOK,
    )
    assert out[0].element.type is ElementType.verse
    assert out[0].element.verse_no == "12-14"


def test_numbered_prose_becomes_translation_with_ref():
    out = adapt_rows(
        [row(1, 205, 6, "english_prose", "12-14. Head, eyes, ears")], book_title=BOOK
    )
    assert out[0].element.type is ElementType.translation
    assert out[0].element.verse_no == "12-14"


def test_notes_prose_becomes_commentary_without_ref():
    out = adapt_rows(
        [row(1, 205, 7, "english_prose", "Notes : To consider which limb")],
        book_title=BOOK,
    )
    assert out[0].element.type is ElementType.commentary
    assert out[0].element.verse_no is None


def test_unmarked_prose_inherits_the_previous_role():
    rows = [
        row(1, 205, 6, "english_prose", "12. Head, eyes"),
        row(2, 205, 7, "english_prose", "and also the nose and temple"),
    ]
    out = adapt_rows(rows, book_title=BOOK)
    assert out[1].element.type is ElementType.translation
    # No ref, so reflow appends it instead of opening a second unit.
    assert out[1].element.verse_no is None


def test_unmarked_prose_after_notes_inherits_commentary():
    rows = [
        row(1, 205, 4, "english_prose", "Notes : As the effects are studied"),
        row(2, 206, 2, "english_prose", "basis of the Drekkanas"),
    ]
    out = adapt_rows(rows, book_title=BOOK)
    assert out[1].element.type is ElementType.commentary


def test_unmarked_prose_with_no_predecessor_is_commentary():
    out = adapt_rows(
        [row(1, 4, 1, "english_prose", "orphan front matter")], book_title=BOOK
    )
    assert out[0].element.type is ElementType.commentary


def test_role_inheritance_resets_at_a_real_heading():
    rows = [
        row(1, 205, 6, "english_prose", "12. Head, eyes"),
        row(2, 206, 0, "heading", "14. EFFECTS OF THE 1st HOUSE 194"),
        row(3, 206, 1, "english_prose", "unmarked after a real heading"),
    ]
    out = adapt_rows(rows, book_title=BOOK)
    assert out[1].element.type is ElementType.heading
    assert out[2].element.type is ElementType.commentary


def test_role_inheritance_survives_a_running_head():
    """A running head is furniture, so it must not break a translation that
    continues onto the next page."""
    rows = [
        row(1, 205, 6, "english_prose", "12. Head, eyes"),
        row(2, 206, 0, "heading", "Brihat Parasara Hora Shastra 198"),
        row(3, 206, 1, "english_prose", "and also the nose"),
    ]
    out = adapt_rows(rows, book_title=BOOK)
    assert out[2].element.type is ElementType.translation


def test_tables_and_charts_map_to_structural_types():
    rows = [
        row(1, 206, 1, "chart", "Original Content:\n# The I Drekkana"),
        row(2, 206, 2, "table", "| a | b |"),
        row(3, 206, 3, "image", "figure caption"),
    ]
    out = adapt_rows(rows, book_title=BOOK)
    assert out[0].element.type is ElementType.figure_chart
    assert out[1].element.type is ElementType.table
    assert out[2].element.type is ElementType.page_furniture


def test_ordering_is_by_page_then_index():
    rows = [
        row(2, 206, 0, "english_prose", "1. second page"),
        row(1, 205, 3, "english_prose", "2. first page"),
    ]
    out = adapt_rows(rows, book_title=BOOK)
    assert [o.element_id for o in out] == [1, 2]
    assert [o.element.reading_order for o in out] == [0, 1]


def test_continues_to_next_page_is_never_set():
    rows = [row(1, 205, 6, "english_prose", "12. Head")]
    assert adapt_rows(rows, book_title=BOOK)[0].element.continues_to_next_page is False


def test_blank_content_is_dropped():
    rows = [
        row(1, 205, 0, "english_prose", "[Heading: X 1]"),
        row(2, 205, 1, "english_prose", None),
        row(3, 205, 2, "english_prose", "12. real content"),
    ]
    out = adapt_rows(rows, book_title=BOOK)
    assert len(out) == 1
    assert out[0].element.reading_order == 0


def test_bridged_elements_carry_no_geometry():
    out = adapt_rows([row(1, 205, 5, "shloka", "a ॥१२॥")], book_title=BOOK)
    assert out[0].element.bbox is None


def test_end_to_end_verse_keeps_its_translation_across_a_page_break():
    """The failure mode the whole gate exists for."""
    rows = [
        row(1, 205, 0, "heading", "Brihat Parasara Hora Shastra 197"),
        row(2, 205, 5, "shloka", "Original Content:\nशिरो ॥१२॥\nमध्य ॥१३॥\nवस्ति ॥१४॥"),
        row(3, 206, 0, "heading", "198 Effects of The First House"),
        row(4, 206, 1, "english_prose", "12-14. Head, eyes, ears, nose"),
    ]
    units = reflow_book(adapt_rows(rows, book_title=BOOK))
    assert len(units) == 1
    assert units[0].verse_ref_local == "12-14"
    assert "Head, eyes" in units[0].translation
    assert adjacency_violations(units) == []
