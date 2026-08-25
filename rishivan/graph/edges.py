"""Every conditional the orchestrator used to take, as a pure function.

A router reads state and returns the name of the next node. It does not write,
does not compute, and does not call anything expensive. That restriction is what
makes the table in `tests/graph/test_edges.py` possible, and that table is the
first time these branches have been tested at all.
"""

from __future__ import annotations

from rishivan.council.domains import QueryDomain
from rishivan.graph.state import RishivanState

#: Domains that cast a chart from something other than a birth moment, and so
#: proceed without birth data. Muhurta uses a target time, Prashna the moment
#: the question was asked.
_CHARTED_WITHOUT_BIRTH = (QueryDomain.MUHURTA, QueryDomain.PRASHNA)


def route_after_intake(state: RishivanState) -> str:
    """warmth · need_birth_data · chart · retrieve

    Small talk is checked first and deliberately: "hi" from a user who has not
    entered birth details is a greeting, and asking them for a birth time is a
    worse answer than saying hello back.
    """
    if state["classification"].get("is_smalltalk_or_gibberish"):
        return "warmth"

    domain = state["query_domain"]
    if domain == QueryDomain.NATAL:
        return "chart" if state.get("birth_data") is not None else "need_birth_data"
    if domain in _CHARTED_WITHOUT_BIRTH:
        return "chart"
    return "retrieve"


def route_after_chart(state: RishivanState) -> str:
    """chart_render · panchang · retrieve"""
    from rishivan.chart.panchang import mentions_panchang

    if state.get("chart") is None:
        return "retrieve"
    if state["classification"].get("intent") == "chart":
        return "chart_render"
    if mentions_panchang(state["question"]):
        return "panchang"
    return "retrieve"


def route_chart_kind(state: RishivanState) -> str:
    """render_numerology · render_ashtakavarga · render_dasha · render_varga ·
    need_birth_data

    Numerology is the one kind that needs a date rather than a moment, so it is
    the one kind that can bounce back to asking for input.
    """
    kind = state["classification"].get("chart_type", "")
    if kind == "numerology":
        return (
            "render_numerology"
            if state.get("birth_data") is not None
            else "need_birth_data"
        )
    if kind == "ashtakavarga":
        return "render_ashtakavarga"
    if kind == "dasha":
        return "render_dasha"
    return "render_varga"


def route_after_retrieval(state: RishivanState) -> str:
    """answer · insufficient

    An empty source list is not an empty answer - it is the answer. Generating
    prose over no retrieved material is the exact failure the grounding
    discipline exists to prevent, and it is invisible in the output.
    """
    return "answer" if state.get("sources") else "insufficient"
