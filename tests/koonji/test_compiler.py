"""The compiler is the quality gate.

An extraction that will not compile is almost always a bad extraction, so
attempting compilation before a human looks at anything filters a substantial
fraction of noise for free. Each pass below exists because it catches a class of
error that is otherwise invisible in production - not because it makes the code
tidy.
"""

import textwrap

import pytest
import yaml

from rishivan.koonji.compiler import (
    CompileError,
    compile_rules,
    parse_rule,
)
from rishivan.koonji.registry import seed_registry
from rishivan.koonji.urf import AssertionKind, Modality, Restriction


@pytest.fixture(scope="module")
def registry():
    return seed_registry()


def doc(text: str) -> dict:
    return yaml.safe_load(textwrap.dedent(text))


WEALTH = """
    id: PAR.WEALTH.2L11H.0001
    version: 1.0.0
    status: production
    school: school.parashari
    assertion: assert_claim
    domains: {domain.wealth: 0.95}
    source:
      book: bphs
      edition: bphs.gcs1984.en
      locator: ch34.v12
      quote: "If the lord of the 2nd is in the 11th, wealth accrues."
      review: {reviewer: RB-001, reviewed_at: 2026-08-23}
    when:
      all:
        - occupies_bhava: {subject: 2nd lord, bhava: 11}
    indicates:
      claim: wealth.accumulation
      polarity: positive
      magnitude: strong
      text: "wealth accrues"
"""


class TestParseAndResolve:
    def test_a_plain_rule_parses(self, registry):
        rule = parse_rule(doc(WEALTH), registry)
        assert rule.rule_id == "PAR.WEALTH.2L11H.0001"
        assert rule.assertion is AssertionKind.ASSERT_CLAIM
        assert rule.consequent.claim_id == "wealth.accumulation"

    def test_aliases_resolve_to_canonical_ids(self, registry):
        """A verse says "Guru"; the engine must never store "Guru"."""
        rule = parse_rule(doc(WEALTH), registry)
        call = rule.antecedent.expr.operands[0].leaf
        assert call.args == {"subject": "lord.bhava.02", "bhava": "bhava.11"}

    def test_sanskrit_names_resolve(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"occupies_bhava": {"subject": "Brihaspati", "bhava": "Dhana"}}]
        rule = parse_rule(d, registry)
        call = rule.antecedent.expr.operands[0].leaf
        assert call.args["subject"] == "graha.jupiter"
        assert call.args["bhava"] == "bhava.02"

    def test_an_unresolvable_symbol_is_an_error_not_a_guess(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"occupies_bhava": {"subject": "Proserpina", "bhava": 11}}]
        result = compile_rules([d], registry)
        assert not result.ok
        assert any("cannot resolve" in e.message for e in result.errors)

    def test_nested_operators_parse(self, registry):
        d = doc(WEALTH)
        d["when"] = [{
            "all": [
                {"occupies_bhava": {"subject": "2nd lord", "bhava": 11}},
                {"any": [
                    {"dignity": {"subject": "2nd lord", "dignity": "exalted"}},
                    {"dignity": {"subject": "2nd lord", "dignity": "own_sign"}},
                ]},
                {"not": {"combust": {"subject": "2nd lord"}}},
            ]
        }]
        rule = parse_rule(d, registry)
        assert rule.antecedent.expr.operands[0].op == "all"

    def test_count_parses(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"count": {"op": "gte", "n": 3, "of": {"in_kendra": {"subject": "?x"}}}}]
        rule = parse_rule(d, registry)
        node = rule.antecedent.expr.operands[0]
        assert node.op == "count" and node.count_n == 3


