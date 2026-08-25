"""Planetary strength — partial, and honest about being partial.

Full six-fold Shadbala is Sthana, Dig, Kaala, Chesta, Naisargika and Drik bala,
each with its own sub-components and its own disagreements between authorities.
Three of those need ephemeris work this codebase does not do yet (Chesta wants
true planetary velocity relative to the Sun; Kaala wants a dozen day/night and
paksha terms). Implementing three of six and calling the result "Shadbala" would
be worse than useless.

So: Sthana + Dig + an affliction adjustment, normalised to 0..1, banded, and
every reading carries `is_estimated=True`. `StrengthReading.claimable_value`
returns None while that flag is set, so the scalar cannot reach a user-visible
claim by accident. The band survives estimation; the number does not.

**Why the flag matters more than the arithmetic.** Everything downstream weights
by strength - the evidence graph, Phase 4's per-domain hierarchies, and any
Rishi that says "weak". A number that is confidently wrong propagates into all
of them and is invisible at every step. A band that is roughly right does not.
"""

from __future__ import annotations

from typing import Optional

from rishivan.chart.ephemeris import Chart
from rishivan.chartstate.types import Band, StrengthReading

SYSTEM = "parashari.partial.v1"
"""Named in every reading. "The selected strength system" is a configuration
decision the blueprint asks to be stated, and `partial` is in the name so that
nothing downstream can mistake this for Shadbala."""

#: Sthana bala, as a fraction. The classical ordering, not the classical
#: rupas — those need the full six-fold framework to mean anything.
DIGNITY_SCORE: dict[str, float] = {
    "exalted": 1.00,
    "moolatrikona": 0.85,
    "own_sign": 0.75,
    "friendly": 0.60,
    "neutral": 0.45,
    "inimical": 0.25,
    "debilitated": 0.05,
}

DIG_BALA_HOUSE: dict[str, int] = {
    "sun": 10, "mars": 10,
    "jupiter": 1, "mercury": 1,
    "moon": 4, "venus": 4,
    "saturn": 7,
    # The nodes have no classical dig bala. Given the Sun's direction so the
    # component is defined rather than absent; it contributes little either way.
    "rahu": 10, "ketu": 10,
}
"""The house where each planet is directionally strongest. Sun and Mars in the
10th, Jupiter and Mercury in the 1st, Moon and Venus in the 4th, Saturn in the
7th."""

DUSTHANAS = (6, 8, 12)

COMBUST_PENALTY = 0.30
RETROGRADE_BONUS = 0.05
"""Retrogression is contested — some authorities count it as strength, some as
disturbance. Small and positive here, which is the majority reading, and small
enough that the disagreement does not decide a band on its own."""

DUSTHANA_PENALTY = 0.15

_WEIGHTS = {"sthana": 0.6, "dig": 0.4}
"""Sthana dominates. With only two real components the split is a judgement, not
a derivation, and it is written here rather than buried in the arithmetic."""

_BAND_EDGES = (
    (0.20, Band.VERY_WEAK),
    (0.40, Band.WEAK),
    (0.60, Band.MODERATE),
    (0.80, Band.STRONG),
)


def band_for(value: float) -> Band:
    """Monotonic by construction: a higher score never lands in a weaker band."""
    for edge, band in _BAND_EDGES:
        if value < edge:
            return band
    return Band.VERY_STRONG


def _bare(graha: str) -> str:
    return graha.removeprefix("graha.").lower()


def _position(chart: Chart, graha: str):
    bare = _bare(graha)
    for name, p in chart.planets.items():
        if name.lower() == bare:
            return p
    raise KeyError(f"{graha!r} is not in this chart")


def _sthana(graha: str, rashi: str) -> float:
    from rishivan.chart.relations import dignity_of

    return DIGNITY_SCORE[dignity_of(_bare(graha), rashi) or "neutral"]


def _dig(graha: str, house: int) -> float:
    """Full at the planet's own direction, zero at the opposite house, linear
    between.

    A cliff would make a planet one house off its direction score the same as
    one six houses off, which is not what the doctrine describes and would put
    two very different charts in the same band.
    """
    best = DIG_BALA_HOUSE.get(_bare(graha), 10)
    distance = abs(house - best) % 12
    if distance > 6:
        distance = 12 - distance
    return 1.0 - distance / 6.0


def strength_of(
    chart: Chart,
    graha: str,
    *,
    combust: Optional[bool] = None,
) -> StrengthReading:
    """One graha's strength, itemised.

    `combust` is passed in rather than computed here. Combustion is an
    elongation calculation the fact compiler already does, and a second
    implementation is a second thing to drift.
    """
    position = _position(chart, graha)

    sthana = _sthana(graha, position.rashi)
    dig = _dig(graha, position.house)
    value = _WEIGHTS["sthana"] * sthana + _WEIGHTS["dig"] * dig

    components = {"sthana": sthana, "dig": dig}

    if combust:
        value -= COMBUST_PENALTY
        components["combust_penalty"] = -COMBUST_PENALTY
    if position.retrograde:
        value += RETROGRADE_BONUS
        components["retrograde"] = RETROGRADE_BONUS
    if position.house in DUSTHANAS:
        value -= DUSTHANA_PENALTY
        components["dusthana_penalty"] = -DUSTHANA_PENALTY

    value = max(0.0, min(1.0, value))
    return StrengthReading(
        value=round(value, 4),
        band=band_for(value),
        system=SYSTEM,
        is_estimated=True,
        components={k: round(v, 4) for k, v in components.items()},
    )
