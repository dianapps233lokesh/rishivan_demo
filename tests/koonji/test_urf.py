"""The closed core is closed. These tests are the fence around it.

If a change makes one of these fail, that is not a broken test - it is a frame
change, which UNIVERSAL_FRAME.md Part 4 calls a genuine architectural event.
"""

import pytest
from pydantic import ValidationError

from rishivan.koonji.urf import (
    AssertionKind,
    Antecedent,
    AttributeConsequent,
    BoolExpr,
    ClaimConsequent,
    ConsequentBinding,
    Dependencies,
    FactConsequent,
    Modality,
    PredicateCall,
    Provenance,
    Qualifiers,
    RegistryKind,
    Restriction,
    Rule,
    project_tcode,
    validate_registry_closure,
    validate_stratification,
    validate_targets,
)


def leaf(predicate: str, **args) -> BoolExpr:
    return BoolExpr(op="leaf", leaf=PredicateCall(predicate=predicate, args=args))


def provenance(**kw) -> Provenance:
    base = dict(
        book_id="bphs",
        edition_id="bphs.gcs1984.en",
        locator="ch34.v12",
        quoted_text="The 2nd lord in the 11th gives wealth.",
    )
    base.update(kw)
    return Provenance(**base)


def claim_rule(rule_id="PAR.WEALTH.0001", **kw) -> Rule:
    fields = dict(
        rule_id=rule_id,
        registry_version="1.0.0",
        school="school.parashari",
        domains={"domain.wealth": 0.95},
        antecedent=Antecedent(
            expr=BoolExpr(
                op="all",
                operands=[leaf("occupies_bhava", subject="lord.bhava.02", bhava="bhava.11")],
            )
        ),
        assertion=AssertionKind.ASSERT_CLAIM,
        consequent=ClaimConsequent(
            claim_id="wealth.accumulation",
            polarity="positive",
            magnitude="strong",
            literal_text="gives wealth",
        ),
        provenance=provenance(),
    )
    fields.update(kw)
    return Rule(**fields)


class TestSevenKinds:
    def test_exactly_seven_assertion_kinds(self):
        assert len(list(AssertionKind)) == 7

    def test_every_kind_is_routed(self):
        from rishivan.koonji.urf import (
            NON_SERVING_KINDS,
            ONTOLOGY_KINDS,
            REMEDY_KINDS,
            SERVING_KINDS,
        )

        routed = SERVING_KINDS | ONTOLOGY_KINDS | REMEDY_KINDS | NON_SERVING_KINDS
        assert routed == set(AssertionKind), "a kind with no destination is a leak"


class TestConsequentPairing:
    """A DERIVE_FACT rule carrying a ClaimConsequent produces no atom and
    starves every rule downstream of it. Silently. So it cannot be built."""

    def test_mismatched_consequent_is_rejected(self):
        with pytest.raises(ValidationError, match="requires FactConsequent"):
            claim_rule(
                assertion=AssertionKind.DERIVE_FACT,
                dependencies=Dependencies(tier=1, produces=["natural_nature"]),
            )

    def test_derivation_must_declare_what_it_produces(self):
        with pytest.raises(ValidationError, match="does not declare it"):
            claim_rule(
                assertion=AssertionKind.DERIVE_FACT,
                consequent=FactConsequent(
                    fact_predicate="functional_nature",
                    subject_expr="graha.mars",
                    value="nature.benefic",
                ),
                dependencies=Dependencies(tier=2, produces=[]),
            )


class TestBoolExprShape:
    def test_leaf_requires_a_predicate_call(self):
        with pytest.raises(ValidationError, match="requires `leaf`"):
            BoolExpr(op="leaf")

    def test_not_takes_exactly_one_operand(self):
        with pytest.raises(ValidationError, match="exactly one operand"):
            BoolExpr(op="not", operands=[leaf("combust", subject="graha.sun"), leaf("retrograde", subject="graha.mars")])

    def test_count_requires_its_threshold(self):
        with pytest.raises(ValidationError, match="count_op and count_n"):
            BoolExpr(op="count", operands=[leaf("in_kendra", subject="graha.mars")])


