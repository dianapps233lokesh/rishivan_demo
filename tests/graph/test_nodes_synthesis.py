"""Arrange what the council said, and never re-decide it.

The invariant running through this file: **disagreement survives and
counter-evidence survives.** Both are the messy half, both are what every
product on the market drops, and both are the entire credibility play.
"""

import pytest

from rishivan.council.rishis.contract import EvidenceItem, RishiReport
from rishivan.council.rishis.sakshi import Audit, Finding
from rishivan.graph.nodes.synthesis import synthesis_node
from rishivan.graph.state import RishivanState, initial_state


def _item(statement="the 2nd lord is exalted", rule_ids=("r1",)):
    return EvidenceItem(statement=statement, rule_ids=list(rule_ids),
                        chart_basis=["x"], weight=0.5, tier="house")


def _report(rishi="dhruvan", score=0.5, *, abstained="", confidence=0.6,
            weakening=None):
    if abstained:
        return RishiReport(rishi=rishi, domain="domain.wealth",
                           abstained=abstained)
    return RishiReport(
        rishi=rishi, domain="domain.wealth",
        supporting=[_item()],
        weakening=list(weakening if weakening is not None
                       else [_item("Saturn aspects the 2nd", ("r2",))]),
        score=score, confidence=confidence,
        confidence_reasons=["two independent sources"],
    )


def _state(reports, *, audit=None, unreviewed=False):
    s = initial_state("will I become wealthy?")
    s["reports"] = list(reports)
    s["audit"] = audit
    s["reading_is_unreviewed"] = unreviewed
    return s


# ==========================================================================
# Convergence: reported, never averaged
# ==========================================================================


def test_agreement_between_two_rishis_is_reported_not_averaged():
    out = synthesis_node(_state([_report("dhruvan", 0.7),
                                 _report("vyom", 0.6)]))
    assert out["convergence"]["agreeing"] == 2
    assert "mean" not in out["convergence"]
    assert "score" not in out["convergence"]


def test_a_disagreement_survives_into_the_summary():
    out = synthesis_node(_state([_report("dhruvan", 0.7),
                                 _report("vyom", -0.6)]))
    assert out["convergence"]["disagreement"] is True
    assert "disagree" in out["council_summary"].lower()


def test_a_disagreement_is_not_split_down_the_middle():
    out = synthesis_node(_state([_report("dhruvan", 0.7),
                                 _report("vyom", -0.6)]))
    assert "average" in out["council_summary"].lower()


def test_a_near_zero_score_is_undecided_not_positive():
    """Rounding an undecided council into a direction manufactures a verdict
    nobody reached."""
    out = synthesis_node(_state([_report("dhruvan", 0.05)]))
    assert out["convergence"]["undecided"] == ["dhruvan"]
    assert out["convergence"]["for"] == []


# ==========================================================================
# What must never be dropped
# ==========================================================================


def test_weakening_evidence_reaches_the_summary():
    out = synthesis_node(_state([_report()]))
    assert "against:" in out["council_summary"]


def test_abstentions_are_named_not_dropped():
    out = synthesis_node(_state([
        _report("dhruvan", 0.5),
        _report("vyom", abstained="no rules fired in my domains"),
    ]))
    assert "abstained" in out["council_summary"].lower()
    assert out["convergence"]["abstained"] == 1


def test_the_audit_findings_reach_the_summary():
    audit = Audit(findings=[Finding(kind="unmentioned_cancellation",
                                    rishi="dhruvan",
                                    detail="a yoga was cancelled and nobody said so")])
    out = synthesis_node(_state([_report()], audit=audit))
    assert "cancelled" in out["council_summary"].lower()


def test_the_auditors_note_reaches_the_summary():
    audit = Audit(findings=[], note="a simpler reading fits this evidence")
    out = synthesis_node(_state([_report()], audit=audit))
    assert "simpler reading" in out["council_summary"]


def test_the_unreviewed_provenance_reaches_the_summary():
    out = synthesis_node(_state([_report()], unreviewed=True))
    assert "review" in out["council_summary"].lower()


def test_confidence_reasons_survive():
    out = synthesis_node(_state([_report()]))
    assert "two independent sources" in out["council_summary"]


# ==========================================================================
# The empty cases, which are answers
# ==========================================================================


def test_no_reports_produces_an_honest_summary_not_an_empty_string():
    """An empty block reads to the narrative model as "no instruction", and
    it fills the gap with its own confidence."""
    out = synthesis_node(_state([]))
    assert out["council_summary"]
    assert "silent" in out["council_summary"].lower()


def test_a_wholly_abstaining_council_says_so_as_a_finding():
    out = synthesis_node(_state([
        _report("dhruvan", abstained="nothing fired"),
        _report("vyom", abstained="nothing fired"),
    ]))
    assert "abstained" in out["council_summary"].lower()
    assert out["convergence"]["speaking"] == 0


# ==========================================================================
# Re-examination
# ==========================================================================


def test_a_re_examined_rishi_speaks_with_its_latest_report():
    """`reports` is additive, so the second pass appends. The council speaks
    with its latest voice; the earlier report stays in state for the trace."""
    out = synthesis_node(_state([
        _report("dhruvan", 0.9),
        _report("dhruvan", -0.4),
    ]))
    assert out["convergence"]["speaking"] == 1
    assert out["convergence"]["against"] == ["dhruvan"]


def test_the_superseded_report_is_not_deleted_from_state():
    state = _state([_report("dhruvan", 0.9), _report("dhruvan", -0.4)])
    synthesis_node(state)
    assert len(state["reports"]) == 2


# ==========================================================================
# Contract
# ==========================================================================


def test_every_key_returned_is_declared_in_the_state():
    out = synthesis_node(_state([_report()]))
    assert set(out) <= set(RishivanState.__annotations__)


def test_the_node_makes_no_model_call():
    """It arranges; it does not run a ninth opinion over the eight that
    already exist."""
    import inspect

    assert "client" not in inspect.signature(synthesis_node).parameters


def test_it_is_deterministic():
    state = _state([_report("dhruvan", 0.7), _report("vyom", -0.6)])
    assert synthesis_node(state) == synthesis_node(state)
