"""Blueprint §8: promise → activation → trigger → peak → fading.

Sibling to `varga_select`; neither reads the other's output. Both read
`chart_state`, which is what makes them independent by construction and lets a
later phase run them concurrently without a reducer.

**The promise comes from the reading, not from here.** A natal promise is a
fired rule with a citation, and this node times a promise rather than
adjudicating one. With no reading yet - which is the case until Phase 4 moves
retrieval ahead of it - `promise` is False and no window is produced. That is
the correct answer, not a missing feature: the dasha arithmetic would happily
yield a date, and yielding one is how a period becomes a prediction nobody
grounded.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rishivan.graph.state import RishivanState

DEFAULT_HORIZON_YEARS = 10
"""How far ahead a timing question looks when it does not say. Long enough for a
mahadasha boundary to fall inside it, short enough that the window means
something."""

DEFAULT_DOMAIN = "domain.temperament"


def dasha_windows_node(state: RishivanState) -> dict:
    from rishivan.timing.query import PRIMARY_SYSTEM, TimingReport, windows_between

    chart = state.get("chart")
    chart_state = state.get("chart_state")
    if chart is None or chart_state is None:
        return {"timing": None}

    routing = state.get("routing") or {}
    domains = routing.get("koonji_domains") or []
    domain = domains[0] if domains else DEFAULT_DOMAIN

    start = state.get("query_time") or datetime.now()
    end = start + timedelta(days=365.2425 * DEFAULT_HORIZON_YEARS)

    reading = state.get("reading")
    promise = bool(reading and reading.promises(domain))

    window = windows_between(
        chart, chart_state, domain, start, end, promise=promise
    )
    return {"timing": TimingReport(by_system={PRIMARY_SYSTEM: window})}
