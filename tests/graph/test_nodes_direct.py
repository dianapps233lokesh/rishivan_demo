"""The direct lane's node, and the timing node without a rule engine behind it."""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.facts import derive_facts
from rishivan.chartstate.build import build_chart_state
from rishivan.graph.nodes.direct import direct_read_node
from rishivan.graph.nodes.timing import dasha_windows_node
from rishivan.graph.state import RishivanState, initial_state

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


def _state(question="when will I marry?", **kw):
    s = initial_state(question, query_time=WHEN)
    s["koonji_domain"] = kw.pop("koonji_domain", "domain.relationship")
    s.update(kw)
    return s


class TestDirectReadNode:
    def test_it_writes_the_prompt_and_nothing_else(self, chart):
        out = direct_read_node(_state(
            chart=chart, chart_facts=derive_facts(chart, when=WHEN),
        ))
        assert set(out) == {"direct_prompt"}
        assert "READING METHOD" in out["direct_prompt"]

    def test_the_key_is_declared_in_the_state_schema(self):
        """LangGraph discards writes to undeclared channels SILENTLY. That has
        shipped here once: retrieve_node returned context_text, the schema did
        not declare it, and every answer was generated with an empty context
        block while the sources panel rendered normally."""
        assert "direct_prompt" in RishivanState.__annotations__

    def test_it_works_without_a_chart(self):
        out = direct_read_node(_state("what is a nakshatra?"))
        assert out["direct_prompt"]

    def test_it_makes_no_model_call(self):
        """The signature takes no client, which is the guarantee. Asserted
        anyway, because a later edit adding one would be easy and silent."""
        import inspect
        assert list(inspect.signature(direct_read_node).parameters) == ["state"]


class TestTimingWithoutAReading:
    def test_no_window_without_a_promise_is_still_the_default(self, chart):
        """Unchanged behaviour for the retrieval lane. A dasha window with no
        grounded promise is how a period becomes a prediction nobody made."""
        state = _state(chart=chart, chart_state=build_chart_state(chart, when=WHEN))
        report = dasha_windows_node(state)["timing"]
        window = report.by_system[report.primary]
        assert window.promise is False

    def test_assume_promise_produces_a_window(self, chart):
        """The direct lane has no rule engine to establish a promise, so the
        arithmetic runs and the MODEL judges whether anything is promised."""
        state = _state(chart=chart, chart_state=build_chart_state(chart, when=WHEN))
        report = dasha_windows_node(state, assume_promise=True)["timing"]
        window = report.by_system[report.primary]
        assert window.promise is True
        assert window.activation is not None

    def test_assume_promise_still_returns_none_without_a_chart(self):
        assert dasha_windows_node(_state(), assume_promise=True)["timing"] is None
