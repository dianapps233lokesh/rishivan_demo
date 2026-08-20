"""The Book × Rishi matrix, Eight Rishis §15.

§15 is the document's direct answer to "books corpus + domain mapping": a book maps to
many Rishis, weighted by concept coverage rather than owned by one. These tests pin the
transcription, because the values are the document's and must not drift into
approximations of them.
"""

import pytest

from rishivan.council.domains import LIFE_DOMAIN_KEYS
from rishivan.council.source_matrix import (
    SOURCE_HIGH,
    SOURCE_LOW,
    SOURCE_MEDIUM,
    SOURCE_RISHI_WEIGHTS,
    SOURCE_VERY_HIGH,
    source_family_for_slug,
    source_weight,
)


def test_every_family_rates_every_domain():
    """§15's table is dense: 8 columns for every row."""
    for family, weights in SOURCE_RISHI_WEIGHTS.items():
        assert set(weights) == set(LIFE_DOMAIN_KEYS), f"{family} is missing a domain"


def test_bphs_is_high_for_all_eight():
    """Stated explicitly in §15, and the reason a book-level weight cannot be the final
    answer for any individual rule."""
    assert set(SOURCE_RISHI_WEIGHTS["BPHS"].values()) == {SOURCE_HIGH}


def test_the_gita_is_very_high_for_dharma_and_low_elsewhere():
    gita = SOURCE_RISHI_WEIGHTS["Bhagavad Gita / Upanishads"]
    assert gita["dharma"] == SOURCE_VERY_HIGH
    assert gita["artha"] == SOURCE_LOW
    assert gita["karma"] == SOURCE_LOW


def test_muhurta_is_low_for_atma_and_high_for_the_event_domains():
    muhurta = SOURCE_RISHI_WEIGHTS["Muhurta corpus"]
    assert muhurta["atma"] == SOURCE_LOW
    assert muhurta["prema"] == SOURCE_HIGH
    assert muhurta["artha"] == SOURCE_HIGH
    assert muhurta["karma"] == SOURCE_HIGH
    assert muhurta["yatra"] == SOURCE_HIGH


def test_samudrika_is_high_only_for_atma():
    samudrika = SOURCE_RISHI_WEIGHTS["Samudrika / palmistry"]
    assert samudrika["atma"] == SOURCE_HIGH
    assert samudrika["aarogya"] == SOURCE_LOW
    assert samudrika["yatra"] == SOURCE_LOW


def test_kp_is_low_for_dharma():
    assert SOURCE_RISHI_WEIGHTS["KP corpus"]["dharma"] == SOURCE_LOW


def test_the_weight_scale_is_ordered():
    assert SOURCE_VERY_HIGH > SOURCE_HIGH > SOURCE_MEDIUM > SOURCE_LOW > 0


# ── Slug → family, for the books actually ingested ───────────────────────────

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
def test_every_ingested_book_maps_to_a_family(slug):
    """An unmapped book falls back to a neutral weight for every Rishi, which silently
    flattens §15 for that book. All 23 ingested slugs must resolve."""
    assert source_family_for_slug(slug) is not None, slug


def test_the_families_ingested_books_map_to_exist_in_the_matrix():
    for slug in INGESTED:
        family = source_family_for_slug(slug)
        assert family in SOURCE_RISHI_WEIGHTS, f"{slug} -> {family!r} is not in §15"


def test_prashna_books_map_to_the_prashna_family():
    assert source_family_for_slug("prasnamarga-raman-part1") == "Prashna corpus"
    assert source_family_for_slug("prashna-tantra") == "Prashna corpus"


def test_nadi_books_map_to_deva_keralam():
    assert source_family_for_slug("devakeralam-chandrakalanadi-vol1") == (
        "Deva Keralam / Nadi"
    )


def test_numerology_books_map_together():
    for slug in ("cheiros-book-of-numbers", "the-complete-book-of-numerology"):
        assert source_family_for_slug(slug) == "Numerology"


# ── The lookup used at retrieval time ────────────────────────────────────────


def test_source_weight_reads_the_matrix():
    assert source_weight("bphs-gcsharma-vol1", "prema") == SOURCE_HIGH
    assert source_weight("muhurtachintamani", "atma") == SOURCE_LOW


