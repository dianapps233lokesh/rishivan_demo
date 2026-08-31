"""Assemble the direct lane's prompt. Make no call.

The node writes a string; `council/direct.py` sends it. That split is the same
one `answer_plan` and `narrate` already make and it buys the same two things: a
graph whose final state is plain data a checkpointer can persist, and a prompt
that can be asserted against without credentials.

This node is where the retrieval lane's four steps - grounding, council routing,
page retrieval and rule matching - are replaced by one: describe the method, and
hand over the chart.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState


def direct_read_node(state: RishivanState, *, for_analysis: bool = False) -> dict:
    """The prompt, for whichever half of the lane is about to read it.

    `for_analysis` is bound by the builder, not decided here, because which lane
    is running is a fact about the graph rather than about this turn. It swaps
    the closing OUTPUT block and nothing else: both lanes reason over the same
    chart, the same method and the same facts, and only the recipient differs.
    """
    from rishivan.council.direct_prompt import build_with_report

    prompt, report = build_with_report(state, for_analysis=for_analysis)
    return {"direct_prompt": prompt, "requirement_report": report}
