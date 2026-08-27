"""Blueprint §8: promise → activation → trigger → peak → fading.

Sibling to `varga_select`; neither reads the other's output. Both read
`chart_state`, which is what makes them independent by construction and lets a
later phase run them concurrently without a reducer.

**The promise comes from the reading, not from here.** A natal promise is a
fired rule with a citation, and this node times a promise rather than
adjudicating one. Phase 4 put `koonji_read` immediately upstream so that the
reading exists by the time this runs; before that it never did, and every
window came back promise-less. Where there is still no reading - a chartless
question, a failed bundle - `promise` is False and no window is produced. That
is the correct answer, not a missing feature: the dasha arithmetic would happily
yield a date, and yielding one is how a period becomes a prediction nobody
grounded.

The direct lane has no reading, and passes `assume_promise=True` so the
arithmetic runs anyway. That lane's prompt labels the result as period
boundaries and asks the model for the promise judgement, which is the trade it
was designed to make - see
`docs/superpowers/specs/2026-08-27-direct-call-reading-design.md`.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rishivan.graph.state import RishivanState

DEFAULT_HORIZON_YEARS = 10
"""How far ahead a timing question looks when it does not say. Long enough for a
mahadasha boundary to fall inside it, short enough that the window means
something."""

def dasha_windows_node(state: RishivanState, *, assume_promise: bool = False) -> dict:
    from rishivan.council.hierarchy import DEFAULT_DOMAIN
    from rishivan.timing.query import PRIMARY_SYSTEM, TimingReport, windows_between

    chart = state.get("chart")
    chart_state = state.get("chart_state")
    if chart is None or chart_state is None:
        return {"timing": None}

    domain = state.get("koonji_domain") or DEFAULT_DOMAIN

    start = state.get("query_time") or datetime.now()
    end = start + timedelta(days=365.2425 * DEFAULT_HORIZON_YEARS)

    reading = state.get("reading")
    # `assume_promise` is the direct lane, where no rule engine runs. Without it
    # `promise` is always False there and `windows_between` yields nothing, so
    # every timing answer would silently lose its window - the exact failure the
    # docstring above was written about, arriving by a different route.
    #
    # It is not a loosening of the grounding rule, it is a relocation of it: the
    # arithmetic still owns every date, and the prompt hands the model the stages
    # labelled as boundaries rather than as a forecast. Who judges whether the
    # chart promises anything moves from the rule base to the model, which is
    # precisely the change being measured.
    promise = assume_promise or bool(reading and reading.promises(domain))

    window = windows_between(
        chart, chart_state, domain, start, end, promise=promise
    )
    return {"timing": TimingReport(by_system={PRIMARY_SYSTEM: window})}
