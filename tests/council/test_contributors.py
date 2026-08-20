"""Contributors compute evidence for the Rishi who speaks.

Deterministic by design (spec Section 3): N generation calls before the first token is
latency the reading cannot absorb, and a generated briefing paraphrases -- the same
failure that already forces nakshatra names to be printed outside the Rishi's voice.
"""

from rishivan.council.contributors import ContributorReport, domain_contribution
from rishivan.rag.rules import RuleHit

LAGNA_RULE = RuleHit(
    rule_key="lagna",
    condition={"atoms": [{"type": "lord_of_house_in_house", "lord_of": 1, "house": 7}]},
    effects=[{"polarity": "positive", "statement": "the native is resolute"}],
    source={"chapter": "12", "verse_ref": "2"},
    relevance=0.0,
)
CAREER_RULE = RuleHit(
    rule_key="career",
    condition={"atoms": [{"type": "lord_of_house_in_house", "lord_of": 10, "house": 11}]},
    effects=[{"polarity": "positive", "statement": "gains through profession"}],
    source={"chapter": "34", "verse_ref": "5"},
    relevance=0.0,
)


def test_a_domain_contributor_returns_only_rules_inside_its_coverage():
    """ATMA's coverage is house 1 alone, so the 10th-house rule must not appear."""
    report = domain_contribution("atma", [LAGNA_RULE, CAREER_RULE])
    assert report is not None
    assert [r.rule_key for r in report.rules] == ["lagna"]


def test_the_report_names_the_persona_that_owns_the_domain():
    report = domain_contribution("atma", [LAGNA_RULE])
    assert report.rishi in {"agam", "tattvan"}
    report = domain_contribution("karma", [CAREER_RULE])
    assert report.rishi == "dhruvan"


def test_a_contributor_with_nothing_in_coverage_returns_none():
    """Spec Section 3: an empty report never reaches the prompt, so a thin corpus
    cannot pad an answer with noise."""
    assert domain_contribution("atma", [CAREER_RULE]) is None


def test_a_contributor_given_no_rules_returns_none():
    assert domain_contribution("atma", []) is None


def test_an_unknown_domain_returns_none_rather_than_everything():
    assert domain_contribution("nonsense", [LAGNA_RULE, CAREER_RULE]) is None


def test_an_empty_report_is_empty():
    assert ContributorReport(rishi="ritam", computed={}, rules=()).is_empty is True
    assert ContributorReport(
        rishi="ritam", computed={"Mahadasha": "Saturn"}, rules=()
    ).is_empty is False
    assert ContributorReport(
        rishi="tattvan", computed={}, rules=(LAGNA_RULE,)
    ).is_empty is False


def test_a_report_is_frozen():
    import dataclasses

    import pytest

    report = ContributorReport(rishi="ritam", computed={}, rules=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.rishi = "vyom"
