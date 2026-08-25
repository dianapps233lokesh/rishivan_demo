"""Cast the chart, compute the daily windows, render whichever table was asked.

A birth chart and a moment chart come from different inputs via different
functions, so they are two nodes rather than one node with a domain check -
`route_after_intake` already made that decision, and re-deciding it inside a
node is exactly the branching this refactor removes.

Rendering is four nodes for the same reason. Everything here is pure local
arithmetic: Swiss Ephemeris plus the vendored varga engine, zero network calls.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from rishivan.graph.state import RishivanState

DEFAULT_LAT = 28.6139
DEFAULT_LON = 77.2090
DEFAULT_PLACE = "New Delhi"

NUMEROLOGY_NEEDS_DOB = (
    "Numerology needs a date of birth, and none was given for this reading."
)
"""Verbatim from `council_consult:261`. Deliberately not the generic message -
the user gave a question this feature cannot answer at all, rather than one it
failed to compute."""


def chart_natal_node(state: RishivanState) -> dict:
    """Port of `council_consult:156-194`.

    The relevant-varga loop matters more than it looks. Every divisional chart
    governs a specific life area, and grounding a marriage reading in D9 without
    putting D9 facts in front of the model means grounding it in nothing.
    """
    from rishivan.chart.ephemeris import compute_chart, summarize
    from rishivan.chart.facts import derive_facts
    from rishivan.chart.local_varga import varga_facts, varga_table_markdown

    chart = compute_chart(state["birth_data"])
    chart_facts = derive_facts(chart)
    tables: dict[str, str] = {}

    covered = {"D1"}
    for code in state["classification"].get("relevant_vargas", []):
        if code in covered:
            continue
        covered.add(code)
        extra = varga_facts(chart, code)
        if not extra:
            continue
        chart_facts = chart_facts + extra
        # The "Computed Chart" panel only ever showed D1, so an answer grounded
        # in another varga had no visible chart to check it against.
        table = varga_table_markdown(chart, code)
        if table:
            tables[code] = table

    return {
        "chart": chart,
        "chart_summary": summarize(chart),
        "chart_facts": chart_facts,
        "relevant_chart_tables": tables,
    }


def chart_moment_node(state: RishivanState) -> dict:
    """Muhurta and Prashna. Port of `council_consult:214-236`."""
    from rishivan.chart.ephemeris import summarize
    from rishivan.chart.facts import derive_muhurta_facts
    from rishivan.chart.panchang import relative_day_offset
    from rishivan.chart.transit import chart_for_moment
    from rishivan.council.domains import QueryDomain

    now = state.get("query_time") or datetime.now()
    if state["query_domain"] == QueryDomain.MUHURTA:
        # Without an explicit target, honour the day the question names -
        # "is tomorrow good?" must not be answered from today's sky.
        moment = state.get("target_time") or (
            now + timedelta(days=relative_day_offset(state["question"]))
        )
    else:
        moment = now

    chart = chart_for_moment(
        moment,
        lat=state.get("lat") or DEFAULT_LAT,
        lon=state.get("lon") or DEFAULT_LON,
        place=state.get("place") or "Query location",
        tz_offset=state.get("tz_offset", 5.5),
    )
    return {
        "chart": chart,
        "chart_summary": summarize(chart),
        "chart_facts": derive_muhurta_facts(chart),
    }


def panchang_node(state: RishivanState) -> dict:
    """Port of `council_consult:199-212` and `239-241`.

    Sunrise/sunset arithmetic, computed rather than left to the model - which
    otherwise deflects ("check a local almanac") or invents clock times. The
    windows lead the fact list because they are ground truth.
    """
    from rishivan.chart.panchang import compute_panchang, relative_day_offset

    base = (state.get("query_time") or datetime.now()).date()
    target = base + timedelta(days=relative_day_offset(state["question"]))
    panchang = compute_panchang(
        target,
        lat=state["lat"] if state.get("lat") is not None else DEFAULT_LAT,
        lon=state["lon"] if state.get("lon") is not None else DEFAULT_LON,
        tz_offset=state.get("tz_offset", 5.5),
        place=state.get("place") or DEFAULT_PLACE,
    )
    summary = panchang.summary()
    return {
        "panchang": summary,
        "chart_facts": summary.splitlines() + (state.get("chart_facts") or []),
    }


# ==========================================================================
# Renderers
# ==========================================================================


def _rendered(table: str | None, subject: str) -> dict:
    """One shape for every renderer.

    A renderer that cannot produce its table returns the reason, naming what it
    failed at. Never fall back to a different chart than the one asked for - an
    honest "can't compute this" beats a silently wrong table, and a generic
    "can't compute this" beats neither.
    """
    if table:
        return {"chart_table": table, "chart_table_error": None}
    return {
        "chart_table": None,
        "chart_table_error": (
            f"I can't compute {subject} in this environment right now."
        ),
    }


def render_varga_node(state: RishivanState) -> dict:
    from rishivan.chart.local_varga import varga_table_markdown

    code = state["classification"].get("varga_code", "D1")
    chart = state.get("chart")
    table = varga_table_markdown(chart, code) if chart is not None else None
    return _rendered(table, f"{code} chart")


def render_dasha_node(state: RishivanState) -> dict:
    from rishivan.chart.local_dasha import dasha_table_markdown

    chart = state.get("chart")
    when = state.get("query_time") or datetime.now()
    table = dasha_table_markdown(chart, when) if chart is not None else None
    return _rendered(table, "vimshottari dasha")


def render_ashtakavarga_node(state: RishivanState) -> dict:
    from rishivan.chart.local_ashtakavarga import ashtakavarga_table_markdown

    chart = state.get("chart")
    table = ashtakavarga_table_markdown(chart) if chart is not None else None
    return _rendered(table, "ashtakavarga")


def render_numerology_node(state: RishivanState) -> dict:
    from rishivan.chart.local_numerology import numerology_table_markdown

    birth = state.get("birth_data")
    if birth is None:
        return {"chart_table": None, "chart_table_error": NUMEROLOGY_NEEDS_DOB}
    return _rendered(
        numerology_table_markdown(birth, state.get("chart")), "numerology"
    )
