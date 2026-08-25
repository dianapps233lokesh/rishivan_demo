"""Build the Rishi-voiced prompt, stream the answer - or decline to.

Port of `council_consult:536-564`. The declining half is not an error path: the
corpus being silent on a question is a legitimate answer, and composing prose
over nothing retrieved is the failure the whole grounding discipline exists to
prevent.
"""

from __future__ import annotations

from typing import Generator

from rishivan.graph.state import RishivanState

INSUFFICIENT = (
    "I don't have material in the ingested books that speaks to this clearly "
    "enough to answer. Saying so is the answer — I'd rather not compose "
    "something that reads like a reading and isn't one."
)
"""Carried in `state["message"]`, NOT streamed.

`council_consult` returned `answer_stream=None` here, and `streamlit_app`
renders its own warning for that case. Streaming this instead would put a canned
refusal inside a Rishi answer card, avatar and sign-off included - a better
product decision, quite possibly, but a product decision, and Phase 1 changes
control flow only. Phase 5 owns the surface."""


def answer_node(state: RishivanState, *, client) -> dict:
    from rishivan.council.client import model_name
    from rishivan.council.prompts import build_rishi_prompt, rule_context

    model = model_name("flash")
    prompt = build_rishi_prompt(
        rishi_name=state["primary_rishi"],
        domain=state["query_domain"],
        question=state["question"],
        context=state.get("context_text", ""),
        chart_facts=state.get("chart_facts"),
        conversation=state.get("conversation"),
        rules=rule_context(state.get("matched_rules") or []),
        life_domain=(state.get("routing") or {}).get("primary"),
        contributors=state.get("contributor_reports") or (),
    )

    def stream() -> Generator[str, None, None]:
        for chunk in client.models.generate_content_stream(
            model=model, contents=prompt
        ):
            if chunk.text:
                yield chunk.text

    return {"outcome": "served", "answer_stream": stream()}


def insufficient_node(state: RishivanState) -> dict:
    return {
        "outcome": "insufficient",
        "message": INSUFFICIENT,
        # None, deliberately - see INSUFFICIENT above.
        "answer_stream": None,
    }
