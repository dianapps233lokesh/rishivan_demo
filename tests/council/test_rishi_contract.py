"""A Rishi report must say what argues against it.

Every product on the market suppresses disconfirming signal because it makes
the answer messier, and a model asked for an opinion supplies a confident one.
A contract is the only place that discipline survives contact with generation —
a prompt asking nicely for counter-evidence gets counter-evidence most of the
time, which is the same as not having it.
"""

import pytest
from pydantic import ValidationError

from rishivan.council.rishis.contract import (
    REPORT_SCHEMA,
    EvidenceItem,
    RishiReport,
    parse_report,
)


def _item(statement="The 2nd lord is exalted in the 11th", **kw):
    kw.setdefault("rule_ids", ["BPHS.WEALTH.CH34V12.0001"])
    kw.setdefault("chart_basis", ["lord.bhava.02 occupies bhava.11"])
    kw.setdefault("weight", 0.5)
    kw.setdefault("tier", "house")
    return EvidenceItem(statement=statement, **kw)


# ==========================================================================
# The weakening requirement
# ==========================================================================


def test_a_report_with_support_and_no_weakening_is_rejected():
    with pytest.raises(ValidationError):
        RishiReport(rishi="vyom", domain="domain.wealth",
                    supporting=[_item()], weakening=[],
                    score=0.5, confidence=0.6)


def test_an_abstention_may_have_neither():
    report = RishiReport(
        rishi="vyom", domain="domain.wealth", supporting=[], weakening=[],
        score=0.0, confidence=0.0,
        abstained="no rules fired in this domain",
    )
    assert report.abstained


def test_a_report_with_both_is_accepted():
    report = RishiReport(
        rishi="vyom", domain="domain.wealth",
        supporting=[_item()], weakening=[_item("Saturn aspects the 2nd")],
        score=0.4, confidence=0.55,
    )
    assert report.weakening


def test_the_rejection_message_says_what_to_do_instead():
    """A contract error a model cannot act on produces a retry that fails the
    same way."""
    with pytest.raises(ValidationError) as exc:
        RishiReport(rishi="vyom", domain="domain.wealth",
                    supporting=[_item()], weakening=[], score=0.5,
                    confidence=0.6)
    assert "abstain" in str(exc.value).lower()


# ==========================================================================
# Traceability
# ==========================================================================


def test_an_evidence_item_must_cite_a_rule():
    """Every item traces to Koonji. An uncited statement is the model's own
    opinion wearing the format of evidence."""
    with pytest.raises(ValidationError):
        EvidenceItem(statement="Jupiter is strong", rule_ids=[],
                     chart_basis=["graha.jupiter"], weight=0.5, tier="house")


def test_an_evidence_item_must_rest_on_something_in_the_chart():
    with pytest.raises(ValidationError):
        EvidenceItem(statement="x", rule_ids=["r1"], chart_basis=[],
                     weight=0.5, tier="house")


def test_an_empty_statement_is_rejected():
    with pytest.raises(ValidationError):
        _item(statement="   ")


def test_a_tier_outside_the_declared_set_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceItem(statement="x", rule_ids=["r1"], chart_basis=["y"],
                     weight=0.5, tier="vibes")


def test_every_declared_tier_is_accepted():
    from rishivan.council.hierarchy import TIERS

    for tier in TIERS:
        assert EvidenceItem(statement="x", rule_ids=["r1"],
                            chart_basis=["y"], weight=0.5, tier=tier)


# ==========================================================================
# Bounds
# ==========================================================================


@pytest.mark.parametrize("score", [1.5, -1.5])
def test_score_is_bounded_both_ways(score):
    with pytest.raises(ValidationError):
        RishiReport(rishi="vyom", domain="d", supporting=[_item()],
                    weakening=[_item()], score=score, confidence=0.5)


def test_a_negative_score_is_legitimate():
    """The chart arguing against the thing asked about is an answer."""
    report = RishiReport(rishi="vyom", domain="d", supporting=[_item()],
                         weakening=[_item()], score=-0.7, confidence=0.6)
    assert report.score < 0


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_confidence_is_bounded(confidence):
    with pytest.raises(ValidationError):
        RishiReport(rishi="vyom", domain="d", supporting=[_item()],
                    weakening=[_item()], score=0.1, confidence=confidence)


# ==========================================================================
# Degrading, rather than failing
# ==========================================================================


def test_unparseable_output_becomes_an_abstention_not_an_exception():
    """A model returning prose where JSON was asked for costs one Rishi's
    opinion. Synthesis proceeds with fewer reports and says so."""
    report = parse_report("I think it's good!", rishi="vyom", domain="d")
    assert report.abstained
    assert report.rishi == "vyom"


def test_a_contract_violation_becomes_an_abstention():
    """Valid JSON that breaks the weakening rule. The likeliest real failure,
    because it is what an encouraging model produces."""
    text = '{"supporting": [{"statement": "good", "rule_ids": ["r1"], '\
           '"chart_basis": ["x"], "weight": 0.5, "tier": "house"}], '\
           '"weakening": [], "score": 0.5, "confidence": 0.6}'
    report = parse_report(text, rishi="vyom", domain="d")
    assert report.abstained


def test_the_abstention_names_the_reason():
    report = parse_report("nonsense", rishi="vyom", domain="d")
    assert len(report.abstained) > 10


def test_a_valid_generation_round_trips():
    text = '{"supporting": [{"statement": "the 2nd lord is exalted", '\
           '"rule_ids": ["r1"], "chart_basis": ["x"], "weight": 0.5, '\
           '"tier": "house"}], "weakening": [{"statement": "Saturn aspects it", '\
           '"rule_ids": ["r2"], "chart_basis": ["y"], "weight": 0.3, '\
           '"tier": "house"}], "score": 0.4, "confidence": 0.6, '\
           '"assumptions": ["birth time to the minute"], '\
           '"would_change_my_mind": ["a D9 contradiction"], '\
           '"confidence_reasons": ["two independent sources"]}'
    report = parse_report(text, rishi="medhan", domain="domain.relationship")
    assert not report.abstained
    assert report.rishi == "medhan"
    assert report.domain == "domain.relationship"
    assert report.assumptions and report.would_change_my_mind


def test_the_rishi_and_domain_are_never_taken_from_the_model():
    """Who is speaking and about what are the graph's facts, not the
    generation's. A model that names itself differently would fan its report
    into the wrong slot."""
    text = '{"rishi": "impostor", "domain": "domain.wealth", '\
           '"supporting": [], "weakening": [], "score": 0, '\
           '"confidence": 0, "abstained": "nothing fired"}'
    report = parse_report(text, rishi="vyom", domain="domain.health")
    assert report.rishi == "vyom"
    assert report.domain == "domain.health"


def test_fenced_json_is_tolerated():
    """Models wrap JSON in markdown fences regardless of the mime type asked
    for. Losing a whole opinion to three backticks is not a tradeoff."""
    text = '```json\n{"supporting": [], "weakening": [], "score": 0, '\
           '"confidence": 0, "abstained": "nothing fired"}\n```'
    assert not parse_report(text, rishi="vyom", domain="d").abstained.startswith(
        "unparseable"
    )


# ==========================================================================
# The schema handed to the model
# ==========================================================================


def test_the_schema_is_generated_from_the_model_not_hand_written():
    """A hand-written copy is a second thing to drift, and it drifts towards
    whatever the model happened to return last."""
    assert REPORT_SCHEMA == RishiReport.model_json_schema()


def test_the_schema_asks_for_weakening():
    assert "weakening" in str(REPORT_SCHEMA)
