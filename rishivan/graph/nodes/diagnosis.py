"""Blueprint §6: the chart becomes a diagnosis before anything reasons over it.

One node, between each chart node and grounding. It reads `chart` and writes
`chart_state` — the canonical, immutable diagnosis every Rishi will share
(spec C1). Nothing downstream consumes it yet; Phase 4's Rishi nodes do.

Placed after the chart and before retrieval on purpose. The diagnosis is what
Phase 3's varga selection and Phase 4's evidence hierarchies read to decide
*what to retrieve*, so it has to exist before the search is planned, not after.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState


def chart_state_node(state: RishivanState) -> dict:
    """Diagnose the chart, or say plainly that there is none.

    A general question never casts a chart and still passes through here,
    because the graph is linear on that stretch. Returning an empty diagnosis is
    cheaper and clearer than a router whose only job is to skip one node.
    """
    from rishivan.chartstate.build import build_chart_state

    chart = state.get("chart")
    if chart is None:
        return {"chart_state": None, "chart_digest": ""}

    diagnosis = build_chart_state(chart, when=state.get("query_time"))
    return {"chart_state": diagnosis, "chart_digest": diagnosis.chart_digest}
