"""Classify the turn, route it, and settle the domain before anything is cast.

Model-calling collaborators are injected. A node that builds its own client
cannot be tested without a network, and an untestable node is where the next
564-line function starts.

There is no "ask the user for birth details" node here, and that is a faithful
port rather than an omission. `council_consult:138` rewrites a natal question
with no birth data into PRASHNA - the moment of asking becomes the chart. Adding
a prompt-for-input branch would be new product behaviour, and Phase 1 changes
control flow only. It is worth revisiting in a later phase; it is not worth
smuggling in here.
"""

from __future__ import annotations

import logging
from typing import Callable

from rishivan.council.domains import QueryDomain
from rishivan.graph.state import RishivanState

logger = logging.getLogger(__name__)

DEFAULT_WARMTH_RISHI = "vyom"
"""A neutral, collective-feeling voice for a greeting that has no thread yet."""


def _domain(raw: object) -> QueryDomain:
    """Whatever the classifier said, as a `QueryDomain`.

    Accepts the enum (what `classify_query` returns today) and the string (what
    survives a JSON round trip through a checkpointer). An unrecognised value
    falls back to the widest scope rather than raising - a classifier having a
    bad day is not an outage.
    """
    if isinstance(raw, QueryDomain):
        return raw
    try:
        return QueryDomain(str(raw))
    except ValueError:
        logger.warning("unknown query_domain %r - falling back to GENERAL", raw)
        return QueryDomain.GENERAL


def intake_node(
    state: RishivanState,
    *,
    classify: Callable | None = None,
    client=None,
    model: str = "",
) -> dict:
    """Port of `council_consult` lines 100-152."""
    if classify is None:
        from rishivan.council.classifier import classify_query as classify
    if not model:
        from rishivan.council.client import model_name

        model = model_name("flash")

    from rishivan.council.personas import get_persona
    from rishivan.council.routing import route_question

    classification = classify(
        client, state["question"], model=model,
        conversation=state.get("conversation"),
    ) or {}

    override = state.get("rishi_override")
    if override:
        # Written back into the classification, not just the result key:
        # downstream prompts read the classification.
        classification["primary_rishi"] = override
    rishi = classification.get("primary_rishi", DEFAULT_WARMTH_RISHI)

    domain = _domain(classification.get("query_domain", QueryDomain.GENERAL))
    if domain == QueryDomain.NATAL and state.get("birth_data") is None:
        logger.info("Natal query but no birth data - falling back to PRASHNA")
        domain = QueryDomain.PRASHNA
    # Written back for the same reason as the override: a prompt that still
    # read `natal` here would describe a birth chart that was never cast.
    classification["query_domain"] = domain

    routing = route_question(state["question"])

    return {
        "classification": classification,
        "routing": {
            "primary": routing.primary,
            "secondary": list(routing.secondary),
            "application": routing.application,
            "universes": sorted(routing.universes),
            "scores": dict(routing.scores),
            "matched": {k: list(v) for k, v in routing.matched.items()},
        },
        "primary_rishi": rishi,
        "rishi_title": get_persona(rishi).title,
        "query_domain": domain,
        "search_query": state["question"],
    }


def warmth_node(
    state: RishivanState,
    *,
    respond: Callable | None = None,
    client=None,
    model: str = "",
) -> dict:
    """Small talk. No chart, no retrieval, no rules - and no apology for it.

    Port of `council_consult` lines 111-132. Stays with whoever the seeker was
    already speaking to, because a greeting mid-conversation should not switch
    voices.
    """
    if respond is None:
        from rishivan.council.warmth import respond_warmly as respond
    if not model:
        from rishivan.council.client import model_name

        model = model_name("flash")

    from rishivan.council.personas import get_persona

    conversation = state.get("conversation")
    rishi = (
        conversation.current_rishi
        if conversation is not None and not conversation.is_empty
        else DEFAULT_WARMTH_RISHI
    )

    return {
        "primary_rishi": rishi,
        "rishi_title": get_persona(rishi).title,
        "is_warmth": True,
        "outcome": "non_analytic",
        "answer_stream": respond(
            client, state["question"], model=model, conversation=conversation
        ),
    }
