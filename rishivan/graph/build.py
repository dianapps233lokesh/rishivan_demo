"""Assemble the graph.

`EDGE_MAPS` and `STATIC_EDGES` are module-level data rather than inline
arguments so the tests can walk the topology. A mistyped destination is
otherwise a runtime KeyError on a branch nobody exercises until a user takes it,
and that is precisely the class of bug this refactor exists to remove.
"""

from __future__ import annotations

from functools import partial

from langgraph.graph import END, START, StateGraph

from rishivan.graph import edges as R
from rishivan.graph.nodes import answer, chart, ground, intake
from rishivan.graph.nodes import retrieve as retrieval
from rishivan.graph.state import RishivanState

NODE_NAMES = (
    "intake", "warmth",
    "chart_natal", "chart_moment", "panchang",
    "chart_render", "render_varga", "render_dasha", "render_ashtakavarga",
    "render_numerology",
    "ground", "council_routing", "retrieve", "answer", "insufficient",
)

EDGE_MAPS: dict[str, dict[str, str]] = {
    "intake": {
        "warmth": "warmth",
        "chart_natal": "chart_natal",
        "chart_moment": "chart_moment",
        "panchang": "panchang",
        "retrieve": "ground",
    },
    "chart_natal": {
        "chart_render": "chart_render",
        "panchang": "panchang",
        "retrieve": "ground",
    },
    "chart_moment": {
        "chart_render": "chart_render",
        "panchang": "panchang",
        "retrieve": "ground",
    },
    "chart_render": {
        "render_varga": "render_varga",
        "render_dasha": "render_dasha",
        "render_ashtakavarga": "render_ashtakavarga",
        "render_numerology": "render_numerology",
    },
    "retrieve": {"answer": "answer", "insufficient": "insufficient"},
}
"""router source -> {router return value: node to run}.

The retrieval routers return `"retrieve"` but land on `ground`, because
grounding and council routing sit between the chart and the search. Keeping the
router's vocabulary ("go and retrieve") separate from the node that starts that
work means adding a step to the retrieval pipeline never edits a router.
"""

STATIC_EDGES: dict[str, str] = {
    "warmth": END,
    "panchang": "ground",
    "ground": "council_routing",
    "council_routing": "retrieve",
    "render_varga": END,
    "render_dasha": END,
    "render_ashtakavarga": END,
    "render_numerology": END,
    "answer": END,
    "insufficient": END,
}


def _chart_render_passthrough(state: RishivanState) -> dict:
    """`chart_render` is a branch point with no work of its own.

    LangGraph needs a node to hang a conditional edge on. Naming it rather than
    folding the branch into the chart nodes keeps `route_chart_kind` separately
    testable, which is the whole reason for this refactor.
    """
    return {}


def build_graph(*, store, client, checkpointer=None):
    g = StateGraph(RishivanState)

    g.add_node("intake", partial(intake.intake_node, client=client))
    g.add_node("warmth", partial(intake.warmth_node, client=client))
    g.add_node("chart_natal", chart.chart_natal_node)
    g.add_node("chart_moment", chart.chart_moment_node)
    g.add_node("panchang", chart.panchang_node)
    g.add_node("chart_render", _chart_render_passthrough)
    g.add_node("render_varga", chart.render_varga_node)
    g.add_node("render_dasha", chart.render_dasha_node)
    g.add_node("render_ashtakavarga", chart.render_ashtakavarga_node)
    g.add_node("render_numerology", chart.render_numerology_node)
    g.add_node("ground", ground.ground_node)
    g.add_node("council_routing", ground.council_routing_node)
    g.add_node(
        "retrieve",
        partial(retrieval.retrieve_node, vector_store=store, client=client),
    )
    g.add_node("answer", partial(answer.answer_node, client=client))
    g.add_node("insufficient", answer.insufficient_node)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", R.route_after_intake, EDGE_MAPS["intake"])
    for node in ("chart_natal", "chart_moment"):
        g.add_conditional_edges(node, R.route_after_chart, EDGE_MAPS[node])
    g.add_conditional_edges(
        "chart_render", R.route_chart_kind, EDGE_MAPS["chart_render"]
    )
    g.add_conditional_edges(
        "retrieve", R.route_after_retrieval, EDGE_MAPS["retrieve"]
    )
    for source, destination in STATIC_EDGES.items():
        g.add_edge(source, destination)

    return g.compile(checkpointer=checkpointer)


def checkpointer_for(env: str = "demo"):
    """Thread id is the conversation id, so a follow-up resumes rather than
    recomputes - which is also what stops turn 14 disagreeing with turn 13 about
    a fact.

    In-memory for the demo: Streamlit Cloud has no Postgres, and the demo's own
    requirements deliberately exclude it.

    **Not wired into `council_consult` yet, and that is deliberate.** State
    carries `answer_stream`, a live generator, and no checkpointer can serialise
    one - `graph.invoke` with a checkpointer raises on it, which
    `tests/graph/test_parity.py` pins. Phase 5 resolves it properly by putting a
    serialisable `AnswerPlan` in state and moving narration outside the graph.
    What a resumed conversation actually needs is the earlier turn's evidence,
    not a half-consumed stream of its prose.
    """
    from langgraph.checkpoint.memory import MemorySaver

    if env == "demo":
        return MemorySaver()

    from langgraph.checkpoint.postgres import PostgresSaver

    from rishivan.config import settings

    return PostgresSaver.from_conn_string(settings.DATABASE_URL)
