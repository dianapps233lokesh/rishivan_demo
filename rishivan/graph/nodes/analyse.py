"""Reason over the chart, then take away what the chart did not license.

The only node in either lane that calls the `pro` tier. It sits between the
prompt builder and the narrator, and it does two things that must not be
separated: it makes the call, and it runs `apply_gate` against the very prompt
that was sent. Gating anywhere else would mean gating against a second assembly
of the prompt, and a gate that checks a different string from the one the model
saw is not a gate.

A failure here does not raise. `verdict` stays `None`, the reason is recorded
for the trace, and `narrate.stream_for` reports the failure to the reader — the
turn is lost, but the run still reaches `persist`, and a lost turn is exactly
the kind a trace is worth having for.
"""

from __future__ import annotations

import logging

from rishivan.graph.state import RishivanState

logger = logging.getLogger(__name__)


def analyse_node(state: RishivanState, *, client) -> dict:
    from rishivan.council.analyse import analyse
    from rishivan.council.verdict import VerdictError, apply_gate

    prompt = state.get("direct_prompt") or ""
    try:
        verdict = analyse(prompt, client=client)
    except VerdictError as exc:
        logger.warning("the two-call lane produced no verdict: %s", exc)
        return {"verdict": None, "verdict_error": str(exc), "verdict_attempted": True}

    gated = apply_gate(verdict, prompt)
    if gated.dropped:
        # Worth a log line rather than only a trace row: a lane that starts
        # dropping windows every turn is a prompt regression, and the first
        # place anybody looks is the console.
        logger.info(
            "the gate removed %d item(s) from the verdict: %s",
            len(gated.dropped), "; ".join(gated.dropped),
        )
    return {"verdict": gated, "verdict_error": "", "verdict_attempted": True}
