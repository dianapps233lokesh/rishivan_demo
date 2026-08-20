"""Dignity, conjunction and aspect tokens — the Parashari model, named explicitly.

Blueprint §7 requires a stated choice, never an assumed universal aspect model, so all
three are spelled out rather than left implicit in the arithmetic:

* **Dignity** — the classical exaltation / debilitation / moolatrikona / own-sign table.
  Spellings match `DIGNITY_SYNONYMS` in the validator, the words rules were grounded on.
* **Conjunction** — whole-sign: two planets in one rashi. Not an orb; BPHS is a
  whole-sign text throughout and an orb model answers differently.
* **Aspect** — Parashari drishti: every planet aspects the 7th from itself, plus Mars
  the 4th and 8th, Jupiter the 5th and 9th, Saturn the 3rd and 10th.

These three families carry 16% of BPHS vol 1's valid rules, inert until this existed.
"""

from rishivan.chart.ephemeris import Chart
from rishivan.chart.tokens import PLANET_TOKEN_NAME, SIGN_TOKEN_NAME

EXALTATION: dict[str, str] = {
    "sun": "aries",
    "moon": "taurus",
    "mars": "capricorn",
    "mercury": "virgo",
    "jupiter": "cancer",
    "venus": "pisces",
    "saturn": "libra",
    "rahu": "taurus",
    "ketu": "scorpio",
}

DEBILITATION: dict[str, str] = {
    "sun": "libra",
    "moon": "scorpio",
    "mars": "cancer",
    "mercury": "pisces",
    "jupiter": "capricorn",
    "venus": "virgo",
    "saturn": "aries",
    "rahu": "scorpio",
    "ketu": "taurus",
}

OWN_SIGNS: dict[str, tuple[str, ...]] = {
    "sun": ("leo",),
    "moon": ("cancer",),
    "mars": ("aries", "scorpio"),
    "mercury": ("gemini", "virgo"),
    "jupiter": ("sagittarius", "pisces"),
    "venus": ("taurus", "libra"),
    "saturn": ("capricorn", "aquarius"),
}
"""The nodes own no sign in the Parashari scheme, so Rahu and Ketu are absent."""

MOOLATRIKONA: dict[str, str] = {
    "sun": "leo",
    "moon": "taurus",
    "mars": "aries",
    "mercury": "virgo",
    "jupiter": "sagittarius",
    "venus": "libra",
    "saturn": "aquarius",
}

SPECIAL_ASPECTS: dict[str, tuple[int, ...]] = {
    "mars": (4, 7, 8),
    "jupiter": (5, 7, 9),
    "saturn": (3, 7, 10),
}
"""Houses counted from the planet itself. Everything else aspects only the 7th."""

DEFAULT_ASPECTS: tuple[int, ...] = (7,)


def dignity_of(planet: str, sign: str) -> str | None:
    """The planet's dignity in this sign, or None if neutral.

    Most specific label wins — exaltation, debilitation, moolatrikona, own sign — because
    "exalted" means exalted, not merely well placed.
    """
    planet, sign = planet.lower(), sign.lower()
    if EXALTATION.get(planet) == sign:
        return "exalted"
    if DEBILITATION.get(planet) == sign:
        return "debilitated"
    if MOOLATRIKONA.get(planet) == sign:
        return "moolatrikona"
    if sign in OWN_SIGNS.get(planet, ()):
        return "own_sign"
    return None


def relation_tokens(chart: Chart, *, scope: str = "") -> dict[str, int | str | bool]:
    """Dignity, conjunction and aspect tokens for this chart.

    Aspects are keyed by the house aspected (`planet.mars.aspects.8`), matching what
    `aspected_by{planet: mars, target: 8}` compiles to. A verse naming a planet as the
    target resolves through that planet's house, so both forms are emitted.
    """
    positions = {
        PLANET_TOKEN_NAME[name]: position
        for name, position in chart.planets.items()
        if name in PLANET_TOKEN_NAME
    }
    tokens: dict[str, int | str | bool] = {}

    for planet, position in positions.items():
        sign = SIGN_TOKEN_NAME.get(position.rashi, position.rashi.lower())
        dignity = dignity_of(planet, sign)
        if dignity is not None:
            tokens[f"{scope}planet.{planet}.dignity"] = dignity

        aspected_houses = SPECIAL_ASPECTS.get(planet, DEFAULT_ASPECTS)
        for offset in aspected_houses:
            house = ((position.house - 1 + offset - 1) % 12) + 1
            tokens[f"{scope}planet.{planet}.aspects.{house}"] = True
            # And the planets sitting in that house, so "aspected by Jupiter" resolves
            # whether the verse names a house or a planet as the target.
            for other, other_position in positions.items():
                if other != planet and other_position.house == house:
                    tokens[f"{scope}planet.{planet}.aspects.{other}"] = True

    for planet, position in positions.items():
        for other, other_position in positions.items():
            if planet != other and position.house == other_position.house:
                tokens[f"{scope}planet.{planet}.conjunct.{other}"] = True

    return tokens