class TestRegistryClosure:
    def closure(self, **overrides):
        base = {
            RegistryKind.PREDICATE: {"occupies_bhava", "dignity"},
            RegistryKind.CLAIM: {"wealth.accumulation"},
            RegistryKind.OBSERVABLE: {"chart"},
            RegistryKind.UNIT: {"years"},
            RegistryKind.ENTITY: {"domain.wealth"},
            RegistryKind.NAMESPACE: {"school.parashari"},
        }
        base.update(overrides)
        return base

    def test_a_closed_rule_passes(self):
        assert validate_registry_closure(claim_rule(), self.closure()) == []

    def test_a_claim_id_in_the_domain_slot_is_rejected(self):
        """An extractor produces `domains: {obstacle.general: 0.9}` readily, and
        it used to compile. The rule then indexes, and is excluded by every
        domain filter forever - nothing fires, nothing errors, and the rule's
        absence from an answer is invisible."""
        rule = claim_rule(domains={"obstacle.general": 0.9})
        errors = validate_registry_closure(rule, self.closure())
        assert any("is not a domain" in e for e in errors)

    def test_an_unregistered_domain_is_rejected(self):
        rule = claim_rule(domains={"domain.gardening": 0.9})
        errors = validate_registry_closure(rule, self.closure())
        assert any("unregistered domain" in e for e in errors)

    def test_an_unregistered_school_is_rejected(self):
        """`school.parashri` is excluded by the school filter forever."""
        rule = claim_rule(school="school.parashri")
        errors = validate_registry_closure(rule, self.closure())
        assert any("unregistered school" in e for e in errors)

    def test_a_partial_closure_does_not_invent_errors(self):
        """Callers hand-build closure dicts. An absent kind means "not supplied",
        not "nothing is registered"."""
        partial = {RegistryKind.PREDICATE: {"occupies_bhava", "dignity"},
                   RegistryKind.CLAIM: {"wealth.accumulation"},
                   RegistryKind.OBSERVABLE: {"chart"}}
        assert validate_registry_closure(claim_rule(), partial) == []

    def test_unregistered_predicate_is_an_error_not_a_warning(self):
        rule = claim_rule(
            antecedent=Antecedent(expr=leaf("prashna.touches", subject="querent"))
        )
        errors = validate_registry_closure(rule, self.closure())
        assert any("should have been an ExtensionProposal" in e for e in errors)

    def test_unregistered_claim_is_caught(self):
        rule = claim_rule(
            consequent=ClaimConsequent(
                claim_id="wealth.lottery_win",
                polarity="positive",
                magnitude="extreme",
                literal_text="wins",
            )
        )
        errors = validate_registry_closure(rule, self.closure())
        assert any("wealth.lottery_win" in e for e in errors)

    def test_cancellation_without_a_target_is_caught(self):
        rule = claim_rule(qualifiers=Qualifiers(modality=Modality.CANCEL))
        errors = validate_registry_closure(rule, self.closure())
        assert any("requires targets_rule" in e for e in errors)

    def test_modifier_without_a_factor_is_caught(self):
        rule = claim_rule(
            qualifiers=Qualifiers(
                modality=Modality.STRENGTHEN, targets_rule="PAR.WEALTH.0001"
            )
        )
        errors = validate_registry_closure(rule, self.closure())
        assert any("requires a factor" in e for e in errors)


class TestStratification:
    def derivation(self, rule_id, tier, reads, produces):
        return claim_rule(
            rule_id=rule_id,
            assertion=AssertionKind.DERIVE_FACT,
            consequent=FactConsequent(
                fact_predicate=produces[0],
                subject_expr="graha.mars",
                value="friendship.friend",
            ),
            dependencies=Dependencies(tier=tier, reads=reads, produces=produces),
        )

    def test_ordered_tiers_pass(self):
        rules = [
            self.derivation("D1", 1, [], ["temporal_friendship"]),
            self.derivation("D2", 2, ["temporal_friendship"], ["composite_friendship"]),
        ]
        assert validate_stratification(rules) == []

    def test_inversion_is_caught(self):
        """Composite friendship computed before temporal friendship reads a
        stale fact and every dignity downstream is wrong."""
        rules = [
            self.derivation("D1", 2, [], ["temporal_friendship"]),
            self.derivation("D2", 1, ["temporal_friendship"], ["composite_friendship"]),
        ]
        errors = validate_stratification(rules)
        assert any("cycle or inversion" in e for e in errors)

    def test_a_fact_produced_at_two_tiers_is_caught(self):
        rules = [
            self.derivation("D1", 1, [], ["temporal_friendship"]),
            self.derivation("D2", 2, [], ["temporal_friendship"]),
        ]
        errors = validate_stratification(rules)
        assert any("exactly one production tier" in e for e in errors)


