"""Blueprint §7: which divisional charts may speak for this question.

Runs after the diagnosis and before grounding, because the selection decides
what goes into the fact set - and the fact set is compiled once. Filtering
afterwards would mean paying for 16 divisions to use three.

The withheld list is the output that matters. "D60 needs a birth time to the
minute; yours is recorded to the hour, so I have not used it" is a sentence the
narrative layer can say only because this node recorded why.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState

DEFAULT_DOMAIN = "domain.temperament"
"""What a question with no routed domain reads from. The self, broadly - which
is what a question nobody could route is usually about."""


def varga_select_node(state: RishivanState) -> dict:
    from rishivan.varga.confidence import resolve_confidence
    from rishivan.varga.select import select_vargas

    chart = state.get("chart")
    if chart is None:
        return {"vargas": None}

    routing = state.get("routing") or {}
    domains = routing.get("koonji_domains") or []
    domain = domains[0] if domains else DEFAULT_DOMAIN

    confidence = resolve_confidence(
        state.get("birth_data"), state.get("birth_confidence")
    )
    return {"vargas": select_vargas(chart, domain, confidence)}
