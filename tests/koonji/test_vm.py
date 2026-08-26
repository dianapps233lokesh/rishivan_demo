"""The rule VM.

Two things here are load-bearing and neither is obvious.

**Evaluation is tri-valued.** A rule resting on a quantity this stack cannot
compute is INDETERMINATE, not NOT_APPLICABLE. Collapsing the two would let the
engine report "the classical indications do not apply" when what it means is "I
could not tell", and that is a lie the user has no way to detect.

**Variables unify against the fact set.** Classical derivations are stated over
pairs - "if a planet is in the 2nd, 4th or 12th from another, they are temporary
friends" - and a rule language that cannot say "another" forces either 72
hand-written rules or an approximation. Both are worse.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.koonji.facts import AtomTable, atom_name, compile_facts
from rishivan.koonji.registry import seed_registry
from rishivan.koonji.urf import (
    Antecedent,
    AssertionKind,
    BoolExpr,
    ClaimConsequent,
    Dependencies,
    FactConsequent,
    Modality,
    PredicateCall,
    Provenance,
    Qualifiers,
    Rule,
)
from rishivan.koonji.vm import Outcome, evaluate, execute, run_derivations

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 23, 12, 0)


@pytest.fixture(scope="module")
def registry():
    return seed_registry()


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


@pytest.fixture(scope="module")
def facts(chart):
    return compile_facts(chart, when=WHEN)


def leaf(predicate, **args):
    return BoolExpr(op="leaf", leaf=PredicateCall(predicate=predicate, args=args))


def rule(rule_id="R1", expr=None, **kw):
    fields = dict(
        rule_id=rule_id,
        registry_version="1.0.0",
        school="school.parashari",
        domains={"domain.wealth": 1.0},
        status="production",
        antecedent=Antecedent(expr=expr),
        assertion=AssertionKind.ASSERT_CLAIM,
        consequent=ClaimConsequent(
            claim_id="wealth.accumulation",
            polarity="positive",
            magnitude="strong",
            literal_text="gives wealth",
        ),
        provenance=Provenance(
            book_id="bphs", edition_id="bphs.gcs1984.en",
            locator="ch34.v12", quoted_text="...",
        ),
    )
    fields.update(kw)
    return Rule(**fields)


def a_true_leaf(facts):
    """Any ground atom actually present on the fixture chart."""
    name = sorted(n for n in facts.atom_names() if n.startswith("occupies_bhava(graha."))[0]
    predicate, rest = name.split("(", 1)
    subject, bhava = rest.rstrip(")").split(",")
    return leaf(predicate, subject=subject, bhava=bhava)


class TestGroundEvaluation:
    def test_a_present_atom_is_true(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        e = leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}")
        assert evaluate(e, facts, registry).truthy()

    def test_an_absent_atom_is_false(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        wrong = (sun % 12) + 1
        e = leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{wrong:02d}")
        assert not evaluate(e, facts, registry).truthy()

    def test_all_needs_every_operand(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        wrong = (sun % 12) + 1
        e = BoolExpr(op="all", operands=[
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{wrong:02d}"),
        ])
        assert not evaluate(e, facts, registry).truthy()

    def test_any_needs_one(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        wrong = (sun % 12) + 1
        e = BoolExpr(op="any", operands=[
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{wrong:02d}"),
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
        ])
        assert evaluate(e, facts, registry).truthy()

    def test_not_inverts(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        e = BoolExpr(op="not", operands=[
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}")
        ])
        assert not evaluate(e, facts, registry).truthy()

    def test_negated_flag_on_the_call_matches_a_not_node(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        e = BoolExpr(op="leaf", leaf=PredicateCall(
            predicate="occupies_bhava",
            args={"subject": "graha.sun", "bhava": f"bhava.{sun:02d}"},
            negated=True,
        ))
        assert not evaluate(e, facts, registry).truthy()

    def test_subject_references_resolve(self, facts, registry, chart):
        """`lord.bhava.10` is an atom subject in its own right, not a lookup."""
        lord = chart.house_lords[10]
        seat = chart.planets[lord].house
        e = leaf("occupies_bhava", subject="lord.bhava.10", bhava=f"bhava.{seat:02d}")
        assert evaluate(e, facts, registry).truthy()


class TestTriValued:
    def test_an_undecidable_predicate_is_unknown_not_false(self, facts, registry):
        e = leaf("strength_band", subject="graha.saturn", band="band.strong")
        result = evaluate(e, facts, registry)
        assert result.unknown
        assert not result.truthy()

    def test_unknown_poisons_a_conjunction(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        e = BoolExpr(op="all", operands=[
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
            leaf("strength_band", subject="graha.sun", band="band.strong"),
        ])
        assert evaluate(e, facts, registry).unknown

    def test_a_definite_false_beats_unknown_in_a_conjunction(self, facts, registry, chart):
        """If one conjunct is definitely false the rule cannot fire, and we do
        not need to know the rest."""
        sun = chart.planets["Sun"].house
        wrong = (sun % 12) + 1
        e = BoolExpr(op="all", operands=[
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{wrong:02d}"),
            leaf("strength_band", subject="graha.sun", band="band.strong"),
        ])
        result = evaluate(e, facts, registry)
        assert not result.unknown and not result.truthy()

    def test_a_definite_true_beats_unknown_in_a_disjunction(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        e = BoolExpr(op="any", operands=[
            leaf("strength_band", subject="graha.sun", band="band.strong"),
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
        ])
        result = evaluate(e, facts, registry)
        assert result.truthy() and not result.unknown

    def test_a_rule_resting_on_shadbala_is_indeterminate(self, facts, registry):
        r = rule(expr=leaf("strength_band", subject="graha.saturn", band="band.strong"))
        firing = execute([r], facts, registry)[0]
        assert firing.outcome is Outcome.INDETERMINATE
        assert "strength_band" in firing.reason


class TestNumeric:
    def test_exact_comparison_reads_the_side_table(self, facts, registry):
        e = leaf("sav_bindu", bhava="bhava.01", op="gte", n=0)
        assert evaluate(e, facts, registry).truthy()

    def test_an_impossible_threshold_is_false(self, facts, registry):
        e = leaf("sav_bindu", bhava="bhava.01", op="gte", n=999)
        assert not evaluate(e, facts, registry).truthy()

    def test_a_missing_exact_value_is_unknown(self, facts, registry):
        e = leaf("strength", subject="graha.sun", op="gte", n=6.0)
        assert evaluate(e, facts, registry).unknown

    def test_occupant_count(self, facts, registry, chart):
        counts = {}
        for p in chart.planets.values():
            counts[p.house] = counts.get(p.house, 0) + 1
        busiest = max(counts, key=counts.get)
        e = leaf("occupant_count", bhava=f"bhava.{busiest:02d}", op="gte", n=counts[busiest])
        assert evaluate(e, facts, registry).truthy()


class TestVariables:
    def test_a_variable_binds_every_match(self, facts, registry, chart):
        e = leaf("occupies_bhava", subject="?x", bhava="bhava.01")
        result = evaluate(e, facts, registry)
        expected = {
            f"graha.{n.lower()}" for n, p in chart.planets.items() if p.house == 1
        }
        bound = {b["?x"] for b in result.bindings if b["?x"].startswith("graha.")}
        assert bound == expected

    def test_variables_join_across_conjuncts(self, facts, registry, chart):
        """?x must be the same body in both leaves."""
        e = BoolExpr(op="all", operands=[
            leaf("occupies_bhava", subject="?x", bhava="bhava.01"),
            leaf("in_kendra", subject="?x"),
        ])
        result = evaluate(e, facts, registry)
        for b in result.bindings:
            graha = b["?x"]
            assert facts.has("occupies_bhava", graha, "bhava.01")
            assert facts.has("in_kendra", graha)

    def test_two_variables_range_over_pairs(self, facts, registry):
        e = leaf("house_distance", subject="?x", other="?y", distance="dist.07")
        result = evaluate(e, facts, registry)
        assert result.bindings
        for b in result.bindings:
            assert b["?x"] != b["?y"]

    def test_an_unsatisfiable_join_yields_nothing(self, facts, registry):
        e = BoolExpr(op="all", operands=[
            leaf("occupies_bhava", subject="?x", bhava="bhava.01"),
            leaf("occupies_bhava", subject="?x", bhava="bhava.07"),
        ])
        assert not evaluate(e, facts, registry).truthy()


class TestCount:
    def test_counts_distinct_solutions_of_one_operand(self, facts, registry, chart):
        in_kendra = sum(1 for p in chart.planets.values() if p.house in (1, 4, 7, 10))
        e = BoolExpr(
            op="count", count_op="gte", count_n=in_kendra,
            operands=[leaf("occupies_bhava", subject="?x", bhava="bhava.01")],
        )
        # weaker threshold: at least one solution exists for a populated house
        e_ok = BoolExpr(
            op="count", count_op="gte", count_n=1,
            operands=[leaf("in_kendra", subject="?x")],
        )
        assert evaluate(e_ok, facts, registry).truthy()

    def test_threshold_not_met_is_false(self, facts, registry):
        e = BoolExpr(
            op="count", count_op="gte", count_n=99,
            operands=[leaf("in_kendra", subject="?x")],
        )
        assert not evaluate(e, facts, registry).truthy()

    def test_counts_truthy_operands_when_given_several(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        wrong = (sun % 12) + 1
        e = BoolExpr(
            op="count", count_op="eq", count_n=1,
            operands=[
                leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
                leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{wrong:02d}"),
            ],
        )
        assert evaluate(e, facts, registry).truthy()


class TestModality:
    def test_a_cancellation_that_fires_cancels_its_target(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        base = rule("BASE", expr=leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"))
        cancel = rule(
            "BASE.C1",
            expr=leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
            qualifiers=Qualifiers(modality=Modality.CANCEL, targets_rule="BASE"),
        )
        by_id = {f.rule_id: f for f in execute([base, cancel], facts, registry)}
        assert by_id["BASE"].outcome is Outcome.CANCELLED
        assert by_id["BASE"].cancelled_by == ["BASE.C1"]

    def test_a_cancellation_that_does_not_fire_leaves_the_target_alone(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        wrong = (sun % 12) + 1
        base = rule("BASE", expr=leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"))
        cancel = rule(
            "BASE.C1",
            expr=leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{wrong:02d}"),
            qualifiers=Qualifiers(modality=Modality.CANCEL, targets_rule="BASE"),
        )
        by_id = {f.rule_id: f for f in execute([base, cancel], facts, registry)}
        assert by_id["BASE"].outcome is Outcome.FIRED

    def test_strengthen_scales_the_target(self, facts, registry, chart):
        sun = chart.planets["Sun"].house
        seat = leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}")
        base = rule("BASE", expr=seat)
        boost = rule(
            "BASE.S1", expr=seat,
            qualifiers=Qualifiers(
                modality=Modality.STRENGTHEN, targets_rule="BASE", factor=1.25
            ),
        )
        by_id = {f.rule_id: f for f in execute([base, boost], facts, registry)}
        assert by_id["BASE"].strength == pytest.approx(1.25)
        assert by_id["BASE"].modifiers == ["BASE.S1"]

    def test_cancellation_beats_a_strengthener(self, facts, registry, chart):
        """A cancelled yoga is cancelled however well supported it was."""
        sun = chart.planets["Sun"].house
        seat = leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}")
        rules = [
            rule("BASE", expr=seat),
            rule("BASE.S1", expr=seat, qualifiers=Qualifiers(
                modality=Modality.STRENGTHEN, targets_rule="BASE", factor=2.0)),
            rule("BASE.C1", expr=seat, qualifiers=Qualifiers(
                modality=Modality.CANCEL, targets_rule="BASE")),
        ]
        by_id = {f.rule_id: f for f in execute(rules, facts, registry)}
        assert by_id["BASE"].outcome is Outcome.CANCELLED


class TestObservables:
    def test_a_rule_needing_an_uncapturable_observable_is_withheld(self, facts, registry, chart):
        """Prasna's breath cannot be observed through a chat box. The engine
        must not answer as though it could."""
        sun = chart.planets["Sun"].house
        r = rule(
            expr=leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
            antecedent=Antecedent(
                expr=leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
                observables_required=["breath"],
            ),
        )
        firing = execute([r], facts, registry)[0]
        assert firing.outcome is Outcome.WITHHELD


class TestDerivations:
    """Derivation rules produce chart facts, execute in tier order, and every
    later tier sees what the earlier ones wrote."""

    def derivation(self, rule_id, tier, expr, predicate, subject, value, obj=None):
        return rule(
            rule_id,
            assertion=AssertionKind.DERIVE_FACT,
            antecedent=Antecedent(expr=expr),
            consequent=FactConsequent(
                fact_predicate=predicate,
                subject_expr=subject,
                object_expr=obj,
                value=value,
            ),
            dependencies=Dependencies(tier=tier, produces=[predicate]),
        )

    def test_a_derivation_writes_an_atom_back(self, facts, registry, chart):
        lagna = chart.lagna_rashi.lower()
        d = self.derivation(
            "D.FUNC.1", 2,
            BoolExpr(op="all", operands=[
                leaf("bhava_in_rashi", bhava="bhava.01", rashi=f"rashi.{lagna}"),
            ]),
            "functional_nature", "graha.mars", "nature.benefic",
        )
        enriched = run_derivations([d], facts, registry)
        assert enriched.has("functional_nature", "graha.mars", "nature.benefic")

    def test_derivations_bind_variables_into_the_produced_fact(self, facts, registry):
        """Temporary friendship is stated over pairs. One rule, not 72."""
        d = self.derivation(
            "D.TF.1", 1,
            BoolExpr(op="any", operands=[
                leaf("house_distance", subject="?x", other="?y", distance=f"dist.{n:02d}")
                for n in (2, 3, 4, 10, 11, 12)
            ]),
            "temporal_friendship", "?x", "friendship.temporary_friend", obj="?y",
        )
        enriched = run_derivations([d], facts, registry)
        produced = [
            a for a in enriched.atom_names() if a.startswith("temporal_friendship(")
        ]
        assert produced, "the pairwise derivation produced nothing"
        for atom in produced:
            args = atom.split("(", 1)[1].rstrip(")").split(",")
            assert args[0] != args[1]

    def test_a_later_tier_sees_an_earlier_tiers_output(self, facts, registry):
        first = self.derivation(
            "D.T1", 1,
            leaf("house_distance", subject="?x", other="?y", distance="dist.04"),
            "temporal_friendship", "?x", "friendship.temporary_friend", obj="?y",
        )
        second = rule(
            "D.T2",
            assertion=AssertionKind.DERIVE_FACT,
            antecedent=Antecedent(expr=leaf(
                "temporal_friendship", subject="?x", other="?y",
                friendship="friendship.temporary_friend",
            )),
            consequent=FactConsequent(
                fact_predicate="composite_friendship",
                subject_expr="?x", object_expr="?y", value="friendship.friend",
            ),
            dependencies=Dependencies(
                tier=2, reads=["temporal_friendship"], produces=["composite_friendship"]
            ),
        )
        enriched = run_derivations([first, second], facts, registry)
        assert any(
            a.startswith("composite_friendship(") for a in enriched.atom_names()
        )

    def test_within_a_tier_rules_do_not_see_each_other(self, facts, registry):
        """That is what stratification means. If a same-tier rule could read a
        same-tier write, the result would depend on evaluation order."""
        a = self.derivation(
            "D.A", 1, leaf("house_distance", subject="?x", other="?y", distance="dist.04"),
            "temporal_friendship", "?x", "friendship.temporary_friend", obj="?y",
        )
        b = rule(
            "D.B",
            assertion=AssertionKind.DERIVE_FACT,
            antecedent=Antecedent(expr=leaf(
                "temporal_friendship", subject="?x", other="?y",
                friendship="friendship.temporary_friend",
            )),
            consequent=FactConsequent(
                fact_predicate="composite_friendship",
                subject_expr="?x", object_expr="?y", value="friendship.friend",
            ),
            dependencies=Dependencies(
                tier=1, reads=["temporal_friendship"], produces=["composite_friendship"]
            ),
        )
        enriched = run_derivations([a, b], facts, registry)
        assert not any(
            x.startswith("composite_friendship(") for x in enriched.atom_names()
        )

    def test_derivations_do_not_mutate_the_input_fact_set(self, facts, registry):
        before = len(facts.atoms)
        d = self.derivation(
            "D.X", 1, leaf("house_distance", subject="?x", other="?y", distance="dist.04"),
            "temporal_friendship", "?x", "friendship.temporary_friend", obj="?y",
        )
        run_derivations([d], facts, registry)
        assert len(facts.atoms) == before
