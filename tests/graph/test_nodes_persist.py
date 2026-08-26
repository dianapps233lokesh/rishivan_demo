"""The audit chain, written where somebody can read it.

`Engine.trace(reading)` already produces the Koonji half — which rules were
considered, which fired, which were cancelled by what, and the verse behind each
one. This node composes it with the council half and hands the whole thing to a
sink.

**The sink is injected.** A node that assumes Postgres is a node that fails in
the one environment this repo actually ships to.
"""

import inspect
import json
from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.graph.nodes.answer_plan import answer_plan_node
from rishivan.graph.nodes.chart import chart_natal_node
from rishivan.graph.nodes.diagnosis import chart_state_node
from rishivan.graph.nodes.hierarchy import hierarchy_node
from rishivan.graph.nodes.koonji import koonji_read_node
from rishivan.graph.nodes.persist import persist_node
from rishivan.graph.nodes.timing import dasha_windows_node
from rishivan.graph.nodes.varga import varga_select_node
from rishivan.graph.state import RishivanState, initial_state

BIRTH = BirthData(year=1990, month=1, day=1, hour=12, minute=37,
                  tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="Delhi")
WHEN = datetime(2026, 8, 26, 12, 0)


def _null(trace, predictions):
    return None


def _raises(trace, predictions):
    raise OSError("no space left on device")


@pytest.fixture(scope="module")
def served():
    s = initial_state("will I become wealthy?", birth_data=BIRTH, query_time=WHEN)
    for node in (chart_natal_node, chart_state_node, hierarchy_node,
                 varga_select_node, koonji_read_node, dasha_windows_node,
                 answer_plan_node):
        s.update(node(s))
    return s


# ==========================================================================
# What the trace carries
# ==========================================================================


def test_the_trace_carries_the_koonji_audit_chain(served):
    trace = persist_node(served, sink=_null)["trace"]
    assert trace["koonji"]["firings"]
    assert trace["koonji"]["bundle_id"]


def test_the_trace_says_which_rules_were_cancelled(served):
    """The artifact the architecture exists to produce. Anyone can wire a
    model to an ephemeris; nobody else can say what was cancelled by what."""
    trace = persist_node(served, sink=_null)["trace"]
    assert "evidence" in trace["koonji"] or "firings" in trace["koonji"]


def test_the_trace_records_the_chart_digest(served):
    """A mismatch on recomputation means the calculation stack drifted under
    stored answers — the highest-severity alarm in the system, and the one
    nobody would otherwise notice."""
    assert persist_node(served, sink=_null)["trace"]["chart_digest"]


def test_the_trace_records_the_registry_fingerprint(served):
    """A trace that cannot say which vocabulary produced it is a trace nobody
    can replay."""
    assert persist_node(served, sink=_null)["trace"]["koonji"]["registry"]


def test_the_trace_records_the_run_id(served):
    assert persist_node(served, sink=_null)["trace"]["run_id"] == served["run_id"]


def test_the_trace_carries_the_answer_plan(served):
    trace = persist_node(served, sink=_null)["trace"]
    assert trace["answer_plan"]["allowed"]


def test_the_trace_records_that_the_rules_are_unreviewed(served):
    """A trace read a year from now must say whether the rules behind it had
    been reviewed at the time."""
    assert persist_node(served, sink=_null)["trace"]["unreviewed"] is True


def test_the_trace_is_json_serialisable(served):
    json.dumps(persist_node(served, sink=_null)["trace"])


# ==========================================================================
# Robustness
# ==========================================================================


def test_a_sink_failure_does_not_fail_the_turn(served):
    """A full disk must not cost the reader their answer."""
    assert persist_node(served, sink=_raises)["trace"]


def test_no_reading_still_writes_a_trace():
    """Why a question produced no reading is exactly what a trace is for."""
    s = initial_state("what is a yoga?")
    s.update(answer_plan_node(s))
    assert persist_node(s, sink=_null)["trace"]


def test_a_chartless_trace_says_there_was_no_reading():
    s = initial_state("what is a yoga?")
    s.update(answer_plan_node(s))
    assert persist_node(s, sink=_null)["trace"]["koonji"] is None


# ==========================================================================
# The ledger
# ==========================================================================


def test_predictions_reach_the_sink(served):
    seen = {}

    def sink(trace, predictions):
        seen["predictions"] = predictions

    persist_node(served, sink=sink)
    assert "predictions" in seen


def test_only_dated_claims_become_predictions(served):
    seen = {}

    def sink(trace, predictions):
        seen["predictions"] = predictions

    persist_node(served, sink=sink)
    plan = served["answer_plan"]
    dated = [c for c in plan.allowed if c.window]
    assert len(seen["predictions"]) == len(dated)


# ==========================================================================
# Contract
# ==========================================================================


def test_every_key_returned_is_declared_in_the_state(served):
    assert set(persist_node(served, sink=_null)) <= set(
        RishivanState.__annotations__)


def test_the_node_makes_no_model_call():
    assert "client" not in inspect.signature(persist_node).parameters


def test_the_sink_is_injected():
    """A node that assumes a database fails in the one environment this repo
    ships to."""
    assert "sink" in inspect.signature(persist_node).parameters
