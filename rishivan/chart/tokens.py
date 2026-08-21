"""Reduce a computed chart to the flat fact tokens the rule base is written against.

The contract between two halves built separately: the chart engine produces English
sentences for page retrieval, rules are compiled to tokens (`planet.saturn.house` -> 7).
Both are needed and only the tokens can be matched.

The failure mode to avoid is silence. A token spelled differently from the vocabulary
means every affected rule matches nothing, with no exception raised — just a rule base
that looks thin. So the scope is checked against the emitted list, and a contract test
pins every token family against real extracted rules.

Dignity, conjunction and aspect come from `relations.py`, which states the Parashari
model it implements rather than assuming one universal aspect model (Blueprint §7).
"""

from datetime import datetime

from rishivan.astro.vocab import EMITTED_SCOPES
from rishivan.chart.dasha import current_periods
from rishivan.chart.ephemeris import RASHI_LORDS, Chart

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
"""Ephemeris rashi name -> the name rules use. The vocabulary is lowercase and the
ephemeris title-case, so "Aries" would not match "aries" under an exact comparison.
Normalised here, once, rather than in whichever comparison runs later."""

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
"""Display name -> token name. Distinct from `astro.vocab.PLANET_TOKEN_NAME`, which
maps the *books'* two-letter codes (`Sa`) rather than ephemeris display names."""


REFERENCE_SCOPES: dict[str, str] = {
    "from_moon.": "Moon",
    "from_sun.": "Sun",
}
"""Scopes that re-count the houses from a planet rather than the Ascendant.

17 atoms in BPHS vol 1's parsed rules use these — "the Moon in the 1st, 4th, 7th or
10th from the Sun" is an ordinary classical construction, and the extraction prompt
expresses it as `planet_in_house` with `scope='from_sun.'` rather than as an aspect.
"""


def _house_from(reference_rashi_index: int, rashi_index: int) -> int:
    """Which house a placement occupies counted from another sign. Whole-sign: the
    reference sign is the 1st, the next the 2nd, as the ephemeris does from the lagna."""
    return ((rashi_index - reference_rashi_index) % 12) + 1


def chart_tokens(chart: Chart, *, scope: str = "") -> dict[str, int | str]:
    """Every fact token this chart supports, as token -> value.

    `scope` is a prefix from `EMITTED_SCOPES`: "" for D1 from the Ascendant,
    "from_moon." / "from_sun." for a relative frame, "d9." for Navamsa. One scope per
    call, so a D1 rule can never accidentally read a D9 placement.
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
        # In a relative frame the HOUSES move too, so the Nth lord is the lord of the
        # Nth sign from the reference planet -- not the lagna's Nth lord re-counted.
        # Sagittarius lagna, Moon in Aquarius: `from_moon.house.1.lord` is Saturn (lord
        # of Aquarius), not Jupiter. The wrong answer here tests a rule against a
        # different planet entirely and matches or misses for no visible reason.
        if reference is None:
            lord_display = chart.house_lords.get(house)
        else:
            sign_index = (reference.rashi_index + house - 1) % 12
            lord_display = RASHI_LORDS[sign_index]
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

    # Imported here rather than at module scope: `relations` imports this module's name
    # tables, so a top-level import would be circular.
    from rishivan.chart.relations import relation_tokens

    tokens.update(relation_tokens(chart, scope=scope))
    return tokens


SUPPORTED_SCOPES: tuple[str, ...] = ("", "from_moon.", "from_sun.")
"""The scopes this module can produce, in merge order.

`EMITTED_SCOPES` also lists d2/d7/d9/d10/d12/d30, which need divisional charts rather
than a re-count of one. No rule needs them yet — of BPHS vol 1's 688 parsed atoms, 671
are D1-from-lagna, 15 from_sun, 2 from_moon, none a varga. When a book does, wire
`chart.local_varga` in here rather than teaching callers to merge scopes.
"""


def dasha_tokens(
    chart: Chart, when: datetime | None = None
) -> dict[str, int | str]:
    """The running Vimshottari periods as fact tokens: `dasha.{level}.lord` -> planet.

    The one token family that is a function of a MOMENT as well as a chart, which is why
    it is not part of `chart_tokens` and why `all_chart_tokens` takes `when`. Everything
    else here is fixed at birth.

    `astro/vocab.py` has declared `dasha_of -> dasha.{level}.lord` since the vocabulary
    was frozen, but nothing emitted it, so 636 activation atoms across the corpus
    addressed a token the chart never produced -- and a rule whose activation cannot be
    evaluated is indistinguishable from a rule with no timing at all. Blueprint §8
    rule 2 is exactly that distinction.

    A level absent from the result is a level with no period running (before birth, or
    past the end of the cycle). Absence is deliberate: `match.engine` treats an unknown
    token as unmatched, so a rule degrades to "cannot say" rather than to a false
    activation.
    """
    tokens: dict[str, int | str] = {}
    for level, period in current_periods(chart, when).items():
        if period is None:
            continue
        # `Period.lord` is the ephemeris display name ("Saturn"); the rule vocabulary is
        # lowercase. An exact comparison across that difference matches nothing.
        tokens[f"dasha.{level}.lord"] = PLANET_TOKEN_NAME.get(
            period.lord, period.lord.lower()
        )
    return tokens


def all_chart_tokens(
    chart: Chart, when: datetime | None = None
) -> dict[str, int | str]:
    """Every token across every supported scope, merged — what the matcher consumes.

    Prefer this to `chart_tokens`: a caller merging scopes by hand can forget one, and a
    forgotten scope means those rules match nothing while every number looks healthy.

    `when` dates the timing tokens and defaults to now. It is optional so that existing
    natal callers keep working, but note that a caller who wants the periods running at
    a moment other than now must say so -- silently defaulting is right for a reading
    cast today and wrong for a backtest.
    """
    tokens: dict[str, int | str] = {}
    for scope in SUPPORTED_SCOPES:
        tokens.update(chart_tokens(chart, scope=scope))
    tokens.update(dasha_tokens(chart, when))
    return tokens
