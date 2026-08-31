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
from rishivan.graph.nodes import (
    analyse, answer, answer_plan, chart, diagnosis, direct, ground, hierarchy, intake,
    koonji, persist, rishi, sakshi, synthesis, timing, varga,
)  # noqa: F401 - `answer` re-exported for callers still importing it
from rishivan.graph.nodes import retrieve as retrieval
from rishivan.graph.state import RishivanState

NODE_NAMES = (
    "intake", "warmth",
    "chart_natal", "chart_moment", "panchang", "chart_state", "hierarchy",
    "varga_select", "koonji_read", "dasha_windows",
    "chart_render", "render_varga", "render_dasha", "render_ashtakavarga",
    "render_numerology", "render_shadbala", "render_unsupported",
    "ground", "council_routing", "retrieve",
    "fan_out", "rishi", "sakshi", "re_examine", "synthesis",
    "answer_plan", "persist", "insufficient",
)

EDGE_MAPS: dict[str, dict[str, str]] = {
    "intake": {
        "warmth": "warmth",
        "chart_natal": "chart_natal",
        "chart_moment": "chart_moment",
        "panchang": "panchang",
        "retrieve": "ground",
    },
    # Both chart nodes route "retrieve" through the §6 diagnosis. The router's
    # vocabulary stays "go and retrieve"; what sits between the chart and the
    # search is the graph's business, so adding a stage never edits a router.
    "chart_natal": {
        "chart_render": "chart_render",
        "panchang": "panchang",
        "retrieve": "chart_state",
    },
    "chart_moment": {
        "chart_render": "chart_render",
        "panchang": "panchang",
        "retrieve": "chart_state",
    },
    "chart_render": {
        "render_varga": "render_varga",
        "render_dasha": "render_dasha",
        "render_ashtakavarga": "render_ashtakavarga",
        "render_numerology": "render_numerology",
        "render_shadbala": "render_shadbala",
        "render_unsupported": "render_unsupported",
    },
    # Retrieval no longer goes straight to prose. `fan_out` is the council;
    # `insufficient` is unchanged and still short-circuits, because nothing
    # retrieved and nothing fired is an answer rather than an error.
    "retrieve": {"answer": "fan_out", "insufficient": "insufficient"},
    "sakshi": {"re_examine": "re_examine", "synthesis": "synthesis"},
    # Both fan-outs return `Send`s, so these mappings declare the *permitted*
    # destinations rather than translating a return value. They are in the
    # table anyway, because `test_every_node_leads_somewhere` walks it and a
    # node whose only exit is registered inline is a node that test cannot see.
    "fan_out": {"rishi": "rishi", "synthesis": "synthesis"},
    "re_examine": {"rishi": "rishi", "synthesis": "synthesis"},
}
"""router source -> {router return value: node to run}.

The retrieval routers return `"retrieve"` but land on `ground`, because
grounding and council routing sit between the chart and the search. Keeping the
router's vocabulary ("go and retrieve") separate from the node that starts that
work means adding a step to the retrieval pipeline never edits a router.
"""

STATIC_EDGES: dict[str, str] = {
    "warmth": END,
    # Panchang goes through the diagnosis too, not straight to grounding: a
    # chart question that also mentions panchang took this edge and reached the
    # Rishis with no §6 diagnosis at all. `chart_state_node` returns an empty
    # diagnosis when there is no chart, so the chartless panchang path is
    # unaffected.
    "panchang": "chart_state",
    # The dependency chain, straightened. Each of these needs the one before
    # it and Phase 4 is where that became true rather than aspirational:
    #
    #   hierarchy     settles the domain          -> varga_select needs it
    #   varga_select  picks the divisions         -> the fact set is built once
    #   koonji_read   fires the rules             -> the promise comes from here
    #   dasha_windows times that promise
    #
    # Before this, varga_select and dasha_windows were siblings reading a
    # routing key nothing wrote, and the timing node read a promise from a
    # reading that was always None. Both were correct and both were inert.
    "chart_state": "hierarchy",
    "hierarchy": "varga_select",
    "varga_select": "koonji_read",
    "koonji_read": "dasha_windows",
    "dasha_windows": "ground",
    "ground": "council_routing",
    "council_routing": "retrieve",
    "render_varga": END,
    "render_dasha": END,
    "render_ashtakavarga": END,
    "render_numerology": END,
    "render_shadbala": END,
    "render_unsupported": END,
    # The council. `rishi` is one node reached by many `Send`s; `sakshi` audits
    # the reports it produced; `re_examine` fans back out to the Rishis a
    # finding names, at most once, and returns through `sakshi` - which is why
    # the bound lives in `route_after_sakshi` rather than in a while loop.
    "rishi": "sakshi",
    # The gate sits between the council and the prose, deliberately: prose is
    # generated FROM the plan, so anything absent from the plan is absent from
    # the prompt and cannot be said however the generation goes.
    "synthesis": "answer_plan",
    # Narration happens in `council_consult`, from the plan - a live generator
    # in state is not serialisable, and a graph that puts one there cannot be
    # checkpointed. See `council/narrate.py`.
    "answer_plan": "persist",
    "persist": END,
    # An insufficient turn is traced too. Why a question produced no reading
    # is exactly what a trace is for, and it is the case most worth reviewing.
    "insufficient": "persist",
}


