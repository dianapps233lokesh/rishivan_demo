"""The independence factor, and the willingness to report against yourself.

Everything in this file is an invariant rather than a number. The exact
confidence a formula returns is a tuning decision; that a paraphrase must not
raise it, and that counter-evidence must not disappear, are not.
"""

import pytest

from rishivan.koonji.evidence import (
    INDEPENDENCE_DISCOUNT,
    INSUFFICIENT_BELOW,
    band_for,
    build_evidence,
    cluster_restatements,
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


def rule(
    rule_id,
    *,
    school="school.parashari",
    book="bphs",
    locator="ch34.v12",
    magnitude="strong",
    polarity="positive",
    claim="wealth.accumulation",
    tier="S0",
    restates=(),
    bhava="bhava.11",
    corroboration_n=None,
    requires_activation=False,
):
    return Rule(
        rule_id=rule_id,
        registry_version="1.0.0",
        school=school,
        domains={"domain.wealth": 1.0},
        status="production",
        antecedent=Antecedent(expr=BoolExpr(
            op="leaf",
            leaf=PredicateCall(
                predicate="occupies_bhava",
                args={"subject": "lord.bhava.02", "bhava": bhava},
            ),
        )),
        assertion=AssertionKind.ASSERT_CLAIM,
        consequent=ClaimConsequent(
            claim_id=claim, polarity=polarity,
            magnitude=magnitude, literal_text="…",
        ),
        qualifiers=Qualifiers(
            corroboration=(
                Corroboration.REQUIRES_N if corroboration_n else Corroboration.STANDALONE
            ),
            corroboration_n=corroboration_n,
            requires_activation=requires_activation,
        ),
        provenance=Provenance(
            book_id=book, edition_id=f"{book}.ed", locator=locator,
            quoted_text="…", authority_tier=tier, restates=list(restates),
        ),
    )


def fired(rule_id, strength=1.0):
    return Firing(
        rule_id=rule_id, version="1.0.0", outcome=Outcome.FIRED, strength=strength
    )


class TestClustering:
    def test_declared_restatements_cluster(self):
        rules = [rule("A"), rule("B", book="saravali", restates=["A"])]
        clusters = cluster_restatements(rules)
        assert clusters["A"] == clusters["B"]

    def test_identical_logic_in_one_school_clusters_without_being_told(self):
        """Two independently extracted rules with the same core and the same
        claim are the same statement, whether or not anybody noticed."""
        rules = [rule("A"), rule("B", book="saravali")]
        clusters = cluster_restatements(rules)
        assert clusters["A"] == clusters["B"]

    def test_identical_logic_across_schools_does_not_cluster(self):
        """Two doctrines reaching the same conclusion by different reasoning is
        real corroboration, and the most valuable kind there is."""
        rules = [rule("A"), rule("J", school="school.jaimini")]
        clusters = cluster_restatements(rules)
        assert clusters["A"] != clusters["J"]

    def test_different_logic_does_not_cluster(self):
        rules = [rule("A", bhava="bhava.11"), rule("B", bhava="bhava.02")]
        clusters = cluster_restatements(rules)
        assert clusters["A"] != clusters["B"]

    def test_clustering_is_transitive(self):
        rules = [
            rule("A", bhava="bhava.11"),
            rule("B", book="saravali", bhava="bhava.05", restates=["A"]),
            rule("C", book="jataka", bhava="bhava.09", restates=["B"]),
        ]
        clusters = cluster_restatements(rules)
        assert clusters["A"] == clusters["B"] == clusters["C"]

    def test_cluster_names_are_stable_across_ordering(self):
        rules = [rule("A"), rule("B", book="saravali", restates=["A"])]
        assert cluster_restatements(rules) == cluster_restatements(list(reversed(rules)))


class TestIndependence:
    """The headline property. This is the difference between an engine that
    sounds certain about everything and one worth believing."""

    def test_a_paraphrase_does_not_raise_confidence_like_a_new_source(self):
        one = build_evidence([fired("A")], [rule("A")])
        paraphrased = build_evidence(
            [fired("A"), fired("B")],
            [rule("A"), rule("B", book="saravali", restates=["A"])],
        )
        independent = build_evidence(
            [fired("A"), fired("J")],
            [rule("A"), rule("J", school="school.jaimini", book="jaimini")],
        )
        assert (
            one.max_confidence
            < paraphrased.max_confidence
            < independent.max_confidence
        ), "a restatement must be worth less than a genuine second doctrine"

    def test_the_restatement_is_marked_and_discounted(self):
        graph = build_evidence(
            [fired("A"), fired("B")],
            [rule("A"), rule("B", book="saravali", restates=["A"])],
        )
        edges = {e.rule_id: e for e in graph.claims[0].support}
        discounted = [e for e in edges.values() if not e.independent]
        assert len(discounted) == 1
        edge = discounted[0]
        assert edge.effective_weight == pytest.approx(
            edge.raw_weight * INDEPENDENCE_DISCOUNT
        )

    def test_the_strongest_member_of_a_cluster_keeps_full_weight(self):
        graph = build_evidence(
            [fired("A"), fired("B")],
            [
                rule("A", magnitude="moderate"),
                rule("B", book="saravali", magnitude="extreme", restates=["A"]),
            ],
        )
        by_id = {e.rule_id: e for e in graph.claims[0].support}
        assert by_id["B"].independent
        assert not by_id["A"].independent

    def test_ten_paraphrases_do_not_manufacture_certainty(self):
        rules = [rule("A")] + [
            rule(f"R{i}", book=f"book{i}", restates=["A"]) for i in range(10)
        ]
        graph = build_evidence([fired(r.rule_id) for r in rules], rules)
        assert graph.claims[0].independent_sources == 1
        assert graph.claims[0].confidence < 0.85

    def test_independent_source_count_is_reported(self):
        rules = [rule("A"), rule("J", school="school.jaimini", book="jaimini")]
        graph = build_evidence([fired(r.rule_id) for r in rules], rules)
        assert graph.claims[0].independent_sources == 2


class TestCounterEvidence:
    def test_counter_evidence_is_kept_not_dropped(self):
        rules = [rule("A"), rule("N", bhava="bhava.06", polarity="negative", book="saravali")]
        graph = build_evidence([fired("A"), fired("N")], rules)
        claim = graph.claims[0]
        assert claim.has_counterevidence
        assert [e.rule_id for e in claim.against] == ["N"]

    def test_counter_evidence_lowers_confidence(self):
        supportive = build_evidence([fired("A")], [rule("A")])
        contested = build_evidence(
            [fired("A"), fired("N")],
            [rule("A"), rule("N", bhava="bhava.06", polarity="negative", book="saravali")],
        )
        assert contested.max_confidence < supportive.max_confidence

    def test_counter_evidence_is_cited_alongside_the_support(self):
        rules = [rule("A"), rule("N", bhava="bhava.06", polarity="negative", book="saravali")]
        graph = build_evidence([fired("A"), fired("N")], rules)
        assert "saravali ch34.v12" in graph.claims[0].citations()


class TestOutcomes:
    def test_a_cancelled_rule_contributes_nothing(self):
        rules = [rule("A")]
        cancelled = Firing(
            rule_id="A", version="1.0.0", outcome=Outcome.CANCELLED,
            cancelled_by=["A.C1"],
        )
        graph = build_evidence([cancelled], rules)
        assert graph.claims == []
        assert graph.cancelled == ["A"]

    def test_indeterminate_rules_are_recorded_but_not_counted(self):
        """A rule we could not evaluate is not a rule that did not apply, and
        the trace has to keep the difference."""
        rules = [rule("A")]
        graph = build_evidence(
            [Firing(rule_id="A", version="1.0.0", outcome=Outcome.INDETERMINATE)],
            rules,
        )
        assert graph.indeterminate == ["A"]
        assert graph.claims == []

    def test_withheld_rules_are_recorded_but_not_counted(self):
        rules = [rule("A")]
        graph = build_evidence(
            [Firing(rule_id="A", version="1.0.0", outcome=Outcome.WITHHELD)], rules
        )
        assert graph.withheld == ["A"]
        assert graph.claims == []

    def test_modifier_strength_scales_the_contribution(self):
        plain = build_evidence([fired("A")], [rule("A")])
        boosted = build_evidence([fired("A", strength=1.5)], [rule("A")])
        assert boosted.max_confidence > plain.max_confidence


class TestCorroboration:
    def test_an_unmet_corroboration_floor_caps_the_claim(self):
        """The author asked for two independent sources. One does not become
        two because the answer would read better."""
        graph = build_evidence(
            [fired("A")], [rule("A", corroboration_n=2)]
        )
        claim = graph.claims[0]
        assert not claim.corroboration_met
        assert claim.confidence <= INSUFFICIENT_BELOW

    def test_a_met_corroboration_floor_does_not_cap(self):
        rules = [
            rule("A", corroboration_n=2),
            rule("J", school="school.jaimini", book="jaimini", corroboration_n=2),
        ]
        graph = build_evidence([fired("A"), fired("J")], rules)
        assert graph.claims[0].corroboration_met
        assert graph.claims[0].confidence > INSUFFICIENT_BELOW

    def test_paraphrases_do_not_satisfy_a_corroboration_floor(self):
        """Otherwise the floor is trivially cleared by finding the same verse
        quoted in a second book, which is not what it is for."""
        rules = [
            rule("A", corroboration_n=2),
            rule("B", book="saravali", restates=["A"], corroboration_n=2),
        ]
        graph = build_evidence([fired("A"), fired("B")], rules)
        assert not graph.claims[0].corroboration_met


class TestAuthority:
    def test_a_secondary_source_weighs_less_than_a_primary(self):
        primary = build_evidence([fired("A")], [rule("A", tier="S0")])
        secondary = build_evidence([fired("A")], [rule("A", tier="S3")])
        assert secondary.max_confidence < primary.max_confidence


class TestBands:
    def test_language_tracks_the_number(self):
        assert band_for(0.2)[0] == "some_indications"
        assert band_for(0.5)[0] == "moderately_supported"
        assert band_for(0.75)[0] == "strongly_indicated"
        assert band_for(0.95)[0] == "consistently_supported"

    def test_no_band_promises_certainty(self):
        for ceiling in (0.1, 0.5, 0.8, 0.99):
            phrasing = band_for(ceiling)[1]
            assert "will" not in phrasing and "definitely" not in phrasing

    def test_confidence_never_reaches_one(self):
        rules = [
            rule(f"S{i}", school=f"school.s{i}", book=f"b{i}", magnitude="extreme")
            for i in range(30)
        ]
        graph = build_evidence([fired(r.rule_id) for r in rules], rules)
        assert graph.max_confidence < 1.0


class TestInsufficient:
    def test_no_firings_is_insufficient(self):
        assert build_evidence([], []).insufficient()

    def test_weak_evidence_is_insufficient(self):
        graph = build_evidence(
            [fired("A")], [rule("A", magnitude="slight", tier="S3")]
        )
        assert graph.insufficient()

    def test_strong_evidence_is_not_insufficient(self):
        rules = [
            rule("A"),
            rule("J", school="school.jaimini", book="jaimini"),
            rule("K", school="school.tajika", book="tajika"),
        ]
        graph = build_evidence([fired(r.rule_id) for r in rules], rules)
        assert not graph.insufficient()


class TestActivation:
    def test_a_promise_is_marked_as_needing_activation(self):
        graph = build_evidence(
            [fired("A")], [rule("A", requires_activation=True)]
        )
        assert graph.claims[0].requires_activation

    def test_one_unconditional_rule_makes_the_claim_unconditional(self):
        rules = [
            rule("A", requires_activation=True),
            rule("J", school="school.jaimini", book="jaimini", requires_activation=False),
        ]
        graph = build_evidence([fired("A"), fired("J")], rules)
        assert not graph.claims[0].requires_activation


class TestDeterminism:
    def test_the_same_input_gives_the_same_graph(self):
        rules = [rule("A"), rule("J", school="school.jaimini", book="jaimini")]
        firings = [fired("A"), fired("J")]
        a = build_evidence(firings, rules)
        b = build_evidence(firings, rules)
        assert [(c.claim_id, c.confidence) for c in a.claims] == [
            (c.claim_id, c.confidence) for c in b.claims
        ]
