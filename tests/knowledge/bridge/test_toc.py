"""The chapter tree, read from BPHS's own printed table of contents."""

from app.knowledge.bridge.adapt import SourceRow
from app.knowledge.bridge.toc import (
    build_chapter_tree,
    derive_page_offset,
    gate_reason,
    parse_toc,
)

BOOK = "Brihat Parasara Hora Shastra"


def row(id_, pg, ix, type_, content):
    return SourceRow(
        id=id_, page_number=pg, element_index=ix, type=type_, content=content
    )


TOC_ROWS = [
    row(1, 3, 0, "heading", "1. THE CREATION 1"),
    row(2, 3, 1, "heading", "2. GREAT INCARNATIONS OF THE LORD 9"),
    row(3, 3, 2, "heading", "14. EFFECTS OF THE 1st HOUSE 194"),
    row(4, 3, 3, "heading", "15. EFFECTS OF THE 2nd HOUSE 201"),
]

RUNNING_HEADS = [
    row(10, 205, 0, "heading", "Brihat Parasara Hora Shastra 197"),
    row(11, 206, 0, "heading", "198 Effects of The First House"),
    row(12, 207, 0, "heading", "Brihat Parasara Hora Shastra 199"),
]


def test_parse_toc_reads_number_title_and_printed_page():
    entries = parse_toc(TOC_ROWS)
    assert [e.number for e in entries] == [1, 2, 14, 15]
    assert entries[0].title == "THE CREATION"
    assert entries[0].printed_page == 1
    assert entries[2].printed_page == 194


def test_parse_toc_ignores_running_heads():
    assert len(parse_toc(TOC_ROWS + RUNNING_HEADS)) == 4


def test_parse_toc_sorts_by_chapter_number():
    shuffled = [TOC_ROWS[2], TOC_ROWS[0], TOC_ROWS[3], TOC_ROWS[1]]
    assert [e.number for e in parse_toc(shuffled)] == [1, 2, 14, 15]


def test_derive_page_offset_uses_the_modal_running_head():
    noisy = RUNNING_HEADS + [
        row(13, 400, 0, "heading", "Brihat Parasara Hora Shastra 1"),  # noise
    ]
    assert derive_page_offset(noisy, book_title=BOOK) == 8


def test_derive_page_offset_none_without_running_heads():
    assert derive_page_offset(TOC_ROWS, book_title=BOOK) is None


def test_gate_reason_flags_non_rule_bearing_chapters():
    assert gate_reason("THE CREATION") == "cosmology"
    assert gate_reason("GREAT INCARNATIONS OF THE LORD") == "devotional"
    assert gate_reason("TO FIND OUT PLANETARY POSITION") == "calculation method"
    assert gate_reason("CONTENTS") == "front matter"


def test_gate_reason_none_for_predictive_chapters():
    assert gate_reason("EFFECTS OF THE 1st HOUSE") is None
    assert gate_reason("EFFECTS OF MARRIAGE") is None


def test_build_chapter_tree_spans_and_gating():
    tree = build_chapter_tree(
        TOC_ROWS + RUNNING_HEADS, book_title=BOOK, total_pdf_pages=657
    )
    assert [c.number for c in tree] == [1, 2, 14, 15]

    creation = tree[0]
    assert creation.printed_page_from == 1
    assert creation.printed_page_to == 8  # up to the next chapter's start
    assert creation.pdf_page_from == 9  # printed 1 + offset 8
    assert creation.is_rule_bearing is False
    assert creation.gating_reason == "cosmology"

    first_house = tree[2]
    assert first_house.is_rule_bearing is True
    assert first_house.printed_page_to == 200

    last = tree[-1]
    assert last.printed_page_to is None  # nothing follows it in the TOC
    assert last.pdf_page_to == 657  # so it runs to the end of the scan


def test_build_chapter_tree_without_offset_leaves_pdf_pages_none():
    tree = build_chapter_tree(TOC_ROWS, book_title=BOOK, total_pdf_pages=657)
    assert all(c.pdf_page_from is None for c in tree)
    assert all(c.pdf_page_to is None for c in tree)
    assert all(c.printed_page_from is not None for c in tree)


def test_build_chapter_tree_empty_when_no_toc():
    assert build_chapter_tree(RUNNING_HEADS, book_title=BOOK, total_pdf_pages=657) == []


