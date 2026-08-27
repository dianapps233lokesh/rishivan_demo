"""The direct lane's topology.

Asserted on the compiled graph rather than by running it, because the thing that
can be wrong is a destination, and a mistyped destination is a KeyError on a
branch nobody takes until a user does.
"""

import pytest

from rishivan.graph.build import (
    DIRECT_EDGE_MAPS, DIRECT_STATIC_EDGES, EDGE_MAPS, STATIC_EDGES, build_graph,
)


@pytest.fixture
def direct_graph():
    return build_graph(store=None, client=None, direct=True)


@pytest.fixture
def default_graph():
    return build_graph(store=None, client=None)


def _nodes(graph):
    return set(graph.get_graph().nodes)


def _edge_pairs(graph):
    return {(e.source, e.target) for e in graph.get_graph().edges}


class TestDirectTopology:
    def test_direct_read_is_reachable_in_direct_mode(self, direct_graph):
        assert "direct_read" in _nodes(direct_graph)

    def test_retrieval_and_the_council_are_absent_in_direct_mode(self, direct_graph):
        nodes = _nodes(direct_graph)
        for gone in ("retrieve", "ground", "council_routing", "koonji_read",
                     "fan_out", "rishi", "sakshi", "re_examine", "synthesis",
                     "answer_plan", "insufficient"):
            assert gone not in nodes, f"{gone} should not exist in the direct lane"

    def test_the_computational_nodes_all_survive(self, direct_graph):
        nodes = _nodes(direct_graph)
        for kept in ("intake", "warmth", "chart_natal", "chart_moment", "panchang",
                     "chart_state", "hierarchy", "varga_select", "dasha_windows",
                     "chart_render", "render_varga", "render_dasha",
                     "render_ashtakavarga", "render_numerology", "persist"):
            assert kept in nodes, f"{kept} must survive into the direct lane"

    def test_the_reading_chain_skips_koonji(self, direct_graph):
        assert ("varga_select", "dasha_windows") in _edge_pairs(direct_graph)

    def test_dasha_windows_leads_to_the_direct_read(self, direct_graph):
        assert ("dasha_windows", "direct_read") in _edge_pairs(direct_graph)

    def test_the_lane_is_traced_like_any_other(self, direct_graph):
        """persist_node reads reading and answer_plan with .get() and tolerates
        both being None. Why a question produced the reading it did is exactly
        what a trace is for, and this lane is the one being evaluated."""
        assert ("direct_read", "persist") in _edge_pairs(direct_graph)

    def test_a_chartless_question_reaches_the_diagnosis_not_grounding(self):
        """In the retrieval lane intake's "retrieve" lands on `ground`. Here it
        lands on `chart_state`, so hierarchy still runs and the method block
        still gets a domain - a chartless question needs a protocol too."""
        assert DIRECT_EDGE_MAPS["intake"]["retrieve"] == "chart_state"

    def test_every_direct_destination_is_a_real_node(self, direct_graph):
        nodes = _nodes(direct_graph)
        destinations = {
            d for table in DIRECT_EDGE_MAPS.values() for d in table.values()
        } | set(DIRECT_STATIC_EDGES)
        assert destinations <= nodes


class TestTheDefaultLaneIsUntouched:
    def test_the_default_tables_still_hold_the_retrieval_topology(self):
        assert EDGE_MAPS["intake"]["retrieve"] == "ground"
        assert STATIC_EDGES["varga_select"] == "koonji_read"
        assert STATIC_EDGES["koonji_read"] == "dasha_windows"

    def test_the_default_graph_still_has_the_council(self, default_graph):
        nodes = _nodes(default_graph)
        for kept in ("retrieve", "ground", "koonji_read", "rishi", "sakshi"):
            assert kept in nodes

    def test_the_default_graph_has_no_direct_read(self, default_graph):
        assert "direct_read" not in _nodes(default_graph)

    def test_the_routers_still_speak_only_of_retrieval(self):
        """The whole reason this task is small. Both retrieval routers return the
        label "retrieve"; only the table it resolves through changes. A router
        that knew the word `direct_read` would be a router with two lanes'
        destinations in it, and `test_edges.py`'s table would need a second
        column."""
        import inspect

        from rishivan.graph import edges

        source = inspect.getsource(edges)
        assert '"retrieve"' in source
        assert "direct_read" not in source

    def test_both_retrieval_routers_return_the_same_label(self):
        """Asserted behaviourally rather than by reading the source, so a
        refactor of how the routers are written cannot make this vacuous."""
        from rishivan.council.domains import QueryDomain
        from rishivan.graph.edges import route_after_chart, route_after_intake
        from rishivan.graph.state import initial_state

        state = initial_state("will I be wealthy?")
        state["classification"] = {"is_smalltalk_or_gibberish": False,
                                   "intent": "reading"}
        state["query_domain"] = QueryDomain.GENERAL
        assert route_after_intake(state) == "retrieve"
        assert route_after_chart(state) == "retrieve"
