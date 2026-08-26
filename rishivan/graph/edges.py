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
    """warmth · chart_natal · chart_moment · panchang · retrieve

    Small talk is checked first and deliberately: "hi" from a user who has not
    entered birth details is a greeting, and asking them for a birth time is a
    worse answer than saying hello back.

    There is no "ask for birth data" destination, and that is not an oversight.
    `intake_node` rewrites a natal question with no chart into PRASHNA - the
    moment of asking becomes the chart - so by the time this runs the domain is
    already one that can be charted. Adding a prompt-for-input branch here would
    be new behaviour, and Phase 1 changes control flow only.
    """
    from rishivan.chart.panchang import mentions_panchang

    if state["classification"].get("is_smalltalk_or_gibberish"):
        return "warmth"

    domain = state["query_domain"]
    if domain == QueryDomain.NATAL:
        # A birth chart and a moment chart are built from different inputs by
        # different functions. That is a branch, and a branch belongs here
        # rather than as an `if` inside one overloaded node.
        return "chart_natal"
    if domain in _CHARTED_WITHOUT_BIRTH:
        return "chart_moment"
    # A general question can still ask about today's panchang, and the
    # orchestrator computes it whether or not a chart was cast.
    return "panchang" if mentions_panchang(state["question"]) else "retrieve"


def route_after_chart(state: RishivanState) -> str:
    """chart_render · panchang · retrieve

    A display request ("show me my D9") short-circuits to a deterministic table
    and never reaches retrieval or a model.
    """
    from rishivan.chart.panchang import mentions_panchang

    if state.get("chart") is not None and state["classification"].get("intent") == "chart":
        return "chart_render"
    return "panchang" if mentions_panchang(state["question"]) else "retrieve"


def route_chart_kind(state: RishivanState) -> str:
    """render_numerology · render_ashtakavarga · render_dasha · render_varga

    Four destinations, one per kind. Numerology's missing-birth-date case is
    handled inside its renderer rather than as a fifth destination, because the
    orchestrator treats it as a table it could not compute - a
    `chart_table_error` - and not as a request for more input.
    """
    kind = state["classification"].get("chart_type", "")
    if kind == "numerology":
        return "render_numerology"
    if kind == "ashtakavarga":
        return "render_ashtakavarga"
    if kind == "dasha":
        return "render_dasha"
    return "render_varga"


def route_after_retrieval(state: RishivanState) -> str:
    """answer · insufficient

    Both halves, matching `council_consult:534`: pages OR rules is enough to
    answer from. Gating on pages alone would discard a reading the rule base
    grounded on its own, which is the half most likely to be right.

    Nothing at all is not an empty answer - it is the answer. Generating prose
    over no retrieved material is the exact failure the grounding discipline
    exists to prevent, and it is invisible in the output.
    """
    if state.get("sources") or state.get("matched_rules"):
        return "answer"
    return "insufficient"


def route_rishis(state: RishivanState):
    """The council fan-out, or straight past it.

    Delegates to `council/rishis/roster.py`, which owns the evidence gate. This
    router exists so the graph's edge table has one place to look for every
    branch, and so `route_rishis` is testable from the same table as the other
    four.

    Returns `"synthesis"` rather than an empty list when nobody qualifies: a
    conditional edge that returns no destinations strands the run, and a
    council of nobody is still a fact the synthesis has to report.
    """
    from rishivan.council.rishis.roster import route_rishis as _route

    sends = _route(state)
    return sends or "synthesis"


def route_after_sakshi(state: RishivanState) -> str:
    """re_examine · synthesis — bounded at one revision.

    Delegates to `council/rishis/sakshi.py`, where the bound lives beside the
    audit that triggers it.
    """
    from rishivan.council.rishis.sakshi import route_after_sakshi as _route

    return _route(state)


def route_re_examination(state: RishivanState):
    """Back to the Rishis a finding named, or on to synthesis.

    Returning `"synthesis"` on an empty list matters more than it looks: an
    audit whose findings all name Rishis that were never invited would
    otherwise strand the run between the auditor and the answer.
    """
    from rishivan.council.rishis.roster import route_re_examination as _route

    return _route(state) or "synthesis"