DIRECT_NODE_NAMES = (
    "intake", "warmth",
    "chart_natal", "chart_moment", "panchang", "chart_state", "hierarchy",
    "varga_select",
    "chart_render", "render_varga", "render_dasha", "render_ashtakavarga",
    "render_numerology", "render_shadbala", "render_unsupported",
    "direct_read", "persist",
)
TWO_CALL_NODE_NAMES = DIRECT_NODE_NAMES + ("analyse",)
"""The same nodes, plus the reasoning call.

`analyse` is the only node in either lane that uses the `pro` tier. It sits
between the prompt and the narrator and does both halves of the seam in one
place: it makes the call, and it gates what comes back against the very prompt
that was sent."""
"""No `dasha_windows`. It times a promise, and the promise comes from a rule
engine this lane does not run - so it produced nothing usable here, and briefly
produced something worse: a window fabricated by `assume_promise=True` that the
model copied out as a dated forecast. The prompt derives its own antardasha
boundaries from the chart instead."""
"""The direct lane's nodes. Every computational one survives; retrieval, the
rule engine and the council do not."""

DIRECT_EDGE_MAPS: dict[str, dict[str, str]] = {
    # The routers are not edited, and that is the point of this table. Both
    # retrieval routers return the label "retrieve", meaning "go and do the
    # reading"; which node begins that reading is the graph's business. So the
    # direct lane is a different resolution of the same vocabulary, and
    # `tests/graph/test_edges.py`'s table stays valid as written.
    "intake": {
        "warmth": "warmth",
        "chart_natal": "chart_natal",
        "chart_moment": "chart_moment",
        "panchang": "panchang",
        # `ground` in the default lane. Here the chartless path goes through the
        # diagnosis so `hierarchy_node` still runs and the method block still
        # gets a domain - a question with no chart needs a protocol too.
        "retrieve": "chart_state",
    },
    "chart_natal": {
        "chart_render": "chart_render",
        "panchang": "panchang",
        "retrieve": "chart_state",
    },
    "chart_moment": {
        "chart_render": "chart_render",
        "panchang": "panchang",
        "retrieve": "chart_state",
    },
    "chart_render": {
        "render_varga": "render_varga",
        "render_dasha": "render_dasha",
        "render_ashtakavarga": "render_ashtakavarga",
        "render_numerology": "render_numerology",
        "render_shadbala": "render_shadbala",
        "render_unsupported": "render_unsupported",
    },
}

DIRECT_STATIC_EDGES: dict[str, str] = {
    "warmth": END,
    "panchang": "chart_state",
    "chart_state": "hierarchy",
    # koonji_read AND dasha_windows are both gone: the first fires rules this
    # lane does not use, and the second times a promise only those rules could
    # have established. The prompt derives its own period boundaries.
    "hierarchy": "varga_select",
    "varga_select": "direct_read",
    "render_varga": END,
    "render_dasha": END,
    "render_ashtakavarga": END,
    "render_numerology": END,
    "render_shadbala": END,
    "render_unsupported": END,
    # Traced like any other lane. `persist_node` reads `reading` and
    # `answer_plan` with `.get()` and tolerates both being None, and this is the
    # lane under evaluation - the one whose traces are most worth having.
    "direct_read": "persist",
    "persist": END,
}


TWO_CALL_STATIC_EDGES: dict[str, str] = {
    # The one edge the second shape changes. `direct_read` writes an analysis
    # prompt instead of a reading prompt, `analyse` calls pro and gates what
    # comes back, and `persist` traces the turn exactly as before.
    "direct_read": "analyse",
    "analyse": "persist",
}
"""Overrides on `DIRECT_STATIC_EDGES`, declared rather than branched.

A second full table would be a second place to add a node and forget. Sharing
the first and overriding one entry keeps the difference between the two shapes
readable as a difference — which is the same reason `DIRECT_EDGE_MAPS` re-maps
the routers' labels instead of editing the routers.
"""


