"""Blueprint §12: settle what kind of question this is, once.

Four nodes downstream key off this one's `koonji_domain` - which vargas may
speak, which rules the index admits, how a firing is weighted, and which Rishis
are invited. Before this node existed, each of them guessed separately, and two
of them read a state key nothing wrote.
"""

import inspect
from datetime import datetime

from rishivan.graph.nodes.hierarchy import hierarchy_node
from rishivan.graph.state import initial_state

WHEN = datetime(2026, 8, 26, 12, 0)


def _state(question):
    state = initial_state(question)
    state["query_time"] = WHEN
    return state


def test_a_marriage_question_routes_to_the_relationship_hierarchy():
    out = hierarchy_node(_state("when will I get married?"))
    assert out["koonji_domain"] == "domain.relationship"
    assert out["hierarchy"].houses[0] == 7


def test_a_career_question_routes_to_the_career_hierarchy():
    out = hierarchy_node(_state("will I get a promotion at work?"))
    assert out["koonji_domain"] == "domain.career"
    assert "D10" in out["hierarchy"].vargas


def test_an_unroutable_question_falls_back_to_temperament():
    """The self, broadly - which is what a question nobody could route is
    usually about. Falling back to nothing would filter the corpus to empty."""
    out = hierarchy_node(_state("hmm"))
    assert out["koonji_domain"] == "domain.temperament"
    assert out["hierarchy"] is not None


def test_the_node_writes_a_parsed_spec():
    out = hierarchy_node(_state("when will I get married?"))
    assert out["spec"] is not None
    assert out["spec"].routing.domains


def test_the_node_writes_a_retrieval_plan():
    out = hierarchy_node(_state("when will I get married?"))
    plan = out["retrieval_plan"]
    assert plan is not None
    assert plan.domains is None or "domain.relationship" in plan.domains


def test_the_node_is_deterministic():
    """Everything up to the fan-out must be reproducible. Two runs of the
    same question that disagree make a stored answer unreviewable."""
    q = "will my business grow next year?"
    a, b = hierarchy_node(_state(q)), hierarchy_node(_state(q))
    assert a["koonji_domain"] == b["koonji_domain"]
    assert a["hierarchy"] is b["hierarchy"]


def test_the_node_makes_no_model_call():
    """The deterministic prefix stays deterministic, and the signature is the
    strongest way to say so - there is no client to call one with."""
    assert "client" not in inspect.signature(hierarchy_node).parameters


def test_the_time_scope_comes_from_query_time_not_the_clock():
    """A Prashna cast for a stated moment, or a backtest about 1998, must not
    be planned against today."""
    state = _state("what happens in the next three years?")
    state["query_time"] = datetime(1998, 6, 1, 9, 0)
    out = hierarchy_node(state)
    plan = out["retrieval_plan"]
    if plan.when is not None:
        assert plan.when.year <= 2001


def test_every_key_returned_is_declared_in_the_state():
    from rishivan.graph.state import RishivanState

    out = hierarchy_node(_state("when will I get married?"))
    assert set(out) <= set(RishivanState.__annotations__)