class TestTypeCheck:
    def test_an_unknown_argument_is_caught(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"occupies_bhava": {"subject": "2nd lord", "house": 11}}]
        result = compile_rules([d], registry)
        assert any("no argument 'house'" in e.message for e in result.errors)

    def test_a_missing_argument_is_caught(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"occupies_bhava": {"subject": "2nd lord"}}]
        result = compile_rules([d], registry)
        assert any("missing required argument" in e.message for e in result.errors)

    def test_a_wrong_kind_is_caught(self, registry):
        """A sign where a house belongs is the kind of slip that produces a
        rule which quietly never fires."""
        d = doc(WEALTH)
        d["when"] = [{"occupies_bhava": {"subject": "2nd lord", "bhava": "taurus"}}]
        result = compile_rules([d], registry)
        assert any("expected bhava" in e.message for e in result.errors)

    def test_cross_school_leakage_is_a_compile_error(self, registry):
        """A Parashari rule reaching for a Jaimini chara karaka is a doctrinal
        error, and it is exactly the kind that reads fine in prose."""
        d = doc(WEALTH)
        d["when"] = [{"chara_karaka": {"subject": "graha.venus", "karaka": "bhava.07"}}]
        result = compile_rules([d], registry)
        assert any("cross-school leakage" in e.message for e in result.errors)

    def test_the_same_predicate_is_fine_in_its_own_school(self, registry):
        d = doc(WEALTH)
        d["school"] = "school.jaimini"
        d["when"] = [{"chara_karaka": {"subject": "graha.venus", "karaka": "bhava.07"}}]
        result = compile_rules([d], registry)
        assert not any("cross-school" in e.message for e in result.errors)


class TestClosure:
    def test_an_unregistered_predicate_fails_the_build(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"observes_touch": {"subject": "querent"}}]
        result = compile_rules([d], registry)
        assert any("ExtensionProposal" in e.message for e in result.errors)

    def test_an_unregistered_claim_fails_the_build(self, registry):
        d = doc(WEALTH)
        d["indicates"]["claim"] = "wealth.lottery"
        result = compile_rules([d], registry)
        assert any("unregistered claim" in e.message for e in result.errors)


class TestContradiction:
    def test_two_houses_for_one_subject_is_unsatisfiable(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"all": [
            {"occupies_bhava": {"subject": "graha.saturn", "bhava": 10}},
            {"occupies_bhava": {"subject": "graha.saturn", "bhava": 4}},
        ]}]
        result = compile_rules([d], registry)
        assert any("unsatisfiable" in e.message for e in result.errors)

    def test_exalted_and_debilitated_at_once_is_unsatisfiable(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"all": [
            {"dignity": {"subject": "graha.saturn", "dignity": "exalted"}},
            {"dignity": {"subject": "graha.saturn", "dignity": "debilitated"}},
        ]}]
        result = compile_rules([d], registry)
        assert any("unsatisfiable" in e.message for e in result.errors)

    def test_disjoint_house_groups_are_caught(self, registry):
        """Kendras are 1/4/7/10, dusthanas 6/8/12. Nothing is in both."""
        d = doc(WEALTH)
        d["when"] = [{"all": [
            {"in_kendra": {"subject": "graha.mars"}},
            {"in_dusthana": {"subject": "graha.mars"}},
        ]}]
        result = compile_rules([d], registry)
        assert any("disjoint" in e.message for e in result.errors)

    def test_overlapping_house_groups_are_allowed(self, registry):
        """Kendra and trikona overlap at the first house, so this is a real
        configuration and must compile."""
        d = doc(WEALTH)
        d["when"] = [{"all": [
            {"in_kendra": {"subject": "graha.mars"}},
            {"in_trikona": {"subject": "graha.mars"}},
        ]}]
        result = compile_rules([d], registry)
        assert result.ok, [str(e) for e in result.errors]

    def test_required_and_forbidden_at_once_is_caught(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"all": [
            {"combust": {"subject": "graha.mercury"}},
            {"not": {"combust": {"subject": "graha.mercury"}}},
        ]}]
        result = compile_rules([d], registry)
        assert any("both required and forbidden" in e.message for e in result.errors)

    def test_a_disjunction_of_dignities_is_not_a_contradiction(self, registry):
        """DNF splits them into separate variants; each is satisfiable."""
        d = doc(WEALTH)
        d["when"] = [{"any": [
            {"dignity": {"subject": "graha.saturn", "dignity": "exalted"}},
            {"dignity": {"subject": "graha.saturn", "dignity": "own_sign"}},
        ]}]
        result = compile_rules([d], registry)
        assert result.ok, [str(e) for e in result.errors]


