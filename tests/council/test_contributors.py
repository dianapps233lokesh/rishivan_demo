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


# --- the three service contributors ------------------------------------------

from datetime import datetime

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.council.contributors import (
    pattern_contribution,
    remedy_contribution,
    timing_contribution,
)

CHART = compute_chart(
    BirthData(1990, 1, 1, 6, 29, 0, 5.5, 28.6139, 77.2090, "New Delhi")
)
WHEN = datetime(2026, 8, 20, 12, 0)

TIMING_RULE = RuleHit(
    rule_key="t", condition={"atoms": []}, effects=[], source={},
    relevance=0.0, rule_category="timing",
)
REMEDY_RULE = RuleHit(
    rule_key="rem", condition={"atoms": []}, effects=[], source={},
    relevance=0.0, remedies=[{"kind": "mantra", "detail": "hymns to Shiva"}],
)


def test_the_timing_contributor_reports_the_running_periods():
    report = timing_contribution(CHART, [], when=WHEN)
    assert report is not None
    assert report.rishi == "ritam"
    assert "Mahadasha" in report.computed
    # Read off chart/dasha.py for this chart and date: the Saturn mahadasha runs
    # 2025-09-21 to 2044-09-21, Vimshottari's nineteen years.
    assert report.computed["Mahadasha"].startswith("Saturn until 2044-09-21")


def test_the_timing_contributor_carries_only_timing_rules():
    report = timing_contribution(CHART, [TIMING_RULE, LAGNA_RULE], when=WHEN)
    assert [r.rule_key for r in report.rules] == ["t"]


def test_the_pattern_contributor_reports_the_janma_nakshatra():
    report = pattern_contribution(CHART, [])
    assert report is not None
    assert report.rishi == "vyom"
    assert report.computed["Janma nakshatra"] == "Dhanishta"


def test_the_remedy_contributor_returns_none_when_no_rule_carries_one():
    """Not a corpus gap -- remedies are extracted. Before the payload fix they were
    never published, so this returned None on every chart."""
    assert remedy_contribution([LAGNA_RULE, CAREER_RULE]) is None


def test_the_remedy_contributor_reports_a_published_remedy():
    report = remedy_contribution([LAGNA_RULE, REMEDY_RULE])
    assert report is not None
    assert report.rishi == "tejan"
    assert [r.rule_key for r in report.rules] == ["rem"]


def test_no_service_contributor_claims_a_domain_persona():
    reports = [
        timing_contribution(CHART, [], when=WHEN),
        pattern_contribution(CHART, []),
        remedy_contribution([REMEDY_RULE]),
    ]
    assert {r.rishi for r in reports if r} == {"ritam", "vyom", "tejan"}


# --- selection ---------------------------------------------------------------

from rishivan.council.contributors import gather
from rishivan.council.routing import route_question


def test_a_timing_question_invokes_ritam():
    routing = route_question("When will I marry?")
    reports = gather(CHART, [TIMING_RULE], routing=routing,
                     question="When will I marry?", when=WHEN)
    assert "ritam" in {r.rishi for r in reports}


def test_a_potential_question_does_not_invoke_ritam():
    """Blueprint §8 rule 2: potential and timing are different reasoning problems. A
    'whether' question must not be handed a period it did not ask about."""
    routing = route_question("Will I marry?")
    reports = gather(CHART, [TIMING_RULE], routing=routing,
                     question="Will I marry?", when=WHEN)
    assert "ritam" not in {r.rishi for r in reports}


def test_vyom_always_contributes():
    for question in ("Will I marry?", "What career suits me?", "Will I be wealthy?"):
        routing = route_question(question)
        reports = gather(CHART, [], routing=routing, question=question, when=WHEN)
        assert "vyom" in {r.rishi for r in reports}, question


def test_a_secondary_domain_contributes_its_own_rules():
    """The billionaire case: §12 asks for ATMA beside ARTHA, so tattvan or agam must
    appear as a contributor."""
    from rishivan.council.routing import merge_supporting

    routing = merge_supporting(
        route_question("Will I become a billionaire?"), ["tattvan"]
    )
    reports = gather(CHART, [LAGNA_RULE, CAREER_RULE], routing=routing,
                     question="Will I become a billionaire?", when=WHEN)
    assert {"tattvan", "agam"} & {r.rishi for r in reports}


def test_the_primary_domain_is_never_also_a_contributor():
    """Its rules are the primary's own evidence, not a contribution."""
    routing = route_question("What career suits me?")
    reports = gather(CHART, [CAREER_RULE], routing=routing,
                     question="What career suits me?", when=WHEN)
    assert "dhruvan" not in {r.rishi for r in reports}


def test_no_empty_report_is_ever_returned():
    routing = route_question("Will I marry?")
    reports = gather(CHART, [], routing=routing, question="Will I marry?", when=WHEN)
    assert all(not r.is_empty for r in reports)


def test_a_remedy_question_routes_by_its_subject_not_by_the_word_remedy():
    assert route_question("What remedies should I do for my health?").primary == "aarogya"
    assert route_question("What remedies for Saturn?").primary is None
