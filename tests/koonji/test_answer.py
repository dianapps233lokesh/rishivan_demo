"""The gated path: a sentence in, a reading or an honest refusal out.

`test_engine.py` covers `read()`, which answers whatever it is asked. This
covers `answer()`, which first has to work out what to ask - and, more often,
that there is nothing to ask at all.

The centre of gravity is the four ways a filtered read comes back with nothing.
They look identical from the outside and mean entirely different things:

    no_coverage    the bundle holds no rules tagged with the routed domain
    scoped == 0    rules exist but the filter admitted none of them
    considered==0  rules were in scope, none matched this chart
    insufficient   rules matched and fired, but too weakly to say anything

Only the second is a bug in the filter. The others are answers.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.koonji.engine import DEFAULT_RULES_DIR, Engine
from rishivan.koonji.question import InputKind, Mode, TurnType
from rishivan.koonji.router import parse

WHEN = datetime(2026, 8, 25, 12, 0)
CANDIDATE = frozenset({"production", "candidate"})
SEED_RULES = DEFAULT_RULES_DIR / "parashari"
HAVE_CHART = {InputKind.BIRTH_PROFILE}


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


def ask(engine, chart, text, **kw):
    kw.setdefault("available", HAVE_CHART)
    kw.setdefault("statuses", CANDIDATE)
    kw.setdefault("when", WHEN)
    return engine.answer(text, chart, **kw)


class TestGateOrder:
    """Each gate is cheaper than the one after it and can end the turn alone."""

    def test_a_greeting_never_touches_the_corpus(self, engine, chart):
        r = ask(engine, chart, "hello")
        assert r.outcome == "not_analytic"
        assert r.reading is None

    def test_a_meta_question_never_touches_the_corpus(self, engine, chart):
        assert ask(engine, chart, "how does this work?").outcome == "not_analytic"

    def test_a_drilldown_is_served_from_the_stored_trace_not_recomputed(self, engine, chart):
        """Recomputing could cite a different bundle than the one that produced
        the claim the user is pointing at."""
        r = ask(engine, chart, "which verse does that come from?")
        assert r.outcome == "not_analytic"
        assert r.spec.turn_type is TurnType.DRILLDOWN

    def test_a_mortality_question_is_refused_even_though_the_rules_exist(self, engine, chart):
        """`domain.longevity` rules are in this bundle and would fire. The
        refusal is a product decision, and it comes before retrieval."""
        r = ask(engine, chart, "when will I die?")
        assert r.outcome == "refused"
        assert r.reading is None
        assert "longevity" in r.message or "death" in r.message.lower()

    def test_refusal_beats_every_other_gate(self, engine, chart):
        """A distress signal in an otherwise unparseable message still refuses,
        rather than asking the user to clarify."""
        assert ask(engine, chart, "i want to die").outcome == "refused"

    def test_an_unsupported_mode_says_so_rather_than_reading_one_chart(self, engine, chart):
        r = ask(engine, chart, "are we compatible?")
        assert r.outcome in ("unsupported", "needs_input")
        assert r.reading is None

    def test_a_missing_chart_is_asked_for(self, engine, chart):
        r = ask(engine, chart, "will I be wealthy?", available=set())
        assert r.outcome == "needs_input"
        assert "birth date" in r.message

    def test_an_unparseable_question_asks_rather_than_answering(self, engine, chart):
        r = ask(engine, chart, "?")
        assert r.outcome == "clarify"
        assert r.reading is None

    def test_a_wiring_bug_is_not_dressed_up_as_insufficient_evidence(self, engine, chart):
        """Caller said the chart was available and passed none. A cheerful
        "the texts are silent" would hide the bug forever."""
        with pytest.raises(ValueError, match="needs a chart"):
            engine.answer("will I be wealthy?", None, available=HAVE_CHART)


class TestFiltering:
    def test_a_routed_question_narrows_the_scope(self, engine, chart):
        wide = engine.read(chart, when=WHEN, statuses=CANDIDATE)
        narrow = ask(engine, chart, "will I be wealthy?").reading
        assert narrow.scoped < engine.bundle.manifest.variant_count
        assert narrow.considered <= wide.considered

    def test_the_filter_is_recorded_on_the_reading(self, engine, chart):
        plan = ask(engine, chart, "will I be wealthy?").plan
        assert plan.domains == frozenset({"domain.wealth"})
        assert plan.schools == frozenset({"school.parashari"})
        assert plan.notes

    def test_an_incidental_domain_tag_does_not_pull_a_rule_in(self, engine, chart):
        """`BPHS.WEALTH.10L11H.0001` is tagged wealth 0.95 and career 0.35. It is
        a wealth rule that touches career, and it must not lead a career
        reading."""
        rule = engine.bundle.rule("BPHS.WEALTH.10L11H.0001")
        assert rule.domains["domain.career"] < 0.5

        career = engine.bundle.index.query(
            engine.bundle.index.facts_for(chart, when=WHEN),
            domains={"domain.career"}, statuses=CANDIDATE, min_domain_weight=0.5,
        )
        assert "BPHS.WEALTH.10L11H.0001" not in career

    def test_the_same_rule_is_reachable_without_the_threshold(self, engine):
        """The threshold changes what a rule is retrieved *as*. It does not
        delete it.

        Asserted on scope rather than on `query`, because whether the rule then
        matches a particular chart is a different question - and mixing the two
        is how you end up believing a filter is broken when the chart simply
        does not have the configuration."""
        index = engine.bundle.index
        args = dict(domains={"domain.career"}, statuses=CANDIDATE)
        assert index.scope_size(**args, min_domain_weight=0.0) > (
            index.scope_size(**args, min_domain_weight=0.5)
        )

    def test_an_untagged_rule_survives_every_domain_filter(self, engine):
        """A rule with no domain tags makes no claim about which part of a life
        it speaks to, so no domain filter can exclude it. Treating "no tags" as
        "matches nothing" is the silent-recall failure the whole retrieval
        design exists to avoid."""
        from rishivan.koonji.index import Variant

        v = Variant(variant_id=0, rule_id="X", core=frozenset(), always=True,
                    domains={}, school="school.parashari", status="production")
        assert v.in_scope({"domain.wealth"}, None, frozenset({"production"}), 0.5)

    def test_a_domain_filter_is_not_an_empty_set(self, engine, chart):
        """None means unfiltered; an empty set retrieves nothing. A router that
        matched no phrase must produce the first."""
        facts = engine.bundle.index.facts_for(chart, when=WHEN)
        assert engine.bundle.index.query(facts, domains=set(), statuses=CANDIDATE) == set()
        assert engine.bundle.index.query(facts, domains=None, statuses=CANDIDATE)

    def test_a_life_map_reads_everything(self, engine, chart):
        r = ask(engine, chart, "give me a full reading")
        assert r.spec.mode is Mode.LIFE_MAP
        assert r.plan.domains is None
        assert r.reading.scoped == engine.bundle.manifest.variant_count

    def test_status_filtering_still_applies_under_a_domain_filter(self, engine, chart):
        r = ask(engine, chart, "will I be wealthy?", statuses=frozenset({"production"}))
        assert all(
            engine.bundle.rule(f.rule_id).status == "production"
            for f in r.reading.firings
        )


class TestEmptyResults:
    """The four ways a read comes back with nothing, kept apart."""

    def test_a_domain_the_bundle_does_not_cover_is_named_as_such(self, engine, chart):
        r = ask(engine, chart, "will I travel abroad?")
        assert r.outcome == "no_coverage"
        assert "travel" in r.message
        assert r.reading is None

    def test_coverage_is_a_property_of_the_corpus_not_the_chart(self, engine):
        coverage = engine.bundle.index.domain_coverage()
        assert coverage["domain.wealth"] > 0
        assert "domain.travel" not in coverage

    def test_one_covered_domain_is_enough_to_proceed(self, engine, chart):
        """Only when *every* routed domain is uncovered is the answer "we hold
        nothing about this"."""
        r = ask(engine, chart, "will I travel abroad for a new job?")
        assert r.outcome == "served"

    def test_an_empty_scope_widens_and_records_that_it_did(self, engine, chart):
        """The filter admitted no rules at all. That is a routing question, not
        a result."""
        r = ask(engine, chart, "will I travel abroad for a new job?")
        assert r.reading.widened
        assert any("widened" in n for n in r.plan.notes)
        assert r.plan.domains is None

    def test_rules_in_scope_that_do_not_match_are_honest_silence(self, engine, chart):
        """This is the one that matters. Relationship rules were in scope and
        none matched this chart, so the material is silent on this marriage.
        Widening here would answer a marriage question with wealth rules."""
        r = ask(engine, chart, "when will I get married?")
        assert r.outcome == "served"
        assert r.reading.scoped > 0
        assert r.reading.considered == 0
        assert not r.reading.widened
        assert r.reading.insufficient

    def test_widening_can_be_turned_off(self, engine, chart):
        r = ask(engine, chart, "will I travel abroad for a new job?", widen_if_empty=False)
        assert not r.reading.widened
        assert r.reading.scoped == 0


