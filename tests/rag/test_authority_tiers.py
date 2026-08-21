"""Source authority comes from Blueprint §12's tiers, not from hand-set numbers.

§12 defines S0 primary classical text, S1 traditional commentary, S2 scholarly edition,
S3 established practitioner, S4 modern interpretation, S5 experimental — "engineering
categories, not claims about spiritual authority". §8's rule 4 is what needs them:
"Primary classical source > established commentary > established practitioner >
experimental material."

The table this replaces was 21 books at invented floats (BPHS 1.00, Phaladeepika 0.90,
Bhavartha 0.70) with no stated basis. The tiers at least have a definition.
"""

from rishivan.council.source_matrix import authority_tier
from rishivan.rag.authority import TIER_WEIGHT, authority_for_slug


def test_the_tier_weights_follow_the_documents_hierarchy():
    """§8 rule 4, in order."""
    order = ["S0", "S1", "S2", "S3", "S4", "S5"]
    weights = [TIER_WEIGHT[tier] for tier in order]
    assert weights == sorted(weights, reverse=True)
    assert all(0 < w <= 1.0 for w in weights)


def test_a_primary_classic_outranks_a_modern_practitioner():
    assert authority_for_slug("bphs-gcsharma-vol1") > authority_for_slug(
        "hindupredictiveastrology-raman"
    )


def test_a_practitioner_work_outranks_a_numerology_title():
    assert authority_for_slug("hindupredictiveastrology-raman") > authority_for_slug(
        "cheiros-book-of-numbers"
    )


def test_authority_is_derived_from_the_tier_not_a_separate_table():
    """One source of truth. Two tables would drift, and this one already had no basis."""
    for slug in ("bphs-gcsharma-vol1", "laghu-parashari",
                 "hindupredictiveastrology-raman", "cheiros-book-of-numbers"):
        assert authority_for_slug(slug) == TIER_WEIGHT[authority_tier(slug)], slug


def test_books_in_the_same_tier_weigh_the_same():
    """§12 does not rank within a tier, and inventing an order would be exactly the
    unfounded precision the old float table had."""
    assert authority_for_slug("bphs-gcsharma-vol1") == authority_for_slug(
        "saravali-santhanam-en"
    )


def test_an_unrated_book_gets_the_lowest_weight():
    assert authority_for_slug("some-new-upload") == TIER_WEIGHT["S5"]