class TestTargets:
    def test_cancellation_pointing_at_a_renamed_rule_is_caught(self):
        """Dead code that looks like a working safety net."""
        rules = [
            claim_rule(rule_id="PAR.WEALTH.0001"),
            claim_rule(
                rule_id="PAR.WEALTH.0001.C1",
                qualifiers=Qualifiers(
                    modality=Modality.CANCEL, targets_rule="PAR.WEALTH.0009"
                ),
            ),
        ]
        errors = validate_targets(rules)
        assert any("targets unknown rule" in e for e in errors)


class TestTCodeProjection:
    """The T-codes are a reporting view. Nothing in the engine depends on them,
    but astrologers read them, so the projection must be stable."""

    def test_lordship(self):
        rule = claim_rule(
            antecedent=Antecedent(
                expr=leaf("occupies_bhava", subject="lord.bhava.02", bhava="bhava.11")
            )
        )
        assert project_tcode(rule) == "T4_lordship"

    def test_placement(self):
        rule = claim_rule(
            antecedent=Antecedent(
                expr=leaf("occupies_bhava", subject="graha.sun", bhava="bhava.10")
            )
        )
        assert project_tcode(rule) == "T3_placement"

    def test_cancellation_wins_over_antecedent_shape(self):
        rule = claim_rule(
            qualifiers=Qualifiers(modality=Modality.CANCEL, targets_rule="X")
        )
        assert project_tcode(rule) == "T10_cancellation"

    def test_derivation(self):
        rule = claim_rule(
            assertion=AssertionKind.DERIVE_FACT,
            consequent=FactConsequent(
                fact_predicate="functional_nature",
                subject_expr="graha.mars",
                value="nature.benefic",
            ),
            dependencies=Dependencies(tier=2, produces=["functional_nature"]),
        )
        assert project_tcode(rule) == "T17_derivation"

    def test_signification_set(self):
        rule = claim_rule(
            assertion=AssertionKind.DEFINE_ATTRIBUTE,
            consequent=AttributeConsequent(
                entity_expr="bhava.11",
                attribute="signifies",
                values=["gains", "income", "elder_sibling", "knees", "ears", "painting"],
            ),
        )
        assert project_tcode(rule) == "T18_signification_set"

    def test_observational(self):
        rule = claim_rule(
            antecedent=Antecedent(
                expr=leaf("occupies_bhava", subject="graha.sun", bhava="bhava.10"),
                observables_required=["breath"],
            )
        )
        assert project_tcode(rule) == "T20_observational"

    def test_quantified(self):
        rule = claim_rule(
            qualifiers=Qualifiers(binding=ConsequentBinding.QUANTIFIED),
            consequent=ClaimConsequent(
                claim_id="longevity.span",
                polarity="negative",
                magnitude="extreme",
                literal_text="the child lives for 4 years",
                quantity=4,
                unit="years",
                bound="exact",
            ),
        )
        assert project_tcode(rule) == "T21_quantified_outcome"


class TestContentHash:
    def test_logic_change_changes_the_hash(self):
        a = claim_rule()
        b = claim_rule(
            antecedent=Antecedent(
                expr=BoolExpr(
                    op="all",
                    operands=[
                        leaf("occupies_bhava", subject="lord.bhava.02", bhava="bhava.10")
                    ],
                )
            )
        )
        assert a.content_hash() != b.content_hash()

    def test_reciting_the_same_logic_from_another_book_hashes_alike(self):
        """Restatement detection leans on this: same logic, different source,
        same hash. Saravali and BPHS agreeing is ONE piece of evidence."""
        a = claim_rule(rule_id="PAR.WEALTH.0001", provenance=provenance(book_id="bphs"))
        b = claim_rule(
            rule_id="SAR.WEALTH.0044",
            provenance=provenance(book_id="saravali", locator="ch10.v3"),
        )
        assert a.content_hash() == b.content_hash()


class TestRestriction:
    def test_longevity_can_be_marked_unreachable_from_serving(self):
        """CORPUS_ANALYSIS gap 5: handle death timing at extraction, not at the
        output filter. A filter you cannot accidentally remove beats one you
        have to remember to apply."""
        rule = claim_rule(
            qualifiers=Qualifiers(restriction=Restriction.NEVER_USER_FACING)
        )
        assert rule.qualifiers.restriction is Restriction.NEVER_USER_FACING
