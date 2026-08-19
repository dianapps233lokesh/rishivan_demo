"""Reduce a computed chart to the flat fact tokens the rule base is written against.

This module is the contract between two halves of the system that were built separately
and do not otherwise speak. The chart engine produces English sentences for page
retrieval ("Ascendant (Lagna) is Aries."); rules are compiled to tokens
(`planet.saturn.house` -> 7). Both are needed, and only the tokens can be matched.

The failure mode this module must not have is silence. `app/astro/vocab.py` warns that a
token spelled differently from the vocabulary means "every affected rule silently matches
nothing" -- no exception, no empty-result signal, just a rule base that appears thin. So
the scope is validated against the emitted list, and a contract test pins the spelling of
every token family against real extracted rules.

Deliberately does NOT emit `dignity_is`, `conjunct` or `aspected_by`. The ephemeris
computes no dignity table, no aspect model and no conjunction orb, and Blueprint §7 is
explicit that the aspect model is school-specific and must never be assumed silently.
Measured on BPHS vol 1: those three types appear in 9 of 376 valid rules (16%), so the
gap is real and bounded. Until it is closed by `relations.py`, those rules are inert --
`satisfies` returns False for a token the chart does not carry, which is the correct
degradation.
"""

from app.astro.vocab import EMITTED_SCOPES
from rishivan.chart.ephemeris import Chart

SIGN_TOKEN_NAME: dict[str, str] = {
    "Aries": "aries",
    "Taurus": "taurus",
    "Gemini": "gemini",
    "Cancer": "cancer",
    "Leo": "leo",
    "Virgo": "virgo",
    "Libra": "libra",
    "Scorpio": "scorpio",
    "Sagittarius": "sagittarius",
    "Capricorn": "capricorn",
    "Aquarius": "aquarius",
    "Pisces": "pisces",
}
"""Ephemeris rashi name -> the name rules use.

The extractor emits `sign: "aries"` because the fact vocabulary is lowercase English, and
`RASHIS` in the ephemeris is title-case. A token holding "Aries" would not match a rule
holding "aries" under an exact comparison, so the normalisation happens here, once,
rather than being left to whichever comparison runs later.
"""

PLANET_TOKEN_NAME: dict[str, str] = {
    "Sun": "sun",
    "Moon": "moon",
    "Mars": "mars",
    "Mercury": "mercury",
    "Jupiter": "jupiter",
    "Venus": "venus",
    "Saturn": "saturn",
    "Rahu": "rahu",
    "Ketu": "ketu",
}
"""`Chart.planets` and `Chart.house_lords` are keyed by display name; tokens use the
vocabulary's names. Named separately from `app.astro.vocab.PLANET_TOKEN_NAME`, which maps
the *books'* two-letter codes (`Sa`) rather than the ephemeris's display names."""


REFERENCE_SCOPES: dict[str, str] = {
    "from_moon.": "Moon",
    "from_sun.": "Sun",
}
"""Scopes that re-count the houses from a planet instead of from the Ascendant.

Not optional decoration: 17 atoms across BPHS vol 1's *parsed* rules use these, because
"the Moon in the 1st, 4th, 7th or 10th from the Sun" is an ordinary classical
construction. `ARGUMENT_SEMANTICS` in the extraction prompt tells the model to express it
as `planet_in_house` with `scope='from_sun.'` rather than as an aspect, so the chart has
to be able to answer it.
"""


def _house_from(reference_rashi_index: int, rashi_index: int) -> int:
    """Which house a placement occupies when counted from another sign.

    Whole-sign: the reference sign is the 1st, the next the 2nd, and so on -- the same
    arithmetic the ephemeris uses to place planets from the lagna.
    """
    return ((rashi_index - reference_rashi_index) % 12) + 1


def chart_tokens(chart: Chart, *, scope: str = "") -> dict[str, int | str]:
    """Every fact token this chart supports, as token -> value.

    `scope` is a prefix from `EMITTED_SCOPES` -- "" for D1 counted from the Ascendant,
    "from_moon." / "from_sun." for a relative frame, "d9." for Navamsa. Callers pass one
    scope per call and merge the results, so a D1 rule can never accidentally read a D9
    placement.
    """
    if scope not in EMITTED_SCOPES:
        raise ValueError(
            f"scope {scope!r} is not emitted by the fact engine; "
            f"emitted scopes are {EMITTED_SCOPES}"
        )

    tokens: dict[str, int | str] = {}
    occupants = dict.fromkeys(range(1, 13), 0)

    # In a relative frame the houses are re-counted from another planet's sign, so every
    # `.house` value below is that offset rather than the position from the lagna.
    reference = chart.planets.get(REFERENCE_SCOPES.get(scope, ""))
    if scope in REFERENCE_SCOPES and reference is None:
        raise ValueError(
            f"scope {scope!r} needs {REFERENCE_SCOPES[scope]}, which this chart lacks"
        )

    def house_of(position) -> int:
        if reference is None:
            return position.house
        return _house_from(reference.rashi_index, position.rashi_index)

    for display_name, position in chart.planets.items():
        planet = PLANET_TOKEN_NAME.get(display_name)
        if planet is None:
            continue
        tokens[f"{scope}planet.{planet}.house"] = house_of(position)
        tokens[f"{scope}planet.{planet}.sign"] = SIGN_TOKEN_NAME.get(
            position.rashi, position.rashi.lower()
        )
        tokens[f"{scope}planet.{planet}.nakshatra"] = position.nakshatra.lower()
        tokens[f"{scope}planet.{planet}.pada"] = position.pada
        occupants[house_of(position)] = occupants.get(house_of(position), 0) + 1

    for house in range(1, 13):
        tokens[f"{scope}house.{house}.occupant_count"] = occupants[house]
        lord_display = chart.house_lords.get(house)
        lord_position = chart.planets.get(lord_display) if lord_display else None
        if lord_position is None:
            continue
        tokens[f"{scope}house.{house}.lord.house"] = house_of(lord_position)
        tokens[f"{scope}house.{house}.lord.sign"] = SIGN_TOKEN_NAME.get(
            lord_position.rashi, lord_position.rashi.lower()
        )
        tokens[f"{scope}house.{house}.lord.name"] = PLANET_TOKEN_NAME.get(
            lord_display, lord_display.lower()
        )

    return tokens


SUPPORTED_SCOPES: tuple[str, ...] = ("", "from_moon.", "from_sun.")
"""The scopes this module can currently produce, in the order they are merged.

`EMITTED_SCOPES` also lists d2/d7/d9/d10/d12/d30, which need divisional charts rather than
a re-count of the same one. They are absent here because no rule needs them yet: of the
688 atoms loaded from BPHS vol 1's parsed rules, 671 are D1-from-lagna, 15 are from_sun
and 2 are from_moon, and not one is a varga. When a book does use them, wire
`rishivan.chart.local_varga` in here rather than teaching callers to merge scopes
themselves.
"""


def all_chart_tokens(chart: Chart) -> dict[str, int | str]:
    """Every token across every supported scope, merged -- what the matcher consumes.

    Callers should prefer this to `chart_tokens`. A caller that merges scopes by hand is
    a caller that can forget one, and a forgotten scope means the affected rules match
    nothing while every other number looks healthy.
    """
    tokens: dict[str, int | str] = {}
    for scope in SUPPORTED_SCOPES:
        tokens.update(chart_tokens(chart, scope=scope))
    return tokens
