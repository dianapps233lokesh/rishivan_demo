"""Page retrieval filters on Blueprint §4's levels, not on an invented taxonomy.

The old filter used ten hand-made tags (`foundation`, `prediction`, `timing`…) that
appear in neither client document and flatten three of §4's five levels into one list.
It was also broken: `book_domain` was written both as `'foundation'` and as the
stringified list `"['numerology']"`, and `MatchAny` cannot match the second — so roughly
a quarter of the corpus, including every numerology book, was unreachable through it.

`book_slug` is already a keyword-indexed payload field, so filtering by slug needs no
re-embedding and no payload rewrite.
"""

from rishivan.council.source_matrix import slugs_for_universe
from rishivan.rag.vector_store import slug_filter


def test_the_jyotisha_universe_excludes_the_numerology_books():
    """§4 level 1, and ER §13: numerology is a modality a Rishi may call, and it "must
    never silently override natal astrology". Retrieving a numerology page as natal
    evidence is that override."""
    jyotisha = slugs_for_universe("jyotisha")
    assert "bphs-gcsharma-vol1" in jyotisha
    assert "prasnamarga-raman-part1" in jyotisha
    assert "cheiros-book-of-numbers" not in jyotisha


def test_the_numerology_universe_holds_only_the_numerology_books():
    numerology = slugs_for_universe("numerology")
    assert numerology == frozenset({
        "cheiros-book-of-numbers",
        "the-complete-book-of-numerology",
        "numerology-key-to-your-inner-self",
        "numerology-and-the-divine-triangle",
    })


def test_every_school_is_inside_the_jyotisha_universe_except_numerology():
    from rishivan.council.source_matrix import BOOK_SCHOOL, universe_for

    for slug, school in BOOK_SCHOOL.items():
        expected = "numerology" if school == "numerology" else "jyotisha"
        assert universe_for(slug) == expected, slug


def test_an_unknown_universe_yields_nothing_rather_than_everything():
    """A typo must not silently widen retrieval to the whole corpus."""
    assert slugs_for_universe("not-a-universe") == frozenset()


def test_the_filter_targets_book_slug_not_book_domain():
    """`book_domain` holds two incompatible shapes in the live collection; `book_slug`
    is written consistently and is already indexed."""
    built = slug_filter(["bphs-gcsharma-vol1", "saravali-santhanam-en"])
    rendered = repr(built)
    assert "book_slug" in rendered
    assert "book_domain" not in rendered


def test_an_empty_slug_list_builds_no_filter():
    """None means "no restriction", which must not be confused with "match nothing"."""
    assert slug_filter([]) is None