def _chart_render_passthrough(state: RishivanState) -> dict:
    """`chart_render` is a branch point with no work of its own.

    LangGraph needs a node to hang a conditional edge on. Naming it rather than
    folding the branch into the chart nodes keeps `route_chart_kind` separately
    testable, which is the whole reason for this refactor.
    """
    return {}


def _fan_out_passthrough(state: RishivanState) -> dict:
    """The council's branch point, with no work of its own."""
    return {}


def build_graph(*, store, client, checkpointer=None, trace_sink=None,
                direct: bool = False, two_call: bool = False):
    """The council graph, or the direct lane, in one of its two shapes.

    Topologies over one node set rather than separate builders, so a change to a
    shared node cannot land in one lane and miss the others.

    `direct=True` drops retrieval, the rule engine and the council, and sends
    one prompt built from the classical method. See
    `docs/superpowers/specs/2026-08-27-direct-call-reading-design.md`.

    `two_call=True` splits that one call in two: `pro` works out what the chart
    carries and returns a `Verdict`, a gate removes anything the prompt did not
    license, and `flash` narrates what survives. It only means anything
    alongside `direct=True` — the council lane already separates deciding from
    saying, through `answer_plan` and `narrate`.
    """
    if direct:
        return _build_direct(
            store=store, client=client, checkpointer=checkpointer,
            trace_sink=trace_sink, two_call=two_call,
        )
    return _build_council(
        store=store, client=client, checkpointer=checkpointer,
        trace_sink=trace_sink,
    )


def _build_direct(*, store, client, checkpointer, trace_sink, two_call=False):
    g = StateGraph(RishivanState)

    g.add_node("intake", partial(intake.intake_node, client=client))
    g.add_node("warmth", intake.warmth_node)
    g.add_node("chart_natal", chart.chart_natal_node)
    g.add_node("chart_moment", chart.chart_moment_node)
    g.add_node("panchang", chart.panchang_node)
    g.add_node("chart_state", diagnosis.chart_state_node)
    g.add_node("hierarchy", hierarchy.hierarchy_node)
    g.add_node("varga_select", varga.varga_select_node)
    g.add_node("chart_render", _chart_render_passthrough)
    g.add_node("render_varga", chart.render_varga_node)
    g.add_node("render_dasha", chart.render_dasha_node)
    g.add_node("render_ashtakavarga", chart.render_ashtakavarga_node)
    g.add_node("render_numerology", chart.render_numerology_node)
    g.add_node("render_shadbala", chart.render_shadbala_node)
    g.add_node("render_unsupported", chart.render_unsupported_node)
    g.add_node(
        "direct_read",
        partial(direct.direct_read_node, for_analysis=two_call),
    )
    if two_call:
        g.add_node("analyse", partial(analyse.analyse_node, client=client))
    g.add_node("persist", partial(persist.persist_node, sink=trace_sink))

    g.add_edge(START, "intake")
    g.add_conditional_edges(
        "intake", R.route_after_intake, DIRECT_EDGE_MAPS["intake"]
    )
    for node in ("chart_natal", "chart_moment"):
        g.add_conditional_edges(
            node, R.route_after_chart, DIRECT_EDGE_MAPS[node]
        )
    g.add_conditional_edges(
        "chart_render", R.route_chart_kind, DIRECT_EDGE_MAPS["chart_render"]
    )
    for source, destination in DIRECT_STATIC_EDGES.items():
        if two_call and source in TWO_CALL_STATIC_EDGES:
            continue
        g.add_edge(source, destination)
    if two_call:
        for source, destination in TWO_CALL_STATIC_EDGES.items():
            g.add_edge(source, destination)

    return g.compile(checkpointer=checkpointer)


