"""Blueprint §12: a firing is weighted by the kind of evidence it rests on.

Without this, a D9 confirmation of a marriage reading counts exactly as much as
the 7th-lord placement it is confirming - which is the "one generic scoring
formula for every life question" the blueprint rejects by name.

Every assertion here is an invariant. The exact weights live in
`council/hierarchy.py` and are a tuning decision; that a D1 placement outranks
its own divisional confirmation is not.
"""

import pytest

from rishivan.koonji.evidence import (
    TIER_PREDICATES,
    build_evidence,
    tier_of,
)
from rishivan.koonji.urf import (
    Antecedent,
    AssertionKind,
    BoolExpr,
    ClaimConsequent,
    Corroboration,
    PredicateCall,
    Provenance,
    Qualifiers,
    Rule,
)
from rishivan.koonji.vm import Firing, Outcome


def _leaf(predicate, **args):
    return BoolExpr(op="leaf", leaf=PredicateCall(predicate=predicate, args=args))


def _rule(rule_id, expr, *, claim="wealth.accumulation", corroboration_n=None):
    return Rule(
        rule_id=rule_id,
        registry_version="1.0.0",
        school="school.parashari",
        domains={"domain.wealth": 1.0},
        status="production",
        antecedent=Antecedent(expr=expr),
        assertion=AssertionKind.ASSERT_CLAIM,
        consequent=ClaimConsequent(
            claim_id=claim, polarity="positive",
            magnitude="strong", literal_text="…",
        ),
        qualifiers=Qualifiers(
            corroboration=(
                Corroboration.REQUIRES_N if corroboration_n
                else Corroboration.STANDALONE
            ),
            corroboration_n=corroboration_n,
        ),
        provenance=Provenance(
            book_id="bphs", edition_id="bphs.ed", locator="ch34.v12",
            quoted_text="…", authority_tier="S0",
        ),
    )


HOUSE_RULE = _rule("r.house", _leaf(
    "occupies_bhava", subject="lord.bhava.02", bhava="bhava.11"))

VARGA_RULE = _rule("r.varga", _leaf(
    "varga_dignity", varga="varga.d9", subject="graha.venus",
    dignity="dignity.exalted"))

DASHA_RULE = _rule("r.dasha", _leaf(
    "dasha_active", subject="graha.jupiter", level="level.maha"))

JAIMINI_RULE = _rule("r.jaimini", _leaf(
    "chara_karaka", subject="graha.venus", karaka="bhava.07"))

MIXED_RULE = _rule("r.mixed", BoolExpr(op="all", operands=[
    _leaf("occupies_bhava", subject="lord.bhava.02", bhava="bhava.11"),
    _leaf("varga_dignity", varga="varga.d9", subject="graha.venus",
          dignity="dignity.exalted"),
]))

CORROBORATED_RULE = _rule("r.strict", _leaf(
    "occupies_bhava", subject="lord.bhava.02", bhava="bhava.11"),
    corroboration_n=3)


def _fired(rule):
    return Firing(rule_id=rule.rule_id, version=rule.version,
                  outcome=Outcome.FIRED, claim_id=rule.consequent.claim_id)


# ==========================================================================
# Classification
# ==========================================================================


def test_a_plain_placement_rule_is_a_house_rule():
    assert tier_of(HOUSE_RULE) == "house"


def test_a_rule_naming_a_varga_is_a_varga_rule():
    assert tier_of(VARGA_RULE) == "varga"


def test_a_dasha_rule_is_a_dasha_rule():
    assert tier_of(DASHA_RULE) == "dasha"


def test_a_chara_karaka_rule_is_a_jaimini_rule():
    assert tier_of(JAIMINI_RULE) == "jaimini"


def test_a_rule_spanning_tiers_takes_the_weakest():
    """A D1 condition does not upgrade a claim that also rests on a D9 one.
    Taking the strongest would let one house predicate launder every
    divisional claim in the corpus into a D1-grade statement."""
    assert tier_of(MIXED_RULE) == "varga"


