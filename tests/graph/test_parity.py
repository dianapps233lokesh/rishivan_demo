"""Phase 1 claims to change control flow and nothing else. This is the claim.

Model output is not compared — it is not deterministic. What is compared is
every decision made *before* a model is called, which is the half that can be
wrong silently: which domain, which chart, which renderer, which retrieval
filter, and whether the corpus was declared silent.

The eval corpus (`tests/eval/prompts.py`) is the source of cases, so this stays
honest as that corpus grows.
"""

import pathlib
from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData
from rishivan.council.domains import QueryDomain
from rishivan.graph.build import EDGE_MAPS
from rishivan.graph.edges import (
    route_after_chart,
    route_after_intake,
    route_chart_kind,
)
from rishivan.graph.nodes.chart import chart_natal_node
from rishivan.graph.state import initial_state

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


def _cases():
    """Loaded by path, not by `import tests.eval.prompts`.

    A stray `tests.py` at the repo root shadows the `tests/` package, and then
    that import resolves to the wrong module and drags in Vertex credentials at
    collection time. Loading by file path is immune to whatever happens to be
    sitting next to the package.
    """
    import importlib.util
    import sys

    name = "_eval_prompts"
    if name not in sys.modules:
        path = pathlib.Path(__file__).resolve().parents[1] / "eval" / "prompts.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        # Registered before exec: `@dataclass` resolves its own annotations
        # through `sys.modules[cls.__module__]`, and an unregistered module
        # makes that lookup return None.
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name].PIPELINE_CASES


def _state_for(case):
    """The state as it stands when `route_after_intake` runs, with the
    classification the case implies."""
    s = initial_state(
        case.question,
        birth_data=BIRTH if case.needs_birth_data else None,
        query_time=WHEN,
    )
    s["classification"] = {
        "is_smalltalk_or_gibberish": bool(case.expect_is_warmth),
        "intent": "chart" if case.expect_chart_table else "predict",
    }
    try:
        s["query_domain"] = QueryDomain(case.expect_domain or "general")
    except ValueError:
        s["query_domain"] = QueryDomain.GENERAL
    return s


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c.id)
def test_every_eval_case_routes_to_a_declared_destination(case):
    """A router returning a value the edge map does not carry is a KeyError at
    runtime, on whichever branch that case happens to be."""
    assert route_after_intake(_state_for(case)) in EDGE_MAPS["intake"]


@pytest.mark.parametrize(
    "case", [c for c in _cases() if c.expect_is_warmth], ids=lambda c: c.id
)
def test_smalltalk_cases_reach_warmth(case):
    assert route_after_intake(_state_for(case)) == "warmth"


@pytest.mark.parametrize(
    "case", [c for c in _cases() if c.expect_chart_table], ids=lambda c: c.id
)
def test_chart_display_cases_reach_a_renderer(case):
    """"show me my D9" must return a table, not a reading. Each of these ends at
    a renderer and never touches retrieval or a model."""
    s = _state_for(case)
    s["chart"] = object()
    assert route_after_chart(s) == "chart_render"
    assert route_chart_kind(s) in EDGE_MAPS["chart_render"]


@pytest.mark.parametrize(
    "case",
    [c for c in _cases() if c.expect_domain == "natal" and not c.expect_chart_table],
    ids=lambda c: c.id,
)
def test_natal_reading_cases_cast_a_birth_chart(case):
    assert route_after_intake(_state_for(case)) == "chart_natal"


class TestDeterminism:
    def test_the_chart_prefix_is_reproducible(self):
        """Everything before the first model call must be reproducible from the
        same inputs, or a trace cannot be replayed."""
        a = chart_natal_node(initial_state("q", birth_data=BIRTH))
        b = chart_natal_node(initial_state("q", birth_data=BIRTH))
        assert a["chart_summary"] == b["chart_summary"]
        assert a["chart_facts"] == b["chart_facts"]

    def test_routing_is_reproducible(self):
        from rishivan.graph.nodes.ground import council_routing_node

        s = initial_state("when will I marry?")
        s["classification"] = {}
        assert council_routing_node(s) == council_routing_node(s)


class TestCheckpointing:
    def test_a_checkpointer_is_available_for_conversations(self):
        """`turn_type: followup` should resume, not recompute — which is also
        what stops turn 14 disagreeing with turn 13 about a fact."""
        from rishivan.graph.build import checkpointer_for

        assert checkpointer_for("demo") is not None

    def test_a_generator_in_state_cannot_be_checkpointed(self, monkeypatch):
        """The constraint, recorded so it is not rediscovered in Phase 5.

        `answer_stream` is a live generator, and no checkpointer can serialise
        one. So the graph runs unpersisted today, which is correct rather than
        merely convenient: what a resumed conversation needs is the *evidence*
        of the earlier turn, not a half-consumed stream of its prose.

        Phase 5 makes this work by putting an `AnswerPlan` in state and moving
        narration outside the graph. Until then, checkpointing is available and
        deliberately not wired into `council_consult`.
        """
        from rishivan.council import classifier, warmth
        from rishivan.graph.build import build_graph, checkpointer_for

        monkeypatch.setattr(
            classifier, "classify_query",
            lambda client, question, **kw: {
                "is_smalltalk_or_gibberish": True, "primary_rishi": "vyom",
                "query_domain": QueryDomain.GENERAL,
            },
        )
        monkeypatch.setattr(
            warmth, "respond_warmly", lambda client, question, **kw: iter(["hi"])
        )
        graph = build_graph(store=None, client=None,
                            checkpointer=checkpointer_for("demo"))
        with pytest.raises(TypeError, match="not msgpack serializable"):
            graph.invoke(
                initial_state("hello"),
                config={"configurable": {"thread_id": "conversation-1"}},
            )

    def test_the_unpersisted_graph_is_what_ships(self, monkeypatch):
        """No checkpointer, and the same turn runs clean."""
        from rishivan.council import classifier, warmth
        from rishivan.graph.build import build_graph

        monkeypatch.setattr(
            classifier, "classify_query",
            lambda client, question, **kw: {
                "is_smalltalk_or_gibberish": True, "primary_rishi": "vyom",
                "query_domain": QueryDomain.GENERAL,
            },
        )
        monkeypatch.setattr(
            warmth, "respond_warmly", lambda client, question, **kw: iter(["hi"])
        )
        out = build_graph(store=None, client=None).invoke(initial_state("hello"))
        assert out["is_warmth"] is True
