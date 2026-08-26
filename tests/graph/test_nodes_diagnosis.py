"""The chart-state node, and its place in the graph.

Phase 2's only change to the graph: one node between each chart node and
grounding. The tests below are mostly about it *not* breaking anything — a new
node in a behaviour-preserving pipeline earns its place by being invisible to
everything downstream until something reads it.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.graph.build import EDGE_MAPS, NODE_NAMES, STATIC_EDGES, build_graph
from rishivan.graph.nodes.diagnosis import chart_state_node
from rishivan.graph.state import RishivanState, initial_state

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def charted():
    from rishivan.graph.nodes.chart import chart_natal_node

    s = initial_state("will I be wealthy?", birth_data=BIRTH, query_time=WHEN)
    s.update(chart_natal_node(s))
    return s


class TestTheNode:
    def test_it_produces_a_chart_state(self, charted):
        out = chart_state_node(charted)
        assert out["chart_state"] is not None
        assert out["chart_state"].planets

    def test_it_stamps_the_digest(self, charted):
        out = chart_state_node(charted)
        assert out["chart_digest"] == out["chart_state"].chart_digest

    def test_it_returns_only_the_keys_it_owns(self, charted):
        assert set(chart_state_node(charted)) <= {"chart_state", "chart_digest"}

    def test_it_uses_the_reading_moment_not_the_wall_clock(self, charted):
        """Dasha activation moves with time. A Prashna cast for a stated moment
        evaluated against today's periods is a different reading."""
        assert chart_state_node(charted)["chart_state"].when == WHEN

    def test_it_is_deterministic(self, charted):
        assert chart_state_node(charted) == chart_state_node(charted)

    def test_no_chart_means_no_diagnosis_rather_than_a_crash(self):
        """A general question never casts a chart, and the node is on that path
        only because the graph is linear there."""
        out = chart_state_node(initial_state("what is a yoga?"))
        assert out["chart_state"] is None
        assert out["chart_digest"] == ""


class TestWiring:
    def test_the_node_is_registered(self):
        assert "chart_state" in NODE_NAMES

    def test_both_chart_nodes_route_through_it(self):
        """Natal and moment charts both get diagnosed. A prashna reading with no
        diagnosis would be the one place the Rishis had to improvise."""
        for node in ("chart_natal", "chart_moment"):
            assert EDGE_MAPS[node]["retrieve"] == "chart_state"

    def test_it_leads_to_grounding(self):
        """Walked, not pinned to one hop. Phase 3 legitimately inserted the
        varga and timing nodes between the diagnosis and grounding, and a test
        that pins a single edge fails on every correct extension."""
        node = "chart_state"
        for _ in range(10):
            node = STATIC_EDGES[node]
            if node == "ground":
                return
        raise AssertionError("the diagnosis never reaches grounding")

    def test_the_panchang_path_is_also_diagnosed(self):
        """A chart question that also mentions panchang took `chart -> panchang
        -> ground` and reached the Rishis with no diagnosis. The node tolerates
        a missing chart, so the chartless panchang path is unaffected."""
        assert STATIC_EDGES["panchang"] == "chart_state"

    def test_every_path_that_casts_a_chart_reaches_the_diagnosis(self):
        """Walked rather than asserted case by case, so a future edge cannot
        quietly bypass it."""
        for node in ("chart_natal", "chart_moment"):
            for destination in EDGE_MAPS[node].values():
                if destination == "chart_render":
                    continue  # a display request, no reading produced
                reached = destination
                while reached not in ("chart_state", "ground"):
                    reached = STATIC_EDGES[reached]
                assert reached == "chart_state", f"{node} -> {destination}"

    def test_the_graph_still_compiles(self):
        assert build_graph(store=None, client=None) is not None

    def test_chart_state_is_declared_in_the_state(self):
        for key in ("chart_state", "chart_digest"):
            assert key in RishivanState.__annotations__, key


class TestItChangesNothingDownstream:
    def test_a_display_request_still_short_circuits(self):
        """"show me my D9" must not start computing a diagnosis it will never
        use."""
        from rishivan.graph.edges import route_after_chart

        s = initial_state("show me my D9 chart", birth_data=BIRTH)
        s["chart"] = object()
        s["classification"] = {"intent": "chart"}
        assert route_after_chart(s) == "chart_render"