VOL2_TOC_ROWS = [
    row(20, 7, 2, "heading", "CHAPTER-48 1-110\nDASA SYSTEMS :"),
    row(21, 7, 4, "heading", "CHAPTER-49 111-132\nRESULTS OF DASAS"),
    row(22, 8, 2, "heading", "CHAPTER-52 158-177\nRESULTS OF CHARA DASAS :"),
]


def test_parse_toc_reads_vol2_chapter_form():
    """Vol 2 prints `CHAPTER-48 1-110` with the title on the next line, and states
    the page range outright rather than leaving the end to be inferred."""
    entries = parse_toc(VOL2_TOC_ROWS)
    assert [e.number for e in entries] == [48, 49, 52]
    assert entries[0].title == "DASA SYSTEMS"
    assert entries[0].printed_page == 1
    assert entries[0].printed_page_to == 110
    assert entries[1].title == "RESULTS OF DASAS"


def test_vol1_form_has_no_explicit_page_end():
    assert parse_toc(TOC_ROWS)[0].printed_page_to is None


def test_stated_range_beats_the_inferred_one():
    """Chapter 49 states 111-132; the next TOC entry starts at 158, so inferring
    would wrongly stretch it to 157."""
    tree = build_chapter_tree(VOL2_TOC_ROWS, book_title=BOOK, total_pdf_pages=818)
    chapter_49 = next(c for c in tree if c.number == 49)
    assert chapter_49.printed_page_to == 132


def test_both_toc_forms_can_coexist():
    tree = build_chapter_tree(
        TOC_ROWS + VOL2_TOC_ROWS, book_title=BOOK, total_pdf_pages=818
    )
    assert [c.number for c in tree] == [1, 2, 14, 15, 48, 49, 52]


def test_pdf_page_end_is_clamped_to_the_scan():
    """A stated range can overrun the scan; the book cannot have more pages than
    were scanned."""
    rows = VOL2_TOC_ROWS + RUNNING_HEADS
    tree = build_chapter_tree(rows, book_title=BOOK, total_pdf_pages=120)
    assert all(c.pdf_page_to <= 120 for c in tree if c.pdf_page_to is not None)


def test_repeated_toc_entries_are_deduplicated():
    """Vol 2's contents pages appear twice in the scan, so chapters parse twice
    with identical titles and ranges. Left in, they violate
    uq_chapter_book_number at persist time."""
    doubled = VOL2_TOC_ROWS + [
        row(30, 90, 2, "heading", "CHAPTER-48 1-110\nDASA SYSTEMS :"),
        row(31, 90, 4, "heading", "CHAPTER-49 111-132\nRESULTS OF DASAS"),
    ]
    entries = parse_toc(doubled)
    assert [e.number for e in entries] == [48, 49, 52]


def test_chapter_numbers_are_unique_and_sorted():
    tree = build_chapter_tree(
        TOC_ROWS + VOL2_TOC_ROWS + VOL2_TOC_ROWS, book_title=BOOK, total_pdf_pages=818
    )
    numbers = [c.number for c in tree]
    assert numbers == sorted(numbers)
    assert len(numbers) == len(set(numbers))


def test_parse_toc_reads_the_three_line_chapter_layout():
    """Chapters 61-66 put the page range on its own line. Reading only the
    two-line layout silently loses exactly those six."""
    entries = parse_toc(
        [
            row(
                40,
                12,
                2,
                "heading",
                "CHAPTER-61\n355-378\n"
                "RESULTS OF THE ANTARDASAS IN THE MAHADASA OF KETU:",
            )
        ]
    )
    assert len(entries) == 1
    assert entries[0].number == 61
    assert entries[0].printed_page == 355
    assert entries[0].printed_page_to == 378
    assert entries[0].title == "RESULTS OF THE ANTARDASAS IN THE MAHADASA OF KETU"


def test_body_chapter_heading_without_a_page_range_is_not_a_toc_entry():
    """`Chapter-48` printed in the body has no page span, so admitting it would
    create a chapter that spans nothing."""
    assert parse_toc([row(41, 100, 0, "heading", "Chapter-48")]) == []
    assert parse_toc([row(42, 100, 0, "heading", "CHAPTER-48\nDASA SYSTEMS :")]) == []