class TestRealizability:
    """Configurations that cannot physically occur. Nobody builds this pass and
    everybody needs it: without it, some percentage of the corpus is dead weight
    that never fires and that you never notice."""

    def test_mercury_cannot_be_five_houses_from_the_sun(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"all": [
            {"occupies_bhava": {"subject": "graha.sun", "bhava": 1}},
            {"occupies_bhava": {"subject": "graha.mercury", "bhava": 6}},
        ]}]
        result = compile_rules([d], registry)
        assert any("maximum elongation" in e.message for e in result.errors)

    def test_mercury_one_sign_from_the_sun_is_fine(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"all": [
            {"occupies_bhava": {"subject": "graha.sun", "bhava": 1}},
            {"occupies_bhava": {"subject": "graha.mercury", "bhava": 2}},
        ]}]
        result = compile_rules([d], registry)
        assert result.ok, [str(e) for e in result.errors]

    def test_venus_gets_a_wider_allowance_than_mercury(self, registry):
        """48 degrees of elongation reaches two signs; 28 does not."""
        d = doc(WEALTH)
        d["when"] = [{"all": [
            {"occupies_bhava": {"subject": "graha.sun", "bhava": 1}},
            {"occupies_bhava": {"subject": "graha.venus", "bhava": 3}},
        ]}]
        assert compile_rules([d], registry).ok

    def test_a_direct_rahu_is_impossible(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"all": [
            {"occupies_bhava": {"subject": "graha.rahu", "bhava": 3}},
            {"not": {"retrograde": {"subject": "graha.rahu"}}},
        ]}]
        result = compile_rules([d], registry)
        assert any("always retrograde" in e.message for e in result.errors)

    def test_a_retrograde_sun_is_impossible(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"retrograde": {"subject": "graha.sun"}}]
        result = compile_rules([d], registry)
        assert any("never retrograde" in e.message for e in result.errors)

    def test_rahu_conjunct_ketu_is_impossible(self, registry):
        d = doc(WEALTH)
        d["when"] = [{"conjunct": {"subject": "graha.rahu", "other": "graha.ketu"}}]
        result = compile_rules([d], registry)
        assert any("180 degrees apart" in e.message for e in result.errors)


class TestCorpusPasses:
    def cancellation(self, target="PAR.WEALTH.2L11H.0001"):
        d = doc(WEALTH)
        d["id"] = "PAR.WEALTH.2L11H.0001.C1"
        d["modality"] = "cancel"
        d["targets"] = target
        d["when"] = [{"combust": {"subject": "2nd lord"}}]
        return d

    def test_a_cancellation_pointing_at_a_real_rule_compiles(self, registry):
        result = compile_rules([doc(WEALTH), self.cancellation()], registry)
        assert result.ok, [str(e) for e in result.errors]

    def test_a_cancellation_pointing_at_nothing_fails(self, registry):
        """Dead code that looks like a working safety net."""
        result = compile_rules(
            [doc(WEALTH), self.cancellation(target="PAR.WEALTH.9999")], registry
        )
        assert any("targets unknown rule" in e.message for e in result.errors)

    def test_an_unconditional_rule_is_refused(self, registry):
        d = doc(WEALTH)
        del d["when"]
        result = compile_rules([d], registry)
        assert not result.ok
        assert any("every chart ever cast" in e.message for e in result.errors)

    def test_the_index_is_not_built_over_a_broken_corpus(self, registry):
        d = doc(WEALTH)
        d["indicates"]["claim"] = "nope.not.registered"
        result = compile_rules([d], registry)
        assert result.index is None, "an index over a known-broken corpus is a trap"

    def test_one_broken_rule_does_not_hide_the_others(self, registry):
        broken = doc(WEALTH)
        broken["id"] = "BROKEN"
        broken["indicates"]["claim"] = "nope"
        also_broken = doc(WEALTH)
        also_broken["id"] = "ALSO"
        also_broken["when"] = [{"retrograde": {"subject": "graha.sun"}}]
        result = compile_rules([broken, also_broken], registry)
        assert {e.rule_id for e in result.errors} >= {"BROKEN", "ALSO"}

    def test_raise_for_errors_surfaces_everything(self, registry):
        d = doc(WEALTH)
        d["indicates"]["claim"] = "nope"
        with pytest.raises(CompileError):
            compile_rules([d], registry).raise_for_errors()


