"""Assemble the diagnosis, and stamp it with a digest.

One chart in, one `ChartState` out, deterministically. Everything expensive is
already done by the modules beside this one; this is the wiring, plus the two
things that only make sense at whole-chart scope: house-level aggregation, and
the digest.

**The digest is an alarm, not an identifier.** It covers the calculation stack -
positions, ayanamsa, lagna - not just the birth details, because a reading
computed under a different ayanamsa is a different reading. Recomputation that
produces a different digest for the same inputs means the calculation stack
drifted underneath stored answers, which is the highest-severity failure in the
system and the one nobody would otherwise notice.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Optional

from rishivan.chart.ephemeris import Chart
from rishivan.chartstate.dispositor import (
    dispositor_chain,
    dispositor_of,
    nakshatra_lord_chain,
    nakshatra_lord_of,
)
from rishivan.chartstate.functional import functional_natures
from rishivan.chartstate.strength import SYSTEM, strength_of
from rishivan.chartstate.types import (
    ChartState,
    HouseDiagnosis,
    PlanetDiagnosis,
)

FRAMEWORK = "parashari"

#: bhava -> the natural significators for it. From `registry.KARAKAS`, inverted
#: and mapped onto the houses each karaka speaks for.
BHAVA_KARAKAS: dict[int, tuple[str, ...]] = {
    1: ("graha.sun",),
    2: ("graha.jupiter",),
    3: ("graha.mars",),
    4: ("graha.moon",),
    5: ("graha.jupiter",),
    6: ("graha.mars", "graha.saturn"),
    7: ("graha.venus",),
    8: ("graha.saturn",),
    9: ("graha.jupiter", "graha.sun"),
    10: ("graha.saturn", "graha.sun"),
    11: ("graha.jupiter",),
    12: ("graha.saturn",),
}

_BENEFIC_WEIGHT = 0.25
"""How much one benefic influence moves a house's signed score. Four benefic
contacts saturate it, which is roughly the point past which more of them stop
telling you anything new."""


def chart_digest(chart: Chart) -> str:
    """A hash over everything that could change a reading.

    Positions to six decimals, plus the ayanamsa and the lagna. Six decimals is
    well below any meaningful astrological difference and well above float
    noise, so the digest is stable across runs without being blind to real
    drift.
    """
    payload = {
        "ayanamsa": round(chart.ayanamsa, 6),
        "ascendant": round(chart.ascendant_longitude, 6),
        "lagna": chart.lagna_rashi,
        "planets": {
            name: [round(p.longitude, 6), p.rashi, p.house, p.retrograde]
            for name, p in sorted(chart.planets.items())
        },
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _ref(name: str) -> str:
    return f"graha.{name.lower()}"


def build_chart_state(
    chart: Chart,
    *,
    when: Optional[datetime] = None,
    framework: str = FRAMEWORK,
) -> ChartState:
    """The whole diagnosis.

    The Koonji fact set is compiled alongside and read for the handful of
    conditions the fact compiler already owns - combustion, vargottama, varga
    dignity, aspects, dasha activation. Recomputing those here would be a second
    implementation of each, and a second thing to drift; a test asserts the two
    never disagree.
    """
    from rishivan.koonji.facts import compile_facts

    facts = compile_facts(chart, when=when)
    verdicts = functional_natures(chart, framework=framework)
    lords = {house: _ref(lord) for house, lord in chart.house_lords.items()}

    planets = tuple(
        _diagnose_planet(chart, facts, verdicts, name)
        for name in sorted(chart.planets)
    )
    by_graha = {p.graha: p for p in planets}
    houses = tuple(
        _diagnose_house(chart, facts, planets, lords, by_graha, bhava)
        for bhava in range(1, 13)
    )

    return ChartState(
        lagna=f"rashi.{chart.lagna_rashi.lower()}",
        planets=planets,
        houses=houses,
        framework=framework,
        strength_system=SYSTEM,
        chart_digest=chart_digest(chart),
        when=when,
    )


def _diagnose_planet(chart, facts, verdicts, name: str) -> PlanetDiagnosis:
    graha = _ref(name)
    position = chart.planets[name]
    verdict = verdicts[graha]

    combust = facts.has("combust", graha)
    dispositor_walk = dispositor_chain(chart, graha)

    varga_dignity: dict[str, str] = {}
    varga_confirms: dict[str, bool] = {}
    natal_dignity = _dignity_of(facts, graha)
    for atom in facts.atom_names():
        if atom.startswith("varga_dignity("):
            varga, subject, dignity = atom[len("varga_dignity("):-1].split(",")
            if subject == graha:
                code = varga.removeprefix("varga.").upper()
                varga_dignity[code] = dignity
                # "Does the varga corroborate the D1 reading" is the question
                # §7 asks; a raw varga sign does not answer it.
                varga_confirms[code] = _is_favourable(dignity) == _is_favourable(
                    natal_dignity
                )

    return PlanetDiagnosis(
        graha=graha,
        natural_nature=verdict.natural_nature,
        functional_nature=verdict.nature,
        functional_reason=verdict.reason,
        rashi=f"rashi.{position.rashi.lower()}",
        dignity=natal_dignity,
        dispositor=dispositor_of(chart, graha),
        dispositor_chain=dispositor_walk.path,
        dispositor_cycle=dispositor_walk.cycle,
        bhava=position.house,
        lordships=verdict.lordships,
        conjunctions=tuple(sorted(_conjunct_with(facts, graha))),
        aspects_cast=tuple(sorted(_aspects_from(facts, graha))),
        aspects_received=tuple(sorted(_aspects_onto(facts, graha))),
        combust=combust,
        retrograde=position.retrograde,
        vargottama=facts.has("vargottama", graha),
        strength=strength_of(chart, graha, combust=combust),
        varga_dignity=varga_dignity,
        varga_confirms=varga_confirms,
        nakshatra=f"nakshatra.{position.nakshatra.lower().replace(' ', '_')}",
        nakshatra_lord=nakshatra_lord_of(chart, graha),
        nakshatra_lord_chain=nakshatra_lord_chain(chart, graha).path,
    )


def _diagnose_house(chart, facts, planets, lords, by_graha, bhava: int) -> HouseDiagnosis:
    lord = lords[bhava]
    lord_diagnosis = by_graha[lord]
    occupants = tuple(sorted(p.graha for p in planets if p.bhava == bhava))
    target = f"bhava.{bhava:02d}"
    aspects = tuple(sorted(
        p.graha for p in planets if target in p.aspects_cast
    ))

    influence, reasons = _influence(planets, occupants, aspects, by_graha)

    return HouseDiagnosis(
        bhava=bhava,
        rashi=_house_rashi(facts, bhava),
        lord=lord,
        lord_placement=lord_diagnosis.bhava,
        lord_strength=lord_diagnosis.strength,
        lord_dispositor=lord_diagnosis.dispositor,
        occupants=occupants,
        aspects_received=aspects,
        karakas=BHAVA_KARAKAS.get(bhava, ()),
        benefic_influence=influence,
        influence_reason=reasons,
        varga_confirms=dict(lord_diagnosis.varga_confirms),
        dasha_active=_dasha_touches(facts, lord, occupants),
    )


def _influence(planets, occupants, aspects, by_graha) -> tuple[float, tuple[str, ...]]:
    """Signed benefic influence, with the reasons that produced it.

    Zero has to mean "genuinely balanced" rather than "nothing was examined",
    and only the reasons distinguish those. So a house with no contacts still
    gets a sentence.
    """
    score = 0.0
    reasons: list[str] = []

    for graha in occupants:
        nature = by_graha[graha].functional_nature
        if nature == "benefic":
            score += _BENEFIC_WEIGHT
            reasons.append(f"{_bare(graha)} occupies it (functional benefic)")
        elif nature == "malefic":
            score -= _BENEFIC_WEIGHT
            reasons.append(f"{_bare(graha)} occupies it (functional malefic)")

    for graha in aspects:
        nature = by_graha[graha].functional_nature
        if nature == "benefic":
            score += _BENEFIC_WEIGHT / 2
            reasons.append(f"aspected by {_bare(graha)} (functional benefic)")
        elif nature == "malefic":
            score -= _BENEFIC_WEIGHT / 2
            reasons.append(f"aspected by {_bare(graha)} (functional malefic)")

    if not reasons:
        reasons.append("no occupant and no aspect from a functional benefic or malefic")

    return round(max(-1.0, min(1.0, score)), 4), tuple(reasons)


# -- small readers over the fact set ---------------------------------------


def _bare(graha: str) -> str:
    return graha.removeprefix("graha.")


def _dignity_of(facts, graha: str) -> str:
    for atom in facts.atom_names():
        if atom.startswith(f"dignity({graha},"):
            return atom[:-1].split(",")[1]
    return "dignity.neutral"


def _is_favourable(dignity: str) -> bool:
    return dignity in ("dignity.exalted", "dignity.moolatrikona", "dignity.own_sign")


def _conjunct_with(facts, graha: str) -> set[str]:
    out = set()
    for atom in facts.atom_names():
        if atom.startswith("conjunct("):
            a, b = atom[len("conjunct("):-1].split(",")
            if a == graha:
                out.add(b)
            elif b == graha:
                out.add(a)
    return out


def _aspects_from(facts, graha: str) -> set[str]:
    prefix = f"aspects({graha},"
    return {
        atom[:-1].split(",")[1]
        for atom in facts.atom_names() if atom.startswith(prefix)
    }


def _aspects_onto(facts, graha: str) -> set[str]:
    out = set()
    for atom in facts.atom_names():
        if atom.startswith("aspects("):
            subject, target = atom[len("aspects("):-1].split(",")
            if target == graha:
                out.add(subject)
    return out


def _house_rashi(facts, bhava: int) -> str:
    prefix = f"bhava_in_rashi(bhava.{bhava:02d},"
    for atom in facts.atom_names():
        if atom.startswith(prefix):
            return atom[:-1].split(",")[1]
    return ""


def _dasha_touches(facts, lord: str, occupants: tuple[str, ...]) -> bool:
    """Is a running period lord tied to this house?

    Lord or occupant. A period whose lord merely aspects the house is a weaker
    claim and belongs with the timing engine in Phase 3, not here.
    """
    active = {
        atom[len("dasha_active("):-1].split(",")[1]
        for atom in facts.atom_names() if atom.startswith("dasha_active(")
    }
    return bool(active & ({lord} | set(occupants)))
