"""End to end: a birth date in, cited claims out, no model involved.

This is the M0 acceptance test made permanent - "you can POST a birth date and
see a rule fire with its source citation" - plus the properties that only show
up once the whole path is wired.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.koonji.engine import DEFAULT_RULES_DIR, Engine
from rishivan.koonji.lint import lint_bundle, reference_corpus
from rishivan.koonji.vm import Outcome

WHEN = datetime(2026, 8, 23, 12, 0)
CANDIDATE = frozenset({"production", "candidate"})
SEED_RULES = DEFAULT_RULES_DIR / "parashari"


@pytest.fixture(scope="module")
def engine():
    # The reviewed track only. `rules/` also holds `converted/`, ~1,100
    # machine-converted candidates that change with every corpus run - a
    # fixture pinned to "whatever is in rules/" would make these tests fail
    # every time somebody extracted a book, which teaches nobody anything.
    return Engine.from_rules(SEED_RULES)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BirthData(
        year=1990, month=1, day=1, hour=12, minute=0,
        tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
    ))


@pytest.fixture(scope="module")
def corpus():
    return reference_corpus(120)


class TestSeedCorpus:
    def test_the_seed_rules_compile(self, engine):
        assert engine.bundle.manifest.rule_count == 8

    def test_every_seed_rule_quotes_its_source(self, engine):
        """A fabricated citation is the most damaging output this system can
        produce, so a rule with no verse text behind it must not exist."""
        for rule in engine.bundle.rules:
            assert rule.provenance.quoted_text.strip(), rule.rule_id
            assert rule.provenance.locator.strip(), rule.rule_id
            assert rule.provenance.book_id.strip(), rule.rule_id

    def test_no_seed_rule_claims_to_be_reviewed(self, engine):
        """None of these has been read by a Jyotish reviewer. `candidate` is the
        honest status, and the compiler enforces it."""
        assert all(r.status == "candidate" for r in engine.bundle.rules)


class TestServingGate:
    def test_unreviewed_rules_are_not_served_by_default(self, engine, chart):
        reading = engine.read(chart, when=WHEN)
        assert reading.firings == []
        assert reading.insufficient

    def test_candidates_are_served_only_when_asked_for(self, engine, chart):
        reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
        assert reading.firings

    def test_a_denied_rule_is_skipped_without_a_rebuild(self, engine, chart):
        before = {f.rule_id for f in engine.read(chart, when=WHEN, statuses=CANDIDATE).firings}
        assert "BPHS.WEALTH.11L.AFFLICTED.0002" in before
        engine.bundle.deny("BPHS.WEALTH.11L.AFFLICTED.0002")
        try:
            after = {f.rule_id for f in engine.read(chart, when=WHEN, statuses=CANDIDATE).firings}
            assert "BPHS.WEALTH.11L.AFFLICTED.0002" not in after
        finally:
            engine.bundle.denied = frozenset()


class TestGrounding:
    def test_every_claim_carries_a_verse(self, engine, chart):
        reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
        for claim in reading.claims:
            assert claim.citations(), f"{claim.claim_id} has no citation"
            for support in claim.support + claim.against:
                assert support.quote.strip()

    def test_every_cited_rule_is_actually_in_the_bundle(self, engine, chart):
        """The one check that catches a fabricated reference: resolve it."""
        known = set(engine.bundle.by_id())
        reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
        for claim in reading.claims:
            for support in claim.support + claim.against:
                assert support.rule_id in known

    def test_no_claim_exceeds_its_evidence(self, engine, corpus):
        for chart in corpus[:40]:
            reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
            for claim in reading.claims:
                assert claim.support, "a claim with no support must not exist"
                assert 0.0 <= claim.confidence < 1.0


class TestRestriction:
    def test_the_longevity_rule_never_reaches_a_reading(self, engine, corpus):
        """Marked never_user_facing at extraction. It is in the corpus for
        provenance and is structurally unreachable from serving - which is a
        filter you cannot forget to apply."""
        for chart in corpus[:60]:
            reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
            for firing in reading.firings:
                if firing.rule_id == "BPHS.LONGEVITY.8L.KENDRA.0001":
                    assert firing.outcome is Outcome.WITHHELD
            assert all(c.claim_id != "longevity.span" for c in reading.claims)


class TestCancellation:
    def test_a_cancellation_is_evaluated_whenever_its_target_is(self, engine, corpus):
        """Otherwise a yoga survives because nothing looked for the clause that
        breaks it - the most damaging thing this engine could get wrong."""
        for chart in corpus:
            reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
            considered = {f.rule_id for f in reading.firings}
            if "BPHS.WEALTH.10L11H.0001" in considered:
                assert "BPHS.WEALTH.11L.AFFLICTED.0002" in considered


class TestRetrievalIsExhaustive:
    def test_nothing_that_would_fire_is_ever_missed(self, engine, corpus):
        """Brute force: evaluate the entire corpus against every chart and
        confirm retrieval proposed everything that fires. This is the property
        a vector index cannot offer, because its misses are invisible."""
        from rishivan.koonji.index import RETRIEVABLE
        from rishivan.koonji.vm import execute, run_derivations

        registry = engine.registry
        # Only kinds retrieval can return. A definition is consumed at compile
        # time and answers no question, so it is correctly absent.
        servable = [
            r for r in engine.bundle.rules
            if r.status in CANDIDATE and r.assertion in RETRIEVABLE
        ]
        for chart in corpus:
            facts = engine.bundle.index.facts_for(chart, when=WHEN)
            facts = run_derivations(engine.bundle.derivations(), facts, registry)
            everything = {
                f.rule_id for f in execute(servable, facts, registry)
                if f.outcome is Outcome.FIRED
            }
            retrieved = engine.bundle.index.query(facts, statuses=CANDIDATE)
            assert not (everything - retrieved), (
                f"retrieval missed {sorted(everything - retrieved)}"
            )


class TestDeterminism:
    def test_the_same_chart_gives_the_same_reading(self, engine, chart):
        a = engine.read(chart, when=WHEN, statuses=CANDIDATE)
        b = engine.read(chart, when=WHEN, statuses=CANDIDATE)
        assert [(c.claim_id, c.confidence) for c in a.claims] == [
            (c.claim_id, c.confidence) for c in b.claims
        ]

    def test_the_reading_records_the_bundle_it_came_from(self, engine, chart):
        reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
        assert reading.bundle_id == engine.bundle.manifest.bundle_id


class TestTrace:
    def test_the_trace_shows_the_whole_chain(self, engine, chart):
        reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
        trace = engine.trace(reading)
        assert trace["bundle_id"] == reading.bundle_id
        assert trace["registry"] == engine.registry.fingerprint()
        assert trace["retrieval"]["corpus"] == 8
        assert trace["facts"]["undecidable_predicates"] == ["strength", "strength_band"]
        for claim in trace["claims"]:
            for support in claim["support"]:
                assert support["citation"] and support["quote"]

    def test_the_trace_is_json_serialisable(self, engine, chart):
        import json

        reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
        assert json.loads(json.dumps(engine.trace(reading)))


class TestPerformance:
    def test_a_reading_is_well_under_the_deterministic_budget(self, engine, chart):
        """The design budgets 400 ms p95 for the entire deterministic layer.
        This is the whole knowledge path, so it should not be close."""
        engine.read(chart, when=WHEN, statuses=CANDIDATE)  # warm
        reading = engine.read(chart, when=WHEN, statuses=CANDIDATE)
        assert reading.elapsed_ms < 100


class TestLints:
    def test_the_lints_run_over_the_seed_corpus(self, engine, corpus):
        report = lint_bundle(engine.bundle, corpus)
        assert report.charts == len(corpus)
        assert set(report.fire_rate) <= set(engine.bundle.by_id())

    def test_the_withheld_rule_is_reported_as_expected_not_as_dead(self, engine, corpus):
        """Reporting a deliberately-restricted rule as broken would train a
        reviewer to un-restrict it."""
        report = lint_bundle(engine.bundle, corpus)
        findings = {f.lint for f in report.by_rule("BPHS.LONGEVITY.8L.KENDRA.0001")}
        assert "withheld" in findings
        assert "never_fires" not in findings

    def test_an_over_general_rule_is_flagged(self, engine, corpus):
        """BPHS 12.2 fires on roughly three charts in four. That is a true
        observation about the verse, and a reviewer should see it."""
        report = lint_bundle(engine.bundle, corpus)
        assert report.fire_rate["BPHS.GENERAL.BENEFIC.KENDRA.0002"] > 0.25
        assert any(
            f.lint == "high_fire_rate"
            for f in report.by_rule("BPHS.GENERAL.BENEFIC.KENDRA.0002")
        )

    def test_the_reference_corpus_is_deterministic(self):
        a = reference_corpus(50)
        b = reference_corpus(50)
        assert [c.lagna_rashi for c in a] == [c.lagna_rashi for c in b]

    def test_the_reference_corpus_spreads_across_lagnas(self):
        """A corpus that is all one ascendant would make every lint a lie."""
        assert len({c.lagna_rashi for c in reference_corpus(120)}) >= 10
