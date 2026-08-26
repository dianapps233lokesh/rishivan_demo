"""Build the narrative gate, and put plain data in state.

The last deterministic node in the graph. Everything before it computed
evidence; this decides what may be said about that evidence, and hands the
answer out as a structure rather than as prose.

**Why it is a node and narration is not.** What leaves the graph has to be
serialisable, or the graph cannot be checkpointed - and a resumed conversation
needs the earlier turn's *evidence*, not a half-consumed stream of its prose.
So the plan is computed here, inside the graph, where it is checkpointed with
everything that produced it; the generator is built one layer out, in
`council_consult`, where nothing needs to persist it.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState


def answer_plan_node(state: RishivanState) -> dict:
    from rishivan.council.answer_plan import build_answer_plan

    return {
        # The graph's terminal outcome. `answer_node` used to set it on its way
        # to building a stream; with narration outside the graph, the last node
        # that runs has to say the run was served.
        "outcome": "served",
        "answer_plan": build_answer_plan(
            question=state["question"],
            domain=state.get("koonji_domain") or "",
            hierarchy=state.get("hierarchy"),
            reading=state.get("reading"),
            reports=state.get("reports") or (),
            audit=state.get("audit"),
            timing=state.get("timing"),
            vargas=state.get("vargas"),
            unreviewed=bool(state.get("reading_is_unreviewed")),
        )
    }