class TestProvenanceGate:
    """`production` has to mean something. Reviewer throughput, not model
    quality, is the real bottleneck on this corpus, and the pressure to let
    extraction auto-publish in order to hit a date will be considerable."""

    def test_an_unreviewed_rule_cannot_be_production(self, registry):
        d = doc(WEALTH)
        d["source"].pop("review", None)
        result = compile_rules([d], registry)
        assert any("no reviewer" in e.message for e in result.errors)

    def test_an_unreviewed_rule_may_be_a_candidate(self, registry):
        d = doc(WEALTH)
        d["source"].pop("review", None)
        d["status"] = "candidate"
        assert compile_rules([d], registry).ok

    def test_a_production_rule_needs_a_quote(self, registry):
        d = doc(WEALTH)
        d["source"]["quote"] = ""
        result = compile_rules([d], registry)
        assert any("no quoted source text" in e.message for e in result.errors)

    def test_a_production_rule_needs_a_locator(self, registry):
        d = doc(WEALTH)
        d["source"]["locator"] = ""
        result = compile_rules([d], registry)
        assert any("no verse locator" in e.message for e in result.errors)


class TestDerivations:
    def derivation(self):
        return doc("""
            id: PAR.DERIVE.TEMPFRIEND.0001
            status: production
            school: school.parashari
            assertion: derive_fact
            domains: {}
            source:
              book: saravali
              edition: saravali.santhanam.en
              locator: ch3.v28
              quote: "If a planet is in the 2nd, 3rd, 4th, 10th, 11th or 12th from another, they are temporary friends."
              review: {reviewer: RB-001}
            dependencies: {tier: 1}
            when:
              any:
                - house_distance: {subject: "?x", other: "?y", distance: dist.02}
                - house_distance: {subject: "?x", other: "?y", distance: dist.12}
            derives:
              fact: temporal_friendship
              subject: "?x"
              object: "?y"
              value: friendship.temporary_friend
        """)

    def test_a_derivation_compiles(self, registry):
        result = compile_rules([self.derivation()], registry)
        assert result.ok, [str(e) for e in result.errors]

    def test_derivations_are_not_indexed(self, registry):
        """They execute exhaustively in tier order; retrieval never sees them."""
        result = compile_rules([doc(WEALTH), self.derivation()], registry)
        assert {v.rule_id for v in result.index.variants} == {"PAR.WEALTH.2L11H.0001"}

    def test_a_tier_inversion_fails_the_build(self, registry):
        low = self.derivation()
        high = doc("""
            id: PAR.DERIVE.COMPOSITE.0001
            status: production
            school: school.parashari
            assertion: derive_fact
            domains: {}
            source: {book: saravali, edition: e, locator: l, quote: q, review: {reviewer: RB-001}}
            dependencies: {tier: 0, reads: [temporal_friendship]}
            when:
              temporal_friendship:
                {subject: "?x", other: "?y", friendship: friendship.temporary_friend}
            derives:
              fact: composite_friendship
              subject: "?x"
              object: "?y"
              value: friendship.friend
        """)
        result = compile_rules([low, high], registry)
        assert any("cycle or inversion" in e.message for e in result.errors)


class TestRestriction:
    def test_longevity_rules_can_be_marked_unreachable_at_extraction(self, registry):
        d = doc(WEALTH)
        d["id"] = "BJ.LONGEVITY.0001"
        d["restriction"] = "never_user_facing"
        d["binding"] = "quantified"
        d["indicates"] = {
            "claim": "longevity.span", "polarity": "negative",
            "magnitude": "extreme", "text": "the child lives for four years",
            "quantity": 4, "unit": "years", "bound": "exact",
        }
        result = compile_rules([d], registry)
        assert result.ok, [str(e) for e in result.errors]
        assert result.rules[0].qualifiers.restriction is Restriction.NEVER_USER_FACING
