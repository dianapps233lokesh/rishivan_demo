"""The adversarial auditor, and the loop bound that keeps it from hanging.

Six of Sakshi's seven hunts are checkable in code, so they are. That means the
audit still works when the model call fails, and it means each hunt has a test
rather than a hope.

The seventh — alternative explanations — is genuinely the model's job, and is
the only part that costs a call.
"""

import pytest

from rishivan.council.rishis.contract import EvidenceItem, RishiReport
from rishivan.council.rishis.sakshi import (
    Finding,
    audit_deterministic,
    route_after_sakshi,
)
from rishivan.council.hierarchy import hierarchy_for

H = hierarchy_for("domain.wealth")


def _item(statement="the 2nd lord is exalted", rule_ids=("r1",), tier="house"):
    return EvidenceItem(statement=statement, rule_ids=list(rule_ids),
                        chart_basis=["x"], weight=0.5, tier=tier)


def _report(rishi="dhruvan", *, score=0.5, supporting=None, weakening=None,
            abstained="", confidence=0.6):
    return RishiReport(
        rishi=rishi, domain="domain.wealth",
        supporting=list(supporting if supporting is not None else [_item()]),
        weakening=list(weakening if weakening is not None else [
            _item("Saturn aspects the 2nd", ("r2",))]),
        score=score, confidence=confidence, abstained=abstained,
    )


class _FakeReading:
    def __init__(self, cancelled=(), claims=()):
        self.evidence = type("E", (), {
            "cancelled": list(cancelled), "indeterminate": [],
        })()
        self.claims = list(claims)


class _FakeClaim:
    def __init__(self, claim_id, met=True, required=1, sources=1):
        self.claim_id = claim_id
        self.corroboration_met = met
        self.corroboration_required = required
        self.independent_sources = sources
        self.confidence = 0.6


# ==========================================================================
# The six deterministic hunts
# ==========================================================================


def test_a_cancelled_rule_nobody_mentioned_is_a_finding():
    """The single most damaging omission available. A yoga the VM broke, and
    seven Rishis describing it as intact."""
    reading = _FakeReading(cancelled=["BPHS.WEALTH.CH34V12.0009"])
    findings = audit_deterministic(
        [_report()], hierarchy=H, reading=reading, timing=None)
    assert any(f.kind == "unmentioned_cancellation" for f in findings)


def test_a_mentioned_cancellation_is_not_a_finding():
    reading = _FakeReading(cancelled=["r9"])
    report = _report(supporting=[_item("x", ("r1",))],
                     weakening=[_item("the yoga was cancelled", ("r9",))])
    findings = audit_deterministic(
        [report], hierarchy=H, reading=reading, timing=None)
    assert not any(f.kind == "unmentioned_cancellation" for f in findings)


def test_a_claim_below_the_corroboration_floor_is_a_finding():
    reading = _FakeReading(claims=[_FakeClaim("wealth.gain", met=False,
                                              required=2, sources=1)])
    findings = audit_deterministic(
        [_report()], hierarchy=H, reading=reading, timing=None)
    assert any(f.kind == "under_corroborated" for f in findings)


def test_two_reports_disagreeing_in_sign_is_a_finding():
    """Not resolved — surfaced. Two Rishis reading the same chart oppositely
    is the thing a reader should see, not have averaged away."""
    findings = audit_deterministic(
        [_report("dhruvan", score=0.7), _report("vyom", score=-0.6)],
        hierarchy=H, reading=_FakeReading(), timing=None)
    assert any(f.kind == "contradiction" for f in findings)


def test_agreement_is_not_a_finding():
    """An auditor that always finds something is an auditor nobody reads."""
    findings = audit_deterministic(
        [_report("dhruvan", score=0.7), _report("vyom", score=0.6)],
        hierarchy=H, reading=_FakeReading(), timing=None)
    assert not any(f.kind == "contradiction" for f in findings)


def test_timing_asserted_without_a_window_is_a_finding():
    report = _report(supporting=[
        _item("this happens in 2028", ("r1",))])
    findings = audit_deterministic(
        [report], hierarchy=H, reading=_FakeReading(), timing=None)
    assert any(f.kind == "undated_timing" for f in findings)


def test_a_date_with_a_window_behind_it_is_not_a_finding():
    class _W:
        promise = True
    timing = type("T", (), {"by_system": {"vimshottari": _W()}})()
    report = _report(supporting=[_item("this happens in 2028", ("r1",))])
    findings = audit_deterministic(
        [report], hierarchy=H, reading=_FakeReading(), timing=timing)
    assert not any(f.kind == "undated_timing" for f in findings)


def test_a_house_the_hierarchy_names_that_nobody_examined_is_a_finding():
    findings = audit_deterministic(
        [_report()], hierarchy=H, reading=_FakeReading(), timing=None)
    assert any(f.kind == "unexamined_hierarchy" for f in findings)


def test_a_council_that_wholly_abstained_is_a_finding():
    findings = audit_deterministic(
        [_report(abstained="nothing fired", supporting=[], weakening=[])],
        hierarchy=H, reading=_FakeReading(), timing=None)
    assert any(f.kind == "no_evidence" for f in findings)


def test_a_clean_set_of_reports_produces_no_findings():
    """The check that stops the auditor becoming decoration."""
    supporting = [
        _item(f"the {h}th is examined", ("r1",)) for h in H.houses
    ]
    reading = _FakeReading(claims=[_FakeClaim("wealth.gain")])
    findings = audit_deterministic(
        [_report(supporting=supporting)],
        hierarchy=H, reading=reading, timing=None)
    assert findings == []


def test_a_finding_names_the_rishi_it_is_for():
    """Re-examination sends findings back to specific Rishis. A finding
    addressed to nobody cannot be acted on."""
    reading = _FakeReading(cancelled=["r9"])
    findings = audit_deterministic(
        [_report()], hierarchy=H, reading=reading, timing=None)
    assert all(isinstance(f.rishi, str) for f in findings)


def test_every_finding_says_something_a_rishi_can_act_on():
    reading = _FakeReading(cancelled=["r9"],
                           claims=[_FakeClaim("w", met=False, required=2)])
    for finding in audit_deterministic(
            [_report()], hierarchy=H, reading=reading, timing=None):
        assert len(finding.detail) > 20, finding.kind


# ==========================================================================
# The loop bound
# ==========================================================================


def _audit(findings):
    from rishivan.council.rishis.sakshi import Audit

    return Audit(findings=list(findings))


def test_findings_send_the_council_back_once():
    state = {"audit": _audit([Finding(kind="contradiction", rishi="vyom",
                                      detail="x" * 30)]), "revisions": 0}
    assert route_after_sakshi(state) == "re_examine"


def test_re_examination_runs_at_most_once():
    """An unbounded critic loop is how a graph hangs in production at 3am,
    and it is a single comparison away."""
    state = {"audit": _audit([Finding(kind="contradiction", rishi="vyom",
                                      detail="x" * 30)]), "revisions": 1}
    assert route_after_sakshi(state) == "synthesis"


def test_a_clean_audit_forwards_immediately():
    assert route_after_sakshi({"audit": _audit([]), "revisions": 0}) == "synthesis"


def test_no_audit_forwards_rather_than_stalling():
    assert route_after_sakshi({"revisions": 0}) == "synthesis"


def test_the_router_is_pure():
    import inspect

    source = inspect.getsource(route_after_sakshi)
    assert "generate_content" not in source
