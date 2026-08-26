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

def varga_select_node(state: RishivanState) -> dict:
    from rishivan.council.hierarchy import DEFAULT_DOMAIN
    from rishivan.varga.confidence import resolve_confidence
    from rishivan.varga.select import select_vargas

    chart = state.get("chart")
    if chart is None:
        return {"vargas": None}

    # Settled once by `hierarchy_node`. This used to read
    # `routing["koonji_domains"]`, which nothing in the graph ever wrote - so
    # every request, whatever it asked about, selected vargas for temperament.
    domain = state.get("koonji_domain") or DEFAULT_DOMAIN

    confidence = resolve_confidence(
        state.get("birth_data"), state.get("birth_confidence")
    )
    return {"vargas": select_vargas(chart, domain, confidence)}
