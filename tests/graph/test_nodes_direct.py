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


class TestTheTimingNodeStillRefusesToInventAPromise:
    """`assume_promise` existed briefly and was removed. This is its epitaph.

    The direct lane passed `assume_promise=True` so the five-stage arithmetic
    would run without a rule engine behind it, on the theory that the prompt
    could label the stages as boundaries and let the model decide whether
    anything was promised. The model did not decide - it wrote "you will receive
    your major career promotion during <activation range>". Because the stages
    anchor to `start=now`, a fabricated promise makes every window begin today,
    which reads as imminent whatever the label says.

    So the node is back to its original rule, and the direct lane derives plain
    antardasha boundaries in the prompt instead.
    """

    def test_no_promise_means_no_window(self, chart):
        state = _state(chart=chart, chart_state=build_chart_state(chart, when=WHEN))
        report = dasha_windows_node(state)["timing"]
        assert report.by_system[report.primary].promise is False

    def test_there_is_no_way_to_ask_it_to_assume_one(self):
        import inspect
        assert list(inspect.signature(dasha_windows_node).parameters) == ["state"]
