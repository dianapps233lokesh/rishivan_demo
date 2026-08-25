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
        contributors=state.get("contributors") or (),
    )

    def stream() -> Generator[str, None, None]:
        for chunk in client.models.generate_content_stream(
            model=model, contents=prompt
        ):
            if chunk.text:
                yield chunk.text

    return {"outcome": "served", "answer_stream": stream()}


def insufficient_node(state: RishivanState) -> dict:
    """Still fills `answer_stream`, because every caller reads the answer the
    same way and a special case here would spread to all of them."""
    return {
        "outcome": "insufficient",
        "message": INSUFFICIENT,
        "answer_stream": iter([INSUFFICIENT]),
    }
