"""Retrieval is a pattern-matching problem, not a search problem.

"Which rules have preconditions this chart satisfies" has an exact, computable
answer. Semantic search answers a different question and fails silently when it
is wrong: the rule sits in the corpus, the embedding does not match, it never
fires, and nobody finds out, because you cannot measure recall against a
denominator you do not know.

So the property under test throughout this file is **no false negatives**. False
positives are free - the VM prunes them with exact values. A false negative is
invisible forever.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.koonji.facts import compile_facts
from rishivan.koonji.index import (
    EmptyCore,
    MismatchedAtomTable,
    RuleIndex,
    dnf_variants,
    extract_core,
)
from rishivan.koonji.registry import seed_registry
from rishivan.koonji.urf import (
    Antecedent,
    AssertionKind,
    BoolExpr,
    ClaimConsequent,
    PredicateCall,
    Provenance,
    Rule,
)
from rishivan.koonji.vm import execute

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090,
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


def leaf(predicate, negated=False, **args):
    return BoolExpr(
        op="leaf",
        leaf=PredicateCall(predicate=predicate, args=args, negated=negated),
    )


def rule(rule_id, expr, *, domains=None, school="school.parashari", status="production"):
    return Rule(
        rule_id=rule_id,
        registry_version="1.0.0",
        school=school,
        domains=domains if domains is not None else {"domain.wealth": 1.0},
        status=status,
        antecedent=Antecedent(expr=expr),
        assertion=AssertionKind.ASSERT_CLAIM,
        consequent=ClaimConsequent(
            claim_id="wealth.accumulation", polarity="positive",
            magnitude="strong", literal_text="gives wealth",
        ),
        provenance=Provenance(
            book_id="bphs", edition_id="bphs.gcs1984.en",
            locator="ch34.v12", quoted_text="...",
        ),
    )


class TestDNF:
    def test_a_conjunction_is_one_variant(self):
        expr = BoolExpr(op="all", operands=[
            leaf("in_kendra", subject="graha.sun"),
            leaf("in_kendra", subject="graha.moon"),
        ])
        assert len(dnf_variants(expr)) == 1

    def test_a_disjunction_becomes_one_variant_each(self):
        expr = BoolExpr(op="any", operands=[
            leaf("occupies_bhava", subject="graha.moon", bhava="bhava.04"),
            leaf("occupies_bhava", subject="graha.moon", bhava="bhava.10"),
        ])
        assert len(dnf_variants(expr)) == 2

    def test_a_disjunction_inside_a_conjunction_multiplies_out(self):
        expr = BoolExpr(op="all", operands=[
            leaf("in_kendra", subject="graha.jupiter"),
            BoolExpr(op="any", operands=[
                leaf("dignity", subject="graha.jupiter", dignity="dignity.own_sign"),
                leaf("dignity", subject="graha.jupiter", dignity="dignity.exalted"),
                leaf("dignity", subject="graha.jupiter", dignity="dignity.moolatrikona"),
            ]),
        ])
        variants = dnf_variants(expr)
        assert len(variants) == 3
        for v in variants:
            assert v.op == "all"
            assert len(v.operands) == 2

    def test_variants_share_the_rules_identity(self, registry, facts):
        """DNF is an implementation detail of retrieval. Three variants of one
        rule are one rule for provenance, or the evidence graph would triple
        count a single verse."""
        expr = BoolExpr(op="any", operands=[
            leaf("in_kendra", subject="graha.sun"),
            leaf("in_trikona", subject="graha.sun"),
        ])
        index = RuleIndex.build([rule("R1", expr)], registry)
        assert {v.rule_id for v in index.variants} == {"R1"}

    def test_explosion_is_refused(self):
        """A rule that normalises to hundreds of variants should be rewritten,
        not silently compiled into a bloated index."""
        big = BoolExpr(op="all", operands=[
            BoolExpr(op="any", operands=[
                leaf("occupies_bhava", subject=f"graha.sun", bhava=f"bhava.{n:02d}")
                for n in range(1, 5)
            ])
            for _ in range(4)
        ])
        with pytest.raises(ValueError, match="variants"):
            dnf_variants(big, limit=32)

    def test_not_of_a_disjunction_is_kept_whole(self):
        """De Morgan would turn this into a conjunction of negations, none of
        which are indexable anyway. Keeping it whole and deferring it to the VM
        is simpler and preserves the superset."""
        expr = BoolExpr(op="not", operands=[
            BoolExpr(op="any", operands=[
                leaf("combust", subject="graha.mercury"),
                leaf("retrograde", subject="graha.mercury"),
            ])
        ])
        assert len(dnf_variants(expr)) == 1


class TestCoreExtraction:
    def test_ground_positive_atoms_form_the_core(self, registry):
        expr = BoolExpr(op="all", operands=[
            leaf("occupies_bhava", subject="lord.bhava.02", bhava="bhava.11"),
            leaf("dignity", subject="lord.bhava.02", dignity="dignity.exalted"),
        ])
        core, always = extract_core(dnf_variants(expr)[0], registry)
        assert core == {
            "occupies_bhava(lord.bhava.02,bhava.11)",
            "dignity(lord.bhava.02,dignity.exalted)",
        }
        assert not always

    def test_negation_is_excluded_from_the_core(self, registry):
        """Indexing on a negative would build a core the fact set can never
        satisfy. Index the positives, get a superset, let the VM negate."""
        expr = BoolExpr(op="all", operands=[
            leaf("occupies_bhava", subject="lord.bhava.10", bhava="bhava.10"),
            leaf("combust", subject="lord.bhava.10", negated=True),
        ])
        core, _ = extract_core(dnf_variants(expr)[0], registry)
        assert core == {"occupies_bhava(lord.bhava.10,bhava.10)"}

    def test_numeric_predicates_are_excluded_from_the_core(self, registry):
        expr = BoolExpr(op="all", operands=[
            leaf("occupies_bhava", subject="graha.saturn", bhava="bhava.10"),
            leaf("sav_bindu", bhava="bhava.10", op="gte", n=30),
        ])
        core, _ = extract_core(dnf_variants(expr)[0], registry)
        assert core == {"occupies_bhava(graha.saturn,bhava.10)"}

    def test_variable_leaves_are_excluded_from_the_core(self, registry):
        expr = BoolExpr(op="all", operands=[
            leaf("occupies_bhava", subject="graha.jupiter", bhava="bhava.01"),
            leaf("conjunct", subject="graha.jupiter", other="?y"),
        ])
        core, _ = extract_core(dnf_variants(expr)[0], registry)
        assert core == {"occupies_bhava(graha.jupiter,bhava.01)"}

    def test_a_rule_with_only_non_ground_conditions_is_always_a_candidate(self, registry):
        """A threshold rule has no ground atom to index on, but it is not
        unconditional. It joins every candidate set and the VM decides."""
        expr = BoolExpr(
            op="count", count_op="gte", count_n=3,
            operands=[leaf("in_kendra", subject="?x")],
        )
        core, always = extract_core(dnf_variants(expr)[0], registry)
        assert core == set()
        assert always

    def test_an_unconditional_rule_is_refused(self, registry):
        """A rule that matches every chart is mis-authored, not permissive."""
        with pytest.raises(EmptyCore):
            RuleIndex.build([rule("R1", None)], registry)


class TestRetrieval:
    def build(self, registry, rules):
        return RuleIndex.build(rules, registry)

    def test_facts_from_another_table_are_refused(self, registry, facts, chart):
        """Same atom, two different integers. Every containment test would
        still run, and every answer would be meaningless."""
        index = self.build(registry, [
            rule("R1", leaf("occupies_bhava", subject="graha.sun", bhava="bhava.01"))
        ])
        with pytest.raises(MismatchedAtomTable):
            index.query(facts)

    def test_a_satisfied_core_is_retrieved(self, registry, facts, chart):
        seat = chart.planets["Sun"].house
        r = rule("R1", leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{seat:02d}"))
        index = self.build(registry, [r])
        assert index.query(index.facts_for(chart, when=WHEN)) == {"R1"}

    def test_an_unsatisfied_core_is_not_retrieved(self, registry, facts, chart):
        seat = chart.planets["Sun"].house
        wrong = (seat % 12) + 1
        r = rule("R1", leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{wrong:02d}"))
        index = self.build(registry, [r])
        assert index.query(index.facts_for(chart, when=WHEN)) == set()

    def test_a_partially_satisfied_core_is_not_retrieved(self, registry, facts, chart):
        seat = chart.planets["Sun"].house
        wrong = (seat % 12) + 1
        r = rule("R1", BoolExpr(op="all", operands=[
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{seat:02d}"),
            leaf("occupies_bhava", subject="graha.moon", bhava=f"bhava.{wrong:02d}"),
        ]))
        index = self.build(registry, [r])
        assert index.query(index.facts_for(chart, when=WHEN)) == set()

    def test_one_satisfied_variant_retrieves_the_rule(self, registry, facts, chart):
        seat = chart.planets["Sun"].house
        wrong = (seat % 12) + 1
        r = rule("R1", BoolExpr(op="any", operands=[
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{wrong:02d}"),
            leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{seat:02d}"),
        ]))
        index = self.build(registry, [r])
        assert index.query(index.facts_for(chart, when=WHEN)) == {"R1"}

    def test_always_candidates_are_always_returned(self, registry, chart):
        r = rule("R1", BoolExpr(
            op="count", count_op="gte", count_n=3,
            operands=[leaf("in_kendra", subject="?x")],
        ))
        index = self.build(registry, [r])
        assert index.query(index.facts_for(chart, when=WHEN)) == {"R1"}

    def test_domain_prefilter_narrows(self, registry, facts, chart):
        seat = chart.planets["Sun"].house
        expr = leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{seat:02d}")
        index = self.build(registry, [
            rule("W1", expr, domains={"domain.wealth": 1.0}),
            rule("C1", expr, domains={"domain.career": 1.0}),
        ])
        own = index.facts_for(chart, when=WHEN)
        assert index.query(own, domains={"domain.career"}) == {"C1"}
        assert index.query(own) == {"W1", "C1"}

    def test_school_prefilter_narrows(self, registry, facts, chart):
        seat = chart.planets["Sun"].house
        expr = leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{seat:02d}")
        index = self.build(registry, [
            rule("P1", expr, school="school.parashari"),
            rule("J1", expr, school="school.jaimini"),
        ])
        assert index.query(
            index.facts_for(chart, when=WHEN), schools={"school.jaimini"}
        ) == {"J1"}

    def test_non_production_rules_are_not_served(self, registry, facts, chart):
        seat = chart.planets["Sun"].house
        expr = leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{seat:02d}")
        index = self.build(registry, [rule("D1", expr, status="draft")])
        assert index.query(index.facts_for(chart, when=WHEN)) == set()


class TestNoFalseNegatives:
    """The property that matters. Retrieval must never drop a rule the VM would
    have fired - checked here by brute force against the whole rule set."""

    def rules_over_the_chart(self, chart):
        """A spread of rules: satisfied, unsatisfied, negated, numeric,
        disjunctive and variable-bearing."""
        sun = chart.planets["Sun"].house
        moon = chart.planets["Moon"].house
        wrong = (sun % 12) + 1
        return [
            rule("HIT.ground", leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}")),
            rule("MISS.ground", leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{wrong:02d}")),
            rule("HIT.conj", BoolExpr(op="all", operands=[
                leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
                leaf("occupies_bhava", subject="graha.moon", bhava=f"bhava.{moon:02d}"),
            ])),
            rule("HIT.disj", BoolExpr(op="any", operands=[
                leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{wrong:02d}"),
                leaf("occupies_bhava", subject="graha.moon", bhava=f"bhava.{moon:02d}"),
            ])),
            rule("HIT.negated", BoolExpr(op="all", operands=[
                leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
                leaf("combust", subject="graha.jupiter", negated=True),
            ])),
            rule("HIT.numeric", BoolExpr(op="all", operands=[
                leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{sun:02d}"),
                leaf("sav_bindu", bhava="bhava.01", op="gte", n=1),
            ])),
            rule("HIT.threshold", BoolExpr(
                op="count", count_op="gte", count_n=1,
                operands=[leaf("in_kendra", subject="?x")],
            )),
            rule("HIT.lord", leaf(
                "occupies_bhava", subject="lord.bhava.01",
                bhava=f"bhava.{chart.planets[chart.house_lords[1]].house:02d}",
            )),
        ]

    def test_retrieval_is_a_superset_of_what_actually_fires(self, registry, chart):
        rules = self.rules_over_the_chart(chart)
        index = RuleIndex.build(rules, registry)
        facts = index.facts_for(chart, when=WHEN)
        retrieved = index.query(facts)

        fired = {
            f.rule_id for f in execute(rules, facts, registry) if f.counts
        }
        missed = fired - retrieved
        assert not missed, f"retrieval dropped rules that fire: {sorted(missed)}"

    def test_retrieval_actually_narrows(self, registry, chart):
        """A superset that is the whole corpus is correct and useless."""
        rules = self.rules_over_the_chart(chart)
        index = RuleIndex.build(rules, registry)
        assert len(index.query(index.facts_for(chart, when=WHEN))) < len(rules)


class TestStats:
    def test_index_reports_its_shape(self, registry, facts, chart):
        seat = chart.planets["Sun"].house
        index = RuleIndex.build(
            [rule("R1", leaf("occupies_bhava", subject="graha.sun", bhava=f"bhava.{seat:02d}"))],
            registry,
        )
        stats = index.stats()
        assert stats["rules"] == 1
        assert stats["variants"] == 1
        assert stats["postings"] >= 1
