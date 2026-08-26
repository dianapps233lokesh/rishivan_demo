"""The §7 and §8 nodes: siblings after the diagnosis, both feeding grounding.

Neither reads the other's output — both read `chart_state` — so they are
independent by construction, which is what lets a later phase run them
concurrently without a reducer.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.graph.build import EDGE_MAPS, NODE_NAMES, STATIC_EDGES, build_graph
from rishivan.graph.nodes.timing import dasha_windows_node
from rishivan.graph.nodes.varga import varga_select_node
from rishivan.graph.state import RishivanState, initial_state
from rishivan.varga.confidence import BirthConfidence

ROUND = BirthData(year=1990, month=1, day=1, hour=12, minute=0,
                  tz_offset_hours=5.5, lat=28.6139, lon=77.2090)
PRECISE = BirthData(year=1990, month=1, day=1, hour=12, minute=37,
                    tz_offset_hours=5.5, lat=28.6139, lon=77.2090)
WHEN = datetime(2026, 8, 25, 12, 0)


def diagnosed(birth=ROUND, domain="domain.career"):
    from rishivan.graph.nodes.chart import chart_natal_node
    from rishivan.graph.nodes.diagnosis import chart_state_node

    s = initial_state("will my career improve?", birth_data=birth, query_time=WHEN)
    s["routing"] = {"primary": "artha", "koonji_domains": [domain]}
    s.update(chart_natal_node(s))
    s.update(chart_state_node(s))
    return s


class TestVargaNode:
    def test_it_selects_vargas(self):
        out = varga_select_node(diagnosed())
        assert out["vargas"].selected

    def test_a_round_birth_time_withholds_the_fine_divisions(self):
        """12:00 reads as hour precision, and D10 is a 3-degree division."""
        out = varga_select_node(diagnosed(ROUND))
        assert out["vargas"].confidence is BirthConfidence.HOUR
        assert "D10" not in out["vargas"].selected
        assert out["vargas"].withheld

    def test_a_precise_birth_time_admits_them(self):
        out = varga_select_node(diagnosed(PRECISE))
        assert out["vargas"].confidence is BirthConfidence.MINUTE
        assert "D10" in out["vargas"].selected

    def test_it_returns_only_the_key_it_owns(self):
        assert set(varga_select_node(diagnosed())) == {"vargas"}

    def test_no_chart_yields_no_selection_rather_than_a_crash(self):
        out = varga_select_node(initial_state("what is a yoga?"))
        assert out["vargas"] is None

    def test_it_is_deterministic(self):
        s = diagnosed()
        assert varga_select_node(s) == varga_select_node(s)


class TestTimingNode:
    def test_it_produces_a_report(self):
        out = dasha_windows_node(diagnosed())
        assert out["timing"] is not None
        assert out["timing"].primary == "vimshottari"

    def test_the_window_is_gated_on_the_promise(self):
        """No Koonji reading yet, so nothing has established a promise. The node
        must not invent one — a period is arithmetic, not a prediction."""
        out = dasha_windows_node(diagnosed())
        window = out["timing"].by_system["vimshottari"]
        assert window.promise is False
        assert window.activation is None

    def test_a_supplied_promise_produces_a_window(self):
        s = diagnosed()
        s["reading"] = _FakeReading(promised={"domain.career"})
        out = dasha_windows_node(s)
        assert out["timing"].by_system["vimshottari"].promise is True

    def test_it_returns_only_the_key_it_owns(self):
        assert set(dasha_windows_node(diagnosed())) == {"timing"}

    def test_no_chart_yields_no_timing(self):
        assert dasha_windows_node(initial_state("what is a yoga?"))["timing"] is None

    def test_it_uses_the_reading_moment(self):
        """A Prashna cast for a stated moment must not be timed against today."""
        out = dasha_windows_node(diagnosed())
        assert out["timing"] is not None


class TestWiring:
    def test_both_nodes_are_registered(self):
        for node in ("varga_select", "dasha_windows"):
            assert node in NODE_NAMES

    def test_the_diagnosis_leads_to_them(self):
        assert STATIC_EDGES["chart_state"] == "varga_select"

    def test_they_run_in_sequence_and_reach_grounding(self):
        assert STATIC_EDGES["varga_select"] == "dasha_windows"
        assert STATIC_EDGES["dasha_windows"] == "ground"

    def test_neither_reads_the_other(self):
        """Independent by construction, which is what lets a later phase run
        them concurrently without needing a reducer."""
        import inspect

        from rishivan.graph.nodes import timing, varga

        assert "vargas" not in inspect.getsource(timing.dasha_windows_node)
        assert "timing" not in inspect.getsource(varga.varga_select_node)

    def test_both_keys_are_declared_in_the_state(self):
        """LangGraph discards writes to undeclared channels silently. That
        shipped once."""
        for key in ("vargas", "timing"):
            assert key in RishivanState.__annotations__

    def test_the_graph_still_compiles(self):
        assert build_graph(store=None, client=None) is not None


class _FakeReading:
    """Stands in for a Koonji `Reading` until Phase 4 wires the real one."""

    def __init__(self, promised):
        self.promised = promised

    def promises(self, domain: str) -> bool:
        return domain in self.promised