class TestTrace:
    def test_the_trace_carries_the_question_and_the_filter(self, engine, chart):
        """A reading whose filter is not in the trace cannot be audited - you
        can see what fired but not what was never looked at."""
        r = ask(engine, chart, "will I be wealthy?")
        trace = engine.trace(r.reading)
        assert trace["question"]["raw"] == "will I be wealthy?"
        assert trace["question"]["routing"]["domains"] == ["domain.wealth"]
        assert trace["retrieval"]["filter"]["domains"] == ["domain.wealth"]
        assert trace["retrieval"]["scoped"] >= trace["retrieval"]["considered"]

    def test_a_direct_read_has_no_question_in_its_trace(self, engine, chart):
        trace = engine.trace(engine.read(chart, when=WHEN, statuses=CANDIDATE))
        assert trace["question"] is None

    def test_the_response_serialises_without_the_chart(self, engine, chart):
        """What gets logged per turn. It must not drag a chart into the log."""
        import json

        payload = ask(engine, chart, "will I be wealthy?").to_dict()
        assert json.loads(json.dumps(payload))["routing"]["domains"] == ["domain.wealth"]


class TestDeterminism:
    def test_the_same_question_produces_the_same_filter_twice(self, engine, chart):
        a = ask(engine, chart, "when will my career improve?")
        b = ask(engine, chart, "when will my career improve?")
        assert a.plan == b.plan
        assert a.spec.model_dump() == b.spec.model_dump()

    def test_a_prebuilt_spec_can_be_passed_straight_in(self, engine, chart):
        """The router is replaceable. `answer()` takes its output, not its
        implementation."""
        spec = parse("will I be wealthy?", now=WHEN, available=HAVE_CHART)
        assert ask(engine, chart, spec).outcome == "served"
