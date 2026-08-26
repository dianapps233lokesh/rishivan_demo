"""The exhaustive list of what the narrative may say.

The gate is on the *prompt*: a model cannot cite what it was never shown. So
everything in this file is about what gets into the plan and what does not — a
claim below the evidence floor, a date with no window behind it, a certainty
word the band does not license.

Deterministic throughout. No client, no clock.
"""

import inspect

import pytest

from rishivan.council.answer_plan import (
    AllowedClaim,
    AnswerPlan,
    build_answer_plan,
)
from rishivan.council.hierarchy import hierarchy_for
from rishivan.council.rishis.contract import EvidenceItem, RishiReport
from rishivan.koonji.evidence import BANDS, INSUFFICIENT_BELOW

DOMAIN = "domain.wealth"


class _Support:
    def __init__(self, rule_id="r1", citation="bphs ch34.v12", tier="house"):
        self.rule_id = rule_id
        self._citation = citation
        self.tier = tier

    @property
    def citation(self):
        return self._citation


class _Claim:
    def __init__(self, claim_id="wealth.accumulation", confidence=0.7,
                 band="strongly_indicated",
                 phrasing="strongly indicated",
                 support=None, against=(), met=True, required=1, sources=2):
        self.claim_id = claim_id
        self.confidence = confidence
        self.band = band
        self.phrasing = phrasing
        self.polarity = "positive"
        self.support = list(support if support is not None else [_Support()])
        self.against = list(against)
        self.corroboration_met = met
        self.corroboration_required = required
        self.independent_sources = sources
        self.requires_activation = False

    def citations(self):
        seen = []
        for s in self.support + self.against:
            if s.citation and s.citation not in seen:
                seen.append(s.citation)
        return seen


class _Reading:
    def __init__(self, claims):
        self.claims = list(claims)

    def promises(self, domain):
        return bool(self.claims)


def _item(statement="the 2nd lord is exalted in the 11th", rule_ids=("r1",)):
    return EvidenceItem(statement=statement, rule_ids=list(rule_ids),
                        chart_basis=["x"], weight=0.5, tier="house")


def _report(rishi="dhruvan", score=0.5, *, abstained="", weakening=None):
    if abstained:
        return RishiReport(rishi=rishi, domain=DOMAIN, abstained=abstained)
    return RishiReport(
        rishi=rishi, domain=DOMAIN, supporting=[_item()],
        weakening=list(weakening if weakening is not None
                       else [_item("Saturn aspects the 2nd", ("r2",))]),
        score=score, confidence=0.6,
    )


class _Window:
    promise = True
    def __init__(self, start="Aug 2026", end="Aug 2036"):
        self.activation = type("R", (), {"__str__": lambda s: f"{start} – {end}",
                                         "start": start, "end": end})()
        self.trigger = None
        self.peak = None
        self.promise_basis = ("bphs ch34.v12",)


class _Timing:
    def __init__(self, window=None):
        self.by_system = {"vimshottari": window or _Window()}


class _Withheld:
    code = "D60"
    reason = "D60 needs a birth time known to the minute; yours is to the hour."


class _Vargas:
    selected = ("D1", "D9")
    withheld = (_Withheld(),)
    notes = ()


def _build(**kw):
    base = dict(
        question="will I become wealthy?",
        domain=DOMAIN,
        hierarchy=hierarchy_for(DOMAIN),
        reading=_Reading([_Claim()]),
        reports=[_report()],
        audit=None,
        timing=None,
        vargas=None,
        unreviewed=False,
    )
    base.update(kw)
    return build_answer_plan(**base)


# ==========================================================================
# The floor
# ==========================================================================


def test_a_claim_below_the_evidence_floor_is_not_allowed():
    """A 0.2-confidence claim is something the chart faintly suggests. It is
    not a statement the prose may assert, and the only reliable way to stop
    that is to never put it in the prompt."""
    plan = _build(reading=_Reading([_Claim(confidence=0.2, band="some_indications")]))
    assert plan.allowed == ()


def test_a_plan_with_nothing_above_the_floor_is_insufficient():
    plan = _build(reading=_Reading([]))
    assert plan.insufficient


def test_a_claim_at_the_floor_is_allowed():
    plan = _build(reading=_Reading([_Claim(confidence=INSUFFICIENT_BELOW)]))
    assert plan.allowed


# ==========================================================================
# Phrasing
# ==========================================================================


def test_an_allowed_claim_carries_the_phrasing_its_band_licenses():
    plan = _build(reading=_Reading([
        _Claim(confidence=0.5, band="some_indications",
               phrasing="some indications suggest")]))
    assert plan.allowed[0].phrasing == "some indications suggest"


def test_no_band_licenses_a_certainty_word():
    """The vocabulary itself has no way to say "will definitely". That is the
    point of licensing phrasing rather than asking for hedging."""
    for _, _, phrasing in BANDS:
        low = phrasing.lower()
        assert "will definitely" not in low
        assert "guaranteed" not in low
        assert "certainly" not in low