def test_every_declared_tier_predicate_is_a_real_registry_predicate():
    """A tier keyed on a predicate that does not exist classifies nothing, and
    silently - the rule falls through to `house` and is over-weighted."""
    from rishivan.koonji.registry import seed_registry

    known = seed_registry().predicates()
    for predicate in TIER_PREDICATES:
        assert predicate in known, predicate


def test_every_tier_produced_is_a_tier_the_hierarchy_weights():
    from rishivan.council.hierarchy import TIERS

    assert set(TIER_PREDICATES.values()) <= set(TIERS)


# ==========================================================================
# Weighting
# ==========================================================================


def test_tier_weights_lower_the_confidence_of_a_varga_claim():
    firing = _fired(VARGA_RULE)
    plain = build_evidence([firing], [VARGA_RULE])
    weighted = build_evidence([firing], [VARGA_RULE], tier_weights={"varga": 0.5})
    assert weighted.claims[0].confidence < plain.claims[0].confidence


def test_a_house_rule_at_full_weight_outranks_a_varga_rule_discounted():
    weights = {"house": 1.0, "varga": 0.55}
    house = build_evidence([_fired(HOUSE_RULE)], [HOUSE_RULE], tier_weights=weights)
    varga = build_evidence([_fired(VARGA_RULE)], [VARGA_RULE], tier_weights=weights)
    assert house.claims[0].confidence > varga.claims[0].confidence


def test_an_absent_tier_weight_means_unchanged():
    """Every existing caller passes nothing. Nothing they get may change."""
    firing = _fired(HOUSE_RULE)
    a = build_evidence([firing], [HOUSE_RULE])
    b = build_evidence([firing], [HOUSE_RULE], tier_weights={"varga": 0.1})
    assert a.claims[0].confidence == b.claims[0].confidence


def test_the_support_edge_records_its_tier():
    """A reader shown a claim must be able to see it rests on a divisional
    chart. Discounting it silently is only half the fix."""
    graph = build_evidence([_fired(VARGA_RULE)], [VARGA_RULE])
    assert graph.claims[0].support[0].tier == "varga"


# ==========================================================================
# The corroboration floor
# ==========================================================================


def test_min_independent_raises_the_corroboration_floor():
    graph = build_evidence(
        [_fired(HOUSE_RULE)], [HOUSE_RULE], min_independent=2
    )
    claim = graph.claims[0]
    assert claim.corroboration_required == 2
    assert not claim.corroboration_met


def test_min_independent_never_lowers_a_rules_own_requirement():
    """A rule whose author demanded three sources still demands three."""
    graph = build_evidence(
        [_fired(CORROBORATED_RULE)], [CORROBORATED_RULE], min_independent=1
    )
    assert graph.claims[0].corroboration_required == 3


def test_a_floor_of_one_is_met_by_a_single_source():
    graph = build_evidence(
        [_fired(HOUSE_RULE)], [HOUSE_RULE], min_independent=1
    )
    assert graph.claims[0].corroboration_met


def test_an_unmet_floor_caps_confidence_rather_than_deleting_the_claim():
    """The claim survives and is stated quietly. Deleting it would hide from
    the reader that the chart said anything at all."""
    from rishivan.koonji.evidence import INSUFFICIENT_BELOW

    graph = build_evidence(
        [_fired(HOUSE_RULE)], [HOUSE_RULE], min_independent=3
    )
    assert graph.claims
    assert graph.claims[0].confidence <= INSUFFICIENT_BELOW


def test_min_independent_none_leaves_every_existing_claim_alone():
    firing = _fired(HOUSE_RULE)
    a = build_evidence([firing], [HOUSE_RULE])
    b = build_evidence([firing], [HOUSE_RULE], min_independent=None)
    assert a.claims[0].confidence == b.claims[0].confidence
    assert a.claims[0].corroboration_required == b.claims[0].corroboration_required
