"""Chart -> human-readable astrological facts.

Bridge between the deterministic compute layer and the interpret layer: it
states, in plain language, exactly what is in the chart so the LLM interprets
stated facts rather than inventing placements. No interpretation here.
"""

from __future__ import annotations

from datetime import datetime

from rishivan.chart.dasha import current_periods, mahadasha_timeline
from rishivan.chart.ephemeris import Chart

_ORDINAL = {
    1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th",
    7: "7th", 8: "8th", 9: "9th", 10: "10th", 11: "11th", 12: "12th",
}
# what each house broadly signifies (for grounding the interpretation)
_HOUSE_TOPIC = {
    1: "self, body, personality", 2: "wealth, family, speech",
    3: "siblings, courage, communication", 4: "mother, home, property, inner peace",
    5: "children, education, creativity", 6: "disease, enemies, debts, service",
    7: "marriage, spouse, partnerships", 8: "longevity, transformation, sudden events",
    9: "fortune, dharma, father, higher learning", 10: "career, status, public life",
    11: "gains, income, friends", 12: "loss, expenses, foreign lands, liberation",
}
_PLANET_ORDER = [
    "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu",
]


def derive_dasha_facts(chart: Chart, when: datetime | None = None) -> list[str]:
    """Mahadasha timeline + currently running periods, as plain-language facts.

    Split out from derive_facts so the orchestrator can append it even when
    chart_facts came from the real P1 backend's varga-only facts — dasha
    timing is pure local arithmetic on the Moon's birth nakshatra and never
    depends on that backend.
    """
    facts: list[str] = []

    # full mahadasha timeline — birth through end of cycle, so past (and
    # future) periods are grounded facts too, not just whichever is running now
    timeline = mahadasha_timeline(chart)
    if timeline:
        spans = ", ".join(
            f"{p.lord} ({p.start.date()} to {p.end.date()})" for p in timeline
        )
        facts.append("Mahadasha timeline from birth: " + spans + ".")

    # current dasha
    cur = current_periods(chart, when)
    if cur["maha"]:
        parts = [f"{cur['maha'].lord} Mahadasha"]
        if cur["antar"]:
            parts.append(f"{cur['antar'].lord} Antardasha")
        if cur["pratyantar"]:
            parts.append(f"{cur['pratyantar'].lord} Pratyantardasha")
        facts.append("Currently running: " + ", ".join(parts) + ".")

    return facts


def derive_facts(chart: Chart, when: datetime | None = None) -> list[str]:
    """Return an ordered list of plain-language facts describing this chart."""
    facts: list[str] = []

    facts.append(f"Ascendant (Lagna) is {chart.lagna_rashi}.")

    # Restated up front, plainly labelled: otherwise it is buried inside the
    # generic per-planet loop below, and "which nakshatra is running for me"
    # gets no clear answer to point to.
    moon = chart.planets["Moon"]
    facts.append(
        f"Birth nakshatra (Janma Nakshatra): {moon.nakshatra}, pada {moon.pada}."
    )

    # planet placements
    for name in _PLANET_ORDER:
        p = chart.planets[name]
        retro = " (retrograde)" if p.retrograde else ""
        facts.append(
            f"{name} is in {p.rashi} in the {_ORDINAL[p.house]} house "
            f"({p.nakshatra} nakshatra, pada {p.pada}){retro}."
        )

    # house lords and where they sit (core of house judgement)
    for h in range(1, 13):
        lord = chart.house_lords[h]
        lord_pos = chart.planets.get(lord)
        where = f"placed in the {_ORDINAL[lord_pos.house]} house" if lord_pos else "n/a"
        facts.append(
            f"The {_ORDINAL[h]} house ({_HOUSE_TOPIC[h]}) is ruled by {lord}, {where}."
        )

    # conjunctions (two+ planets sharing a house)
    by_house: dict[int, list[str]] = {}
    for name in _PLANET_ORDER:
        by_house.setdefault(chart.planets[name].house, []).append(name)
    for h, names in sorted(by_house.items()):
        if len(names) >= 2:
            facts.append(
                f"Conjunction: {', '.join(names)} are together in the "
                f"{_ORDINAL[h]} house."
            )

    # yogas (deterministic detection)
    try:
        from rishivan.chart.yogas import detect_yogas
        yogas = detect_yogas(chart)
        for y in yogas:
            facts.append(f"Yoga: {y.name} — {y.description}")
    except Exception:  # noqa: BLE001 — yoga detection is supplementary
        pass

    facts.extend(derive_dasha_facts(chart, when))

    # The transiting Moon's nakshatra — the literal answer to "which nakshatra
    # is running for me right now?" Distinct from both the birth nakshatra above
    # (fixed at birth) and the dasha lord above (a planet, not a nakshatra —
    # Vimshottari dasha periods are planetary).
    #
    # Cast for `when`, not for the wall clock. It used to call `transit_chart()`
    # with no argument, so this one line ignored the `when` every other fact in
    # the list honours — a prompt could state the Moon in Aquarius here and in
    # Capricorn two blocks down, both labelled as now. The Moon moves a sign
    # every 2.25 days, which is what made the divergence visible.
    from rishivan.chart.transit import chart_for_moment
    moment = when or datetime.now()
    tm = chart_for_moment(moment).planets["Moon"]
    facts.append(
        f"Transiting Moon on {moment.date()} (not the birth nakshatra): "
        f"{tm.nakshatra}, pada {tm.pada}, Moon in {tm.rashi}."
    )

    return facts


def derive_muhurta_facts(chart: Chart) -> list[str]:
    """Return facts relevant for muhurta / prashna from a moment chart.

    This includes planetary positions (same as natal) plus muhurta-specific
    indicators like the Moon's nakshatra (tithi, tarabala, chandrabala are
    derived from the Moon's position).
    """
    facts: list[str] = []

    facts.append(f"Chart cast for: {chart.birth.place or 'unknown location'}.")
    facts.append(f"Ascendant (Lagna) of the moment is {chart.lagna_rashi}.")

    # Moon position is key for muhurta
    moon = chart.planets["Moon"]
    facts.append(
        f"Moon is in {moon.rashi} ({moon.nakshatra} nakshatra, pada {moon.pada}) "
        f"in the {_ORDINAL[moon.house]} house from lagna."
    )

    # All planet positions
    for name in _PLANET_ORDER:
        p = chart.planets[name]
        retro = " (retrograde)" if p.retrograde else ""
        facts.append(
            f"{name} is in {p.rashi} in the {_ORDINAL[p.house]} house{retro}."
        )

    # House lords (important for prashna — the lagna lord's placement indicates the answer)
    for h in (1, 7, 10):  # Key houses for prashna
        lord = chart.house_lords[h]
        lord_pos = chart.planets.get(lord)
        where = f"placed in the {_ORDINAL[lord_pos.house]} house" if lord_pos else "n/a"
        facts.append(
            f"The {_ORDINAL[h]} house lord is {lord}, {where}."
        )

    # Conjunctions
    by_house: dict[int, list[str]] = {}
    for name in _PLANET_ORDER:
        by_house.setdefault(chart.planets[name].house, []).append(name)
    for h, names in sorted(by_house.items()):
        if len(names) >= 2:
            facts.append(
                f"Conjunction at moment: {', '.join(names)} in the {_ORDINAL[h]} house."
            )

    # Yogas (apply to query-moment chart too)
    try:
        from rishivan.chart.yogas import detect_yogas
        yogas = detect_yogas(chart)
        for y in yogas:
            facts.append(f"Yoga at query moment: {y.name} — {y.description}")
    except Exception:  # noqa: BLE001
        pass

    return facts
