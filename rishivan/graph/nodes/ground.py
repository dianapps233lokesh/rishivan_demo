"""Ground the retrieval query, and settle who is answering.

Two steps the orchestrator numbers 3 and 3b, kept apart because they answer
different questions: *what should we search for* and *who owns this question*.

Both run after the chart because both can depend on it - the dasha lord that
grounds a remedy query is not knowable until a chart exists.
"""

from __future__ import annotations

from datetime import datetime

from rishivan.council.domains import QueryDomain
from rishivan.graph.state import RishivanState

REMEDY_RISHI = "tejan"
"""The remedies voice. BPHS titles its remedy chapters by planet name
("Saturn", "Mercury"), so a bare "remedies" query misses them entirely - this
Rishi being chosen is the signal to ground the search by the running Mahadasha
lord instead."""


def ground_node(state: RishivanState) -> dict:
    """Port of `council_consult:296-360`.

    The search query is the classifier's, augmented by whatever the chart makes
    knowable. Every augmentation here replaces a keyword guess with a computed
    fact, which is the difference between retrieving about "dasha" and
    retrieving about the planet actually ruling the period.
    """
    from rishivan.chart.dasha import current_periods

    out: dict = {}
    chart = state.get("chart")
    when = state.get("query_time") or datetime.now()
    classification = state["classification"]

    if chart is not None and state["query_domain"] == QueryDomain.NATAL:
        from rishivan.chart.transit import transit_chart

        birth_moon = chart.planets["Moon"]
        today_moon = transit_chart().planets["Moon"]
        current = current_periods(chart, when)
        # Surfaced independently of the voice: an LLM told to "name the
        # nakshatra plainly" paraphrases it into flavour text instead.
        out["nakshatra_now"] = {
            "birth": {"nakshatra": birth_moon.nakshatra, "pada": birth_moon.pada,
                      "rashi": birth_moon.rashi},
            "today": {"nakshatra": today_moon.nakshatra, "pada": today_moon.pada,
                      "rashi": today_moon.rashi},
            "dasha": [
                {"level": level, "lord": p.lord, "ends": p.end.date().isoformat()}
                for level, p in current.items() if p is not None
            ],
        }

    search_query = classification.get("search_query") or state["question"]

    dasha_level = classification.get("dasha_level", "none")
    if dasha_level != "none" and chart is not None:
        periods = current_periods(chart, when)
        if dasha_level == "all":
            chain = " → ".join(
                f"{periods[lvl].lord} {lvl}dasha"
                for lvl in ("maha", "antar", "pratyantar")
                if periods.get(lvl)
            )
            if chain:
                search_query = f"{search_query} — current dasha: {chain}"
        else:
            period = periods.get(dasha_level)
            if period:
                search_query = (
                    f"{search_query} — current {dasha_level}dasha lord: {period.lord}"
                )

    if state.get("primary_rishi") == REMEDY_RISHI and chart is not None:
        maha = current_periods(chart, when).get("maha")
        if maha:
            search_query = (
                f"{search_query} — remedies for {maha.lord}: "
                "mantra, gemstone, donation, ritual"
            )

    out["search_query"] = search_query
    return out


def council_routing_node(state: RishivanState) -> dict:
    """Port of `council_consult:363-390` — step 3b, which Rishis own this.

    This deliberately overrides the voice `intake_node` provisionally picked.
    The routed life domain decides who speaks, not the classifier: the coverage
    gate keys off the domain, so letting the model choose independently allowed
    a persona with no coverage of the subject to answer anyway.
    """
    from rishivan.council.domains import primary_rishi_for
    from rishivan.council.personas import get_persona
    from rishivan.council.routing import merge_supporting, route_question

    routing = merge_supporting(
        route_question(state["question"]),
        state["classification"].get("supporting_rishis") or [],
    )
    rishi = primary_rishi_for(
        routing.primary, classifier_pick=state.get("primary_rishi")
    )
    return {
        "primary_rishi": rishi,
        "rishi_title": get_persona(rishi).title,
        "life_domain": routing.primary,
        "routing": {
            "primary": routing.primary,
            "secondary": list(routing.secondary),
            "application": routing.application,
            "universes": sorted(routing.universes),
            "matched": {k: list(v) for k, v in routing.matched.items()},
            "unsupported": routing.unsupported,
        },
    }