def test_the_phrasing_comes_from_the_claim_not_from_this_module():
    """A second copy of the band vocabulary is a second thing to drift."""
    plan = _build(reading=_Reading([_Claim(phrasing="moderately supported")]))
    assert plan.allowed[0].phrasing == "moderately supported"


# ==========================================================================
# What must not be dropped
# ==========================================================================


def test_counter_evidence_is_carried_on_the_claim():
    """The half every product drops. If it survives the evidence graph and
    dies here, it has been dropped — just later."""
    claim = _Claim(against=[_Support("r9", "saravali ch5.v3")])
    plan = _build(reading=_Reading([claim]))
    assert plan.allowed[0].counter


def test_an_uncorroborated_claim_is_marked_not_deleted():
    plan = _build(reading=_Reading([
        _Claim(met=False, required=2, sources=1)]))
    assert plan.allowed
    assert not plan.allowed[0].corroborated


def test_an_uncorroborated_claim_produces_something_that_must_be_said():
    plan = _build(reading=_Reading([_Claim(met=False, required=2, sources=1)]))
    assert any("corrobor" in m.lower() for m in plan.must_say)


def test_withheld_vargas_become_something_that_must_be_said():
    plan = _build(vargas=_Vargas())
    assert any("D60" in m for m in plan.must_say)


def test_an_abstention_becomes_something_that_must_be_said():
    plan = _build(reports=[_report(), _report("vyom", abstained="nothing fired")])
    assert any("abstain" in m.lower() for m in plan.must_say)


def test_unreviewed_rules_become_something_that_must_be_said():
    plan = _build(unreviewed=True)
    assert any("review" in m.lower() for m in plan.must_say)


# ==========================================================================
# Dates
# ==========================================================================


def test_a_date_is_only_allowed_when_a_window_supports_it():
    plan = _build(timing=None)
    assert all(not c.window for c in plan.allowed)


def test_no_window_forbids_naming_a_date():
    plan = _build(timing=None)
    assert any("date" in m.lower() for m in plan.must_not_say)


def test_a_window_attaches_to_the_claims_it_supports():
    plan = _build(timing=_Timing())
    assert any(c.window for c in plan.allowed)


def test_a_window_lifts_the_prohibition_on_dates():
    plan = _build(timing=_Timing())
    assert not any("date" in m.lower() for m in plan.must_not_say)


def test_a_promiseless_window_is_not_a_window():
    class _NoPromise:
        promise = False
        activation = None
    plan = _build(timing=_Timing(_NoPromise()))
    assert all(not c.window for c in plan.allowed)


# ==========================================================================
# The council
# ==========================================================================


def test_a_wholly_abstaining_council_is_insufficient():
    plan = _build(reports=[_report("dhruvan", abstained="nothing fired"),
                           _report("vyom", abstained="nothing fired")])
    assert plan.insufficient


def test_the_council_disagreement_survives():
    plan = _build(reports=[_report("dhruvan", 0.7), _report("vyom", -0.6)])
    assert plan.disagreement
    assert "average" in plan.disagreement.lower()


def test_agreement_produces_no_disagreement_note():
    plan = _build(reports=[_report("dhruvan", 0.7), _report("vyom", 0.6)])
    assert not plan.disagreement


def test_an_overclaim_prohibition_names_the_band_it_is_protecting():
    plan = _build(reading=_Reading([
        _Claim(confidence=0.5, band="some_indications",
               phrasing="some indications suggest")]))
    assert any("certain" in m.lower() or "definite" in m.lower()
               for m in plan.must_not_say)


# ==========================================================================
# Determinism and shape
# ==========================================================================


def test_the_plan_is_deterministic():
    assert _build() == _build()


def test_claims_are_ordered_by_confidence():
    plan = _build(reading=_Reading([
        _Claim("a", confidence=0.5), _Claim("b", confidence=0.9)]))
    assert [c.claim_id for c in plan.allowed] == ["b", "a"]


def test_the_builder_takes_no_client():
    assert "client" not in inspect.signature(build_answer_plan).parameters


def test_the_builder_reads_no_clock():
    """A backtest asks about 1998. A plan stamped `now` makes every replayed
    run look like it was produced today."""
    assert "datetime.now" not in inspect.getsource(build_answer_plan)


def test_the_plan_is_serialisable():
    """The whole structural point of the phase: this thing has to survive a
    checkpointer."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    JsonPlusSerializer().dumps_typed(_build(timing=_Timing(), vargas=_Vargas()))


def test_every_allowed_claim_cites_something():
    """A statement the prose may make with nothing behind it is the exact
    thing this gate exists to prevent."""
    for claim in _build().allowed:
        assert claim.citations or claim.rule_ids
