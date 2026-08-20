"""M1 schema: chapter tree, Rishi affinity, authority tier, geometry-free rows."""

from rishivan.models.knowledge.affinity import RISHI_KEYS, BookRishiAffinity
from rishivan.models.knowledge.book import Book
from rishivan.models.knowledge.chapter import Chapter
from rishivan.models.knowledge.page import PageElementRow


def test_chapter_table_and_columns():
    assert Chapter.__tablename__ == "chapter"
    for col in (
        "book_id",
        "number",
        "title",
        "printed_page_from",
        "printed_page_to",
        "pdf_page_from",
        "pdf_page_to",
        "is_rule_bearing",
        "gating_reason",
    ):
        assert col in Chapter.__table__.columns


def test_eight_rishi_keys_exact():
    assert RISHI_KEYS == (
        "atma",
        "prema",
        "artha",
        "karma",
        "vansh",
        "aarogya",
        "yatra",
        "dharma",
    )


def test_affinity_table():
    assert BookRishiAffinity.__tablename__ == "book_rishi_affinity"
    assert "weight" in BookRishiAffinity.__table__.columns
    assert "rishi" in BookRishiAffinity.__table__.columns


def test_book_has_source_authority_tier():
    assert "source_authority_tier" in Book.__table__.columns


def test_bridged_element_needs_no_geometry():
    # BPHS carries JSONB null bbox on all 10,052 rows; the column must accept it.
    assert PageElementRow.__table__.columns["bbox"].nullable is True
    assert "source_element_id" in PageElementRow.__table__.columns
