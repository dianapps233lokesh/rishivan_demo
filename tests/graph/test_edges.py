"""Every branch the orchestrator used to take, as a table.

These branches exist today inside `council_consult`, where testing one meant
running all of it - chart computation, embeddings, model calls. That is why none
of them were tested. Pure functions fix that, and the table below is the list of
behaviours Phase 1 must preserve exactly.
"""

import copy

import pytest

from rishivan.council.domains import QueryDomain
from rishivan.graph.edges import (
    route_after_chart,
    route_after_intake,
    route_after_retrieval,
    route_chart_kind,
)
from rishivan.graph.state import initial_state


def state(**kw):
    s = initial_state(kw.pop("question", "will I be wealthy?"))
    s.update(kw)
    return s


class TestAfterIntake:
    def test_smalltalk_bypasses_everything(self):
        s = state(classification={"is_smalltalk_or_gibberish": True})
        assert route_after_intake(s) == "warmth"

    def test_a_natal_question_without_birth_data_still_charts(self):
        """`council_consult:138` rewrites the domain to PRASHNA rather than
        asking for a birth time - the moment of asking becomes the chart. The
        rewrite is a state write, so it lives in `intake_node`; by the time this
        router runs the domain is already chartable."""
        s = state(query_domain=QueryDomain.NATAL, birth_data=None)
        assert route_after_intake(s) == "chart_natal"

    def test_a_natal_question_with_birth_data_proceeds(self):
        s = state(query_domain=QueryDomain.NATAL, birth_data=object())
        assert route_after_intake(s) == "chart_natal"

    def test_muhurta_proceeds_to_chart_without_birth_data(self):
        """Muhurta is cast from a target moment, not from a birth."""
        s = state(query_domain=QueryDomain.MUHURTA, birth_data=None)
        assert route_after_intake(s) == "chart_moment"

    def test_prashna_proceeds_without_birth_data(self):
        s = state(query_domain=QueryDomain.PRASHNA, birth_data=None)
        assert route_after_intake(s) == "chart_moment"

    def test_a_general_question_skips_the_chart(self):
        s = state(query_domain=QueryDomain.GENERAL, birth_data=None)
        assert route_after_intake(s) == "retrieve"

    def test_a_general_question_about_panchang_still_computes_it(self):
        """`council_consult:200` guards panchang on the question alone, not on
        a chart existing."""
        s = state(query_domain=QueryDomain.GENERAL,
                  question="what is the panchang tomorrow?")
        assert route_after_intake(s) == "panchang"

    def test_smalltalk_wins_over_everything_else(self):
        """Order matters: "hi" from a user with no birth data is a greeting, and
        casting a prashna chart for it would be absurd."""
        s = state(
            classification={"is_smalltalk_or_gibberish": True},
            query_domain=QueryDomain.NATAL, birth_data=None,
        )
        assert route_after_intake(s) == "warmth"


class TestAfterChart:
    def test_a_chart_request_goes_to_rendering(self):
        s = state(chart=object(), classification={"intent": "chart"})
        assert route_after_chart(s) == "chart_render"

    def test_a_panchang_mention_goes_to_panchang(self):
        s = state(chart=object(), classification={"intent": "predict"},
                  question="what is the panchang today?")
        assert route_after_chart(s) == "panchang"

    def test_an_ordinary_question_goes_to_retrieval(self):
        s = state(chart=object(), classification={"intent": "predict"})
        assert route_after_chart(s) == "retrieve"

    def test_chart_intent_without_a_chart_does_not_render(self):
        """`if chart is not None and intent == 'chart'` - both halves."""
        s = state(chart=None, classification={"intent": "chart"})
        assert route_after_chart(s) == "retrieve"

    def test_a_display_request_beats_a_panchang_mention(self):
        """"show me my chart" returns the table and stops. The orchestrator
        computes panchang first but returns the table either way, so the visible
        answer is identical."""
        s = state(chart=object(), classification={"intent": "chart"},
                  question="show me my chart for the panchang today")
        assert route_after_chart(s) == "chart_render"


class TestChartKind:
    @pytest.mark.parametrize("kind,expected", [
        ("numerology", "render_numerology"),
        ("ashtakavarga", "render_ashtakavarga"),
        ("dasha", "render_dasha"),
        ("rashi", "render_varga"),
        ("", "render_varga"),
    ])
    def test_each_chart_kind_has_a_renderer(self, kind, expected):
        s = state(classification={"chart_type": kind}, birth_data=object())
        assert route_chart_kind(s) == expected

    def test_numerology_without_a_birth_date_still_routes_to_its_renderer(self):
        """The orchestrator reports this as a table it could not compute, not as
        a request for input. The renderer owns that message; the router does not
        grow a fifth destination for it."""
        s = state(classification={"chart_type": "numerology"}, birth_data=None)
        assert route_chart_kind(s) == "render_numerology"


class TestAfterRetrieval:
    def test_sources_lead_to_an_answer(self):
        assert route_after_retrieval(state(sources=[{"text": "x"}])) == "answer"

    def test_rules_alone_are_enough_to_answer_from(self):
        """`council_consult:534` gates on pages OR rules. Requiring pages would
        discard a reading the rule base grounded by itself - the half most
        likely to be right."""
        s = state(sources=[], matched_rules=[{"rule_id": "BPHS.X"}])
        assert route_after_retrieval(s) == "answer"

    def test_neither_is_insufficient_evidence(self):
        """Saying the corpus is silent is an answer. Generating around it is the
        failure this whole architecture exists to prevent."""
        assert route_after_retrieval(state(sources=[], matched_rules=[])) == "insufficient"


class TestPurity:
    def test_routers_do_not_mutate_state(self):
        """A router that writes is a node wearing an edge's clothes, and the
        write lands on a path nobody expects."""
        for router in (route_after_intake, route_after_chart,
                       route_chart_kind, route_after_retrieval):
            s = state(chart=object(), sources=[{"text": "x"}],
                      birth_data=object(),
                      classification={"intent": "predict", "chart_type": ""})
            skip = ("chart", "conversation", "birth_data")
            before = copy.deepcopy({k: v for k, v in s.items() if k not in skip})
            router(s)
            after = {k: v for k, v in s.items() if k not in skip}
            assert before == after, router.__name__

    def test_every_router_returns_a_plain_string(self):
        """LangGraph maps the return value through an edge dict. A non-string
        silently misses every key in it."""
        for router, s in (
            (route_after_intake, state()),
            (route_after_chart, state(chart=object(),
                                      classification={"intent": "predict"})),
            (route_chart_kind, state(classification={"chart_type": ""},
                                     birth_data=object())),
            (route_after_retrieval, state(sources=[])),
        ):
            assert isinstance(router(s), str), router.__name__
