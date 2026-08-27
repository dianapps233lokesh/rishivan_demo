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


def direct_read_node(state: RishivanState) -> dict:
    from rishivan.council.direct_prompt import build_direct_prompt

    return {"direct_prompt": build_direct_prompt(state)}
