"""One policy per varga: purpose, method, evidence tier, confidence floor.

Blueprint §7: "Do not use every Varga merely because it exists. Each Varga must
have a documented purpose, calculation method and evidence hierarchy."

The tests below mostly guard against the two ways this table rots: a varga the
engine can compute but nobody wrote a policy for, and a policy that asserts a
confidence floor instead of deriving it from the varga's own arc.
"""

import pytest

from rishivan.varga.confidence import BirthConfidence, min_confidence_for_arc
from rishivan.varga.policy import (
    POLICIES,
    Usage,
    arc_of,
    policies_for_domain,
    policy_for,
)


class TestCompleteness:
    def test_every_computable_varga_has_a_policy(self):
        """A varga the engine can compute and nobody scoped is a varga that
        will eventually be used for something it was never meant for."""
        from rishivan.chart.vendor import varga

        assert set(varga.VARGA_REGISTRY) == set(POLICIES)

    def test_every_policy_states_a_purpose(self):
        for p in POLICIES.values():
            assert p.purpose.strip(), p.code

    def test_every_policy_names_its_method(self):
        for p in POLICIES.values():
            assert p.method.strip(), p.code

    def test_no_method_is_claimed_without_a_source(self):
        """A calculation method with no citation is a method nobody can check,
        and divisional schemes are exactly where authorities diverge."""
        for p in POLICIES.values():
            assert p.method_source.strip(), p.code

    def test_an_unknown_code_raises(self):
        with pytest.raises(KeyError):
            policy_for("D81")


class TestTheBlueprintTable:
    """Seeded verbatim. Each of these is a row a reviewer can check."""

    @pytest.mark.parametrize("code,domain", [
        ("D2", "domain.wealth"),
        ("D3", "domain.status"),
        ("D4", "domain.property"),
        ("D7", "domain.progeny"),
        ("D9", "domain.relationship"),
        ("D10", "domain.career"),
        ("D12", "domain.status"),
        ("D20", "domain.spiritual"),
        ("D24", "domain.education"),
    ])
    def test_the_primary_domain_matches_the_table(self, code, domain):
        assert policy_for(code).domain == domain

    def test_d1_is_always_primary(self):
        assert policy_for("D1").usage is Usage.ALWAYS

    def test_d9_and_d10_are_mandatory_cross_checks(self):
        for code in ("D9", "D10"):
            assert policy_for(code).usage is Usage.MANDATORY_CROSSCHECK

    def test_d27_is_gated_on_validated_methodology(self):
        """"Use only with validated methodology" — so it does not ship on."""
        assert policy_for("D27").usage is Usage.VALIDATED_ONLY

    def test_d30_is_marked_cautious(self):
        assert "caution" in policy_for("D30").purpose.lower() or \
            policy_for("D30").usage is Usage.METHOD_SPECIFIC

    def test_the_high_sensitivity_vargas_are_method_specific_or_stricter(self):
        for code in ("D40", "D45", "D60"):
            assert policy_for(code).usage in (
                Usage.METHOD_SPECIFIC, Usage.VALIDATED_ONLY,
            )


class TestConfidenceIsDerivedNotAsserted:
    def test_the_floor_comes_from_the_varga_arc(self):
        """Derived, so adding D81 needs arithmetic rather than a judgement."""
        for p in POLICIES.values():
            assert p.min_birth_confidence == min_confidence_for_arc(arc_of(p.code))

    def test_the_arc_shrinks_as_the_divisor_grows(self):
        assert arc_of("D1") > arc_of("D9") > arc_of("D60")

    def test_d60_is_half_a_degree(self):
        assert arc_of("D60") == pytest.approx(0.5)

    def test_d60_demands_minute_precision(self):
        """The blueprint's own example: "D60 and other high-sensitivity Vargas
        must be flagged when birth-time uncertainty makes them unreliable"."""
        assert policy_for("D60").min_birth_confidence >= BirthConfidence.MINUTE

    def test_a_finer_varga_never_demands_less(self):
        by_divisor = sorted(POLICIES.values(), key=lambda p: arc_of(p.code), reverse=True)
        floors = [p.min_birth_confidence for p in by_divisor]
        assert floors == sorted(floors)


class TestLookupByDomain:
    def test_a_career_question_reaches_d10(self):
        assert "D10" in [p.code for p in policies_for_domain("domain.career")]

    def test_a_marriage_question_reaches_d9(self):
        assert "D9" in [p.code for p in policies_for_domain("domain.relationship")]

    def test_a_domain_nobody_mapped_returns_nothing_rather_than_everything(self):
        """Returning all sixteen for an unmapped domain is how "do not use every
        varga merely because it exists" gets quietly undone."""
        assert policies_for_domain("domain.gardening") == ()

    def test_d1_is_not_returned_by_domain(self):
        """It is always in scope, so returning it per-domain would double it."""
        for domain in ("domain.career", "domain.wealth"):
            assert "D1" not in [p.code for p in policies_for_domain(domain)]


class TestEvidenceTier:
    def test_every_policy_has_a_tier(self):
        for p in POLICIES.values():
            assert p.evidence_tier in (1, 2)

    def test_the_mandatory_crosschecks_are_tier_one(self):
        """Tier 1 corroborates D1 directly; tier 2 is supporting only."""
        for code in ("D9", "D10"):
            assert policy_for(code).evidence_tier == 1
