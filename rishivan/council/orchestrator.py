"""Council Orchestrator — the adapter over the council graph.

The pipeline itself lives in `rishivan.graph`: intake and warmth, the natal and
moment chart nodes, panchang, the four table renderers, grounding, council
routing, retrieval and the answer. `rishivan/graph/README.md` has the topology.

This module used to be that pipeline, 564 lines with every branch inline, which
made the branches untestable — you could not ask "what happens to a muhurta
question with no birth data" without running chart computation, embeddings and
two model calls. Now a node does work and an edge chooses, and every router is a
pure function with a table-driven test.

What is left here is the call signature, kept exactly, because
`streamlit_app.py` and `tests/eval/run_eval.py` depend on it and a refactor that
also moved its callers could not be reviewed against the behaviour it claims to
preserve.
"""
from __future__ import annotations

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def council_consult(
    client,
    store,
    question: str,
    *,
    rishi_override: str | None = None,
    birth_data=None,
    query_time: datetime | None = None,
    target_time: datetime | None = None,
    lat: float | None = None,
    lon: float | None = None,
    tz_offset: float = 5.5,
    place: str = "",
    conversation=None,         # rishivan.council.conversation.Conversation
    direct: bool = False,      # the direct lane; thread_id stays last, see below
    thread_id: str | None = None,
) -> dict:
    """Full Council consultation, run as a graph.

    Kept as a function with this exact signature because `streamlit_app.py` and
    `tests/eval/run_eval.py` call it, and a refactor that also changes its
    callers cannot be reviewed against the behaviour it claims to preserve.

    Everything that used to be an `if` in this function is now a node or a
    conditional edge in `rishivan.graph` - see `rishivan/graph/README.md` for
    the topology. This body should stay an adapter; if it grows branches again,
    the graph is being worked around rather than extended.

    `thread_id` opts into persistence. Pass a conversation id and the run is
    checkpointed under it, so a follow-up resumes rather than recomputes -
    which is also what stops turn 14 disagreeing with turn 13 about a fact.
    Omit it and nothing is persisted, which is exactly the behaviour every
    caller had before Phase 5. Opt-in rather than default because a checkpointer
    that nobody asked for is a database nobody provisioned.

    `direct=True` takes the direct lane and adds `direct_prompt` to the result;
    `docs/superpowers/specs/2026-08-27-direct-call-reading-design.md` says why.

    Returns a dict with keys:
      primary_rishi, rishi_title, query_domain, classification,
      chart_summary, chart_facts, sources, search_query, answer_stream
    """
    from rishivan.council import narrate
    from rishivan.graph.build import build_graph, runtime_for
    from rishivan.graph.state import RESULT_KEYS, initial_state

    checkpointer, config = runtime_for(thread_id)
    graph = build_graph(store=store, client=client,
                        checkpointer=checkpointer, direct=direct)
    final = graph.invoke(initial_state(
        question,
        rishi_override=rishi_override,
        birth_data=birth_data,
        query_time=query_time,
        target_time=target_time,
        lat=lat,
        lon=lon,
        tz_offset=tz_offset,
        place=place,
        conversation=conversation,
        thread_id=thread_id,
    ), config=config)

    # Narration happens HERE, not in the graph. The graph's final state has to
    # be plain data for a checkpointer to persist it, and a live generator is
    # the one thing that cannot be - so the plan comes out of the graph and the
    # stream is built from it, one layer out. The caller contract is unchanged:
    # `answer_stream` is still a generator of text chunks.
    result = {key: final.get(key) for key in RESULT_KEYS}
    result["answer_stream"] = narrate.stream_for(final, client=client)
    result["answer_plan"] = final.get("answer_plan")
    # Set only on the paths that produce them, and read with `.get()` by every
    # caller. Promising them unconditionally would be a new contract.
    for optional in ("routing", "panchang", "life_domain", "direct_prompt"):
        if final.get(optional):
            result[optional] = final[optional]
    if final.get("context_text"):
        result["_context_text"] = final["context_text"]
    return result