def test_an_unknown_slug_gets_a_neutral_weight_not_zero():
    """Zero would silently delete an unmapped book from every reading."""
    weight = source_weight("some-book-nobody-mapped", "prema")
    assert 0 < weight <= SOURCE_HIGH


def test_an_unknown_domain_gets_a_neutral_weight():
    assert source_weight("bphs-gcsharma-vol1", "not-a-domain") > 0


# ── Blueprint §12 source tiers ───────────────────────────────────────────────
#
# "S0 primary classical text; S1 traditional commentary; S2 scholarly/critical edition;
# S3 established practitioner; S4 modern interpretation; S5 experimental." BP §12 calls
# these "engineering categories, not claims about spiritual authority".


def test_every_ingested_book_has_a_tier():
    from rishivan.council.source_matrix import authority_tier

    for slug in INGESTED:
        assert authority_tier(slug) in {"S0", "S1", "S2", "S3", "S4", "S5"}, slug


def test_the_primary_classics_are_s0():
    from rishivan.council.source_matrix import authority_tier

    for slug in ("bphs-gcsharma-vol1", "bphs-gcsharma-vol2", "brihatjataka-row-1919",
                 "saravali-santhanam-en", "phaladeepika-sastri-1950"):
        assert authority_tier(slug) == "S0", slug


def test_a_modern_practitioner_work_ranks_below_a_classic():
    """Hindu Predictive Astrology is B. V. Raman writing in the 20th century, not a
    classical source. BP §4's hierarchy of evidence depends on the difference."""
    from rishivan.council.source_matrix import authority_tier

    assert authority_tier("hindupredictiveastrology-raman") > "S0"


def test_numerology_is_not_classical_jyotisha():
    from rishivan.council.source_matrix import authority_tier

    assert authority_tier("cheiros-book-of-numbers") >= "S3"


def test_an_unknown_slug_gets_the_lowest_tier():
    """An unrated book must not inherit classical authority by default."""
    from rishivan.council.source_matrix import authority_tier

    assert authority_tier("some-book-nobody-rated") == "S5"


# ── Blueprint §4 levels 1 and 2: universe and school ─────────────────────────
#
# §5 gives the school per book family directly ("BPHS / Parashari", "Brihat Jataka /
# Classical Hora", "Prashna Marga / Prashna"). §8 rule 5 is why it must be recorded:
# "Never mix schools silently. If a Jaimini rule is used alongside Parashari, label
# both." A rule stored with the column default is a rule that cannot be labelled.


def test_every_ingested_book_declares_a_school_and_universe():
    from rishivan.council.source_matrix import school_for, universe_for

    for slug in INGESTED:
        assert school_for(slug), slug
        assert universe_for(slug), slug


def test_the_schools_match_the_document():
    from rishivan.council.source_matrix import school_for

    assert school_for("bphs-gcsharma-vol1") == "parashari"
    assert school_for("phaladeepika-sastri-1950") == "parashari"
    assert school_for("brihatjataka-row-1919") == "classical_hora"
    assert school_for("devakeralam-chandrakalanadi-vol1") == "nadi"
    assert school_for("prasnamarga-raman-part1") == "prashna"
    assert school_for("prashna-tantra") == "prashna"
    assert school_for("muhurtachintamani") == "muhurta"


def test_numerology_is_a_separate_universe_not_a_jyotisha_school():
    """§4 level 1 separates Jyotisha from Numerology, and ER §13 makes numerology a
    modality a Rishi may call -- never something that silently joins natal evidence."""
    from rishivan.council.source_matrix import school_for, universe_for

    assert universe_for("cheiros-book-of-numbers") == "numerology"
    assert universe_for("bphs-gcsharma-vol1") == "jyotisha"
    assert school_for("cheiros-book-of-numbers") == "numerology"


def test_more_than_one_school_is_present_in_the_corpus():
    """If every book were one school, §8 rule 5 would be untestable -- and it is about
    to matter, because Prashna and Muhurta books are being bridged."""
    from rishivan.council.source_matrix import school_for

    assert len({school_for(slug) for slug in INGESTED}) >= 4


def test_an_unknown_slug_has_an_explicit_unknown_school():
    """Never defaulted to parashari: a mislabelled school is exactly the silent
    doctrine-mixing §8 rule 5 forbids."""
    from rishivan.council.source_matrix import school_for

    assert school_for("some-book-nobody-classified") == "unknown"
