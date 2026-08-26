"""The last deterministic thing the graph does.

It computes the gate. Task 3 moves narration outside the graph to consume it;
this file only asserts the plan is built, is right, and reaches the end.
"""

import inspect
from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.graph.nodes.answer_plan import answer_plan_node
from rishivan.graph.nodes.chart import chart_natal_node
from rishivan.graph.nodes.diagnosis import chart_state_node
from rishivan.graph.nodes.hierarchy import hierarchy_node
from rishivan.graph.nodes.koonji import koonji_read_node
from rishivan.graph.nodes.timing import dasha_windows_node
from rishivan.graph.nodes.varga import varga_select_node
from rishivan.graph.state import RishivanState, initial_state

BIRTH = BirthData(year=1990, month=1, day=1, hour=12, minute=37,
                  tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="Delhi")
WHEN = datetime(2026, 8, 26, 12, 0)


@pytest.fixture(scope="module")
def prepared():
    s = initial_state("will I become wealthy?", birth_data=BIRTH, query_time=WHEN)
    for node in (chart_natal_node, chart_state_node, hierarchy_node,
                 varga_select_node, koonji_read_node, dasha_windows_node):
        s.update(node(s))
    return s


def test_the_node_produces_a_plan(prepared):
    assert answer_plan_node(prepared)["answer_plan"] is not None


def test_the_plan_allows_something_on_a_real_chart(prepared):
    """A chart that fires 57 rules and licenses no claim means the floor and
    the evidence graph stopped agreeing."""
    assert answer_plan_node(prepared)["answer_plan"].allowed


def test_the_plan_carries_the_routed_domain(prepared):
    plan = answer_plan_node(prepared)["answer_plan"]
    assert plan.domain == prepared["koonji_domain"]


def test_the_plan_carries_the_question(prepared):
    assert answer_plan_node(prepared)["answer_plan"].question == prepared["question"]


def test_the_plan_says_the_rules_are_unreviewed(prepared):
    """All 1,117 are candidates, and `koonji_read` flags it. If the flag stops
    here the reader never hears it."""
    assert answer_plan_node(prepared)["answer_plan"].unreviewed


def test_no_reading_still_produces_a_plan():
    """A general question casts no chart and still gets an answer. A None plan
    downstream is indistinguishable from a crash."""
    plan = answer_plan_node(initial_state("what is a yoga?"))["answer_plan"]
    assert plan is not None
    assert plan.insufficient


def test_a_chartless_plan_forbids_composing_a_reading():
    plan = answer_plan_node(initial_state("what is a yoga?"))["answer_plan"]
    assert any("silent" in m.lower() for m in plan.must_not_say)


def test_the_node_makes_no_model_call():
    assert "client" not in inspect.signature(answer_plan_node).parameters


def test_the_node_is_deterministic(prepared):
    assert answer_plan_node(prepared) == answer_plan_node(prepared)


def test_it_returns_only_the_key_it_owns(prepared):
    assert set(answer_plan_node(prepared)) == {"answer_plan"}


def test_every_key_returned_is_declared_in_the_state(prepared):
    assert set(answer_plan_node(prepared)) <= set(RishivanState.__annotations__)


def test_the_plan_is_serialisable(prepared):
    """The reason the phase exists. One unserialisable field here and
    checkpointing stays broken."""
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    JsonPlusSerializer().dumps_typed(answer_plan_node(prepared)["answer_plan"])