def _build_council(*, store, client, checkpointer, trace_sink):
    g = StateGraph(RishivanState)

    g.add_node("intake", partial(intake.intake_node, client=client))
    g.add_node("warmth", intake.warmth_node)
    g.add_node("chart_natal", chart.chart_natal_node)
    g.add_node("chart_moment", chart.chart_moment_node)
    g.add_node("panchang", chart.panchang_node)
    g.add_node("chart_state", diagnosis.chart_state_node)
    g.add_node("hierarchy", hierarchy.hierarchy_node)
    g.add_node("varga_select", varga.varga_select_node)
    g.add_node("koonji_read", koonji.koonji_read_node)
    g.add_node("dasha_windows", timing.dasha_windows_node)
    g.add_node("chart_render", _chart_render_passthrough)
    g.add_node("render_varga", chart.render_varga_node)
    g.add_node("render_dasha", chart.render_dasha_node)
    g.add_node("render_ashtakavarga", chart.render_ashtakavarga_node)
    g.add_node("render_numerology", chart.render_numerology_node)
    g.add_node("render_shadbala", chart.render_shadbala_node)
    g.add_node("render_unsupported", chart.render_unsupported_node)
    g.add_node("ground", ground.ground_node)
    g.add_node("council_routing", ground.council_routing_node)
    g.add_node(
        "retrieve",
        partial(retrieval.retrieve_node, vector_store=store, client=client),
    )
    g.add_node("fan_out", _fan_out_passthrough)
    g.add_node("rishi", partial(rishi.rishi_node, client=client))
    g.add_node("sakshi", partial(sakshi.sakshi_node, client=client))
    g.add_node("re_examine", sakshi.re_examine_node)
    g.add_node("synthesis", synthesis.synthesis_node)
    g.add_node("answer_plan", answer_plan.answer_plan_node)
    g.add_node("persist", partial(persist.persist_node, sink=trace_sink))
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
    # The fan-out. `fan_out` is a named branch point rather than a node,
    # because `route_rishis` returns `Send`s and LangGraph needs somewhere to
    # hang them - and because a Rishi that is never invited must still leave a
    # path to synthesis, which `_fan_out_passthrough` provides by returning an
    # empty Send list when nothing qualifies.
    g.add_conditional_edges(
        "fan_out", R.route_rishis, list(EDGE_MAPS["fan_out"].values())
    )
    g.add_conditional_edges(
        "re_examine", R.route_re_examination,
        list(EDGE_MAPS["re_examine"].values()),
    )
    g.add_conditional_edges(
        "sakshi", R.route_after_sakshi, EDGE_MAPS["sakshi"]
    )
    for source, destination in STATIC_EDGES.items():
        g.add_edge(source, destination)

    return g.compile(checkpointer=checkpointer)


_DEMO_SAVER = None
"""The in-process checkpoint store. See `checkpointer_for`."""


def runtime_for(thread_id: str | None, env: str = "demo"):
    """`(checkpointer, config)` for a run, given an optional conversation id.

    Persistence is opt-in: no thread id, no checkpointer, and the behaviour is
    exactly what every caller had before Phase 5. A checkpointer nobody asked
    for is a database nobody provisioned.

    Lives here rather than as two ternaries in `council_consult`, because that
    adapter is meant to stay branch-free and a test asserts it. The decision is
    about how the graph runs, which is this module's business.
    """
    if not thread_id:
        return None, None
    return checkpointer_for(env), {"configurable": {"thread_id": thread_id}}


def checkpointer_for(env: str = "demo"):
    """Thread id is the conversation id, so a follow-up resumes rather than
    recomputes - which is also what stops turn 14 disagreeing with turn 13 about
    a fact.

    In-memory for the demo: Streamlit Cloud has no Postgres, and the demo's own
    requirements deliberately exclude it.

    **Wired in as of Phase 5**, via `runtime_for`. It took two changes and only
    the first was foreseen: `answer_stream` left state (narration happens in
    `council_consult` now, from the `AnswerPlan`), and `AtomTable` became a
    dataclass, because LangGraph serialises dataclasses and refuses plain
    classes - `FactSet` holds one and `Reading` holds a `FactSet`, so a single
    plain class made the whole state unpersistable.

    What a resumed conversation actually needs is the earlier turn's evidence,
    not a half-consumed stream of its prose, and that is now what it gets.
    """
    from langgraph.checkpoint.memory import MemorySaver

    if env == "demo":
        # A module-level singleton, and that is the entire point of it.
        # `MemorySaver` keeps its checkpoints in the instance, so building a
        # fresh one per request gives every turn an empty store - the
        # checkpointer would be wired, configured, and persisting nothing,
        # which looks exactly like working.
        global _DEMO_SAVER
        if _DEMO_SAVER is None:
            _DEMO_SAVER = MemorySaver()
        return _DEMO_SAVER

    from langgraph.checkpoint.postgres import PostgresSaver

    from rishivan.config import settings

    return PostgresSaver.from_conn_string(settings.DATABASE_URL)
