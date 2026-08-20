"""What the primary Rishi is allowed to see, and in what order.

Blueprint §8 rule 4 is a hierarchy of evidence. It cannot hold when a flat fact dump sits
beside cited rules with equal visibility, or when an S3 source and an S0 source look
identical.
"""

from rishivan.council.contributors import ContributorReport
from rishivan.council.prompts import contributor_context, coverage_facts, rule_context
from rishivan.rag.rules import RuleHit

FACTS = [
    "Ascendant (Lagna) is Cancer.",
    "The 1st house (self, body, personality) is ruled by Moon, placed in the 8th house.",
    "The 10th house (career, status, public life) is ruled by Mars, placed in the 5th house.",
]


def test_facts_inside_coverage_come_before_the_wider_chart():
    text = coverage_facts(FACTS, "atma")
    assert text.index("WITHIN YOUR COVERAGE") < text.index("WIDER CONTEXT")


def test_a_fact_about_an_owned_house_lands_inside_coverage():
    """ATMA owns house 1 alone."""
    inside = coverage_facts(FACTS, "atma").split("WIDER CONTEXT")[0]
    assert "1st house" in inside
    assert "10th house" not in inside


def test_a_planet_the_constitution_owns_lands_inside_coverage():
    """ATMA owns the Sun and Moon outright (§4). A house-only reading of coverage
    filed "Sun is in ..." under the wider chart -- demoting the single most important
    fact for a personality question."""
    facts = [*FACTS, "Sun is in Sagittarius in the 6th house (Purva Ashadha, pada 2)."]
    inside = coverage_facts(facts, "atma").split("WIDER CONTEXT")[0]
    assert "Sun is in Sagittarius" in inside


def test_a_planet_fact_is_not_filed_by_where_the_planet_sits():
    """The 6th is the Sun's location, not the fact's subject.

    KARMA owns house 6 and no planet at all, so a fact filed by the trailing house
    number would be claimed by KARMA -- a career reading leading on the Sun because it
    happens to sit in the 6th. AAROGYA is the wrong domain to test this with: it owns
    the Sun outright as the vitality karaka, so the fact is legitimately its own.
    """
    facts = ["Sun is in Sagittarius in the 6th house (Purva Ashadha, pada 2)."]
    inside = coverage_facts(facts, "karma").split("WIDER CONTEXT")[0]
    assert "Sun is in Sagittarius" not in inside


def test_the_chart_framework_is_always_inside_coverage():
    """Step 1 of every §4-11 protocol is "chart framework"."""
    for domain in ("atma", "artha", "prema"):
        inside = coverage_facts(FACTS, domain).split("WIDER CONTEXT")[0]
        assert "Ascendant (Lagna) is Cancer." in inside, domain


def test_no_fact_is_dropped():
    """Every §4-11 protocol ends in whole-chart synthesis, so demote -- never delete."""
    text = coverage_facts(FACTS, "atma")
    for fact in FACTS:
        assert fact in text


def test_an_unrouted_question_gets_the_facts_unsplit():
    text = coverage_facts(FACTS, None)
    assert "WIDER CONTEXT" not in text
    for fact in FACTS:
        assert fact in text


def test_a_contributor_block_names_the_rishi_and_its_values():
    report = ContributorReport(
        rishi="ritam",
        computed={"Mahadasha": "Saturn until 2044-09-21"},
        rules=(),
        note="3 timing rules true of this chart",
    )
    text = contributor_context((report,))
    assert "RITAM" in text
    assert "Saturn until 2044-09-21" in text
    assert "3 timing rules" in text


def test_no_contributors_renders_nothing():
    assert contributor_context(()) == ""


def test_a_rule_carries_its_tier_and_school():
    """The billionaire reading named an S3 source a 'classic text' while S0 BPHS sat
    unnamed beside it. Blueprint §8 rule 5 also forbids mixing schools silently."""
    hit = RuleHit(
        rule_key="r", condition={}, effects=[{"polarity": "positive", "statement": "x"}],
        source={"chapter": "1", "verse_ref": "1", "translation": "t"},
        relevance=1.0, tier="S3", school="prashna",
    )
    text = rule_context([hit])
    assert "S3" in text
    assert "prashna" in text
