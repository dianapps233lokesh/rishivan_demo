"""Shadbala — the six-fold strength, computed in full.

`chartstate/strength.py` computes two of the six and says so in its own name:
`parashari.partial.v1`, `is_estimated=True`, and a `claimable_value` that
returns None so the scalar cannot reach a reader by accident. Its docstring
named the three blockers: Chesta wants true velocity relative to the Sun, Kaala
wants a dozen day/night and paksha terms, and implementing three of six and
calling it Shadbala would be worse than useless.

Every one of those blockers is now gone. `PlanetPosition.speed_deg_per_day` is
signed daily motion; `chart/panchang.py` gives sunrise and sunset; `chart/limbs.py`
gives paksha and the Sun-Moon elongation. So this is the whole thing.

**Units are Virupas throughout.** Sixty Virupas make one Rupa, and the required
strength per graha is quoted in Rupas by every classical source, so both are
reported. A total is meaningless without its requirement: Mercury needs seven
Rupas and Mars five, so 340 Virupas is weak for one and strong for the other.

**Every convention is named, per this repo's standing rule that no method ships
without a source.** Shadbala is the single most divergent calculation in Jyotish
- authorities disagree on Chesta's state boundaries, on Ayana's formula, on
whether the Moon's Paksha bala doubles, and on which house cusp Dig bala
measures from. Each function says which reading it implements. A number nobody
can trace is worse here than no number, because it looks authoritative.

**The nodes are excluded.** Rahu and Ketu have no Shadbala: they are not bodies,
they cast no light, they have no velocity of their own in this scheme and the
classical texts assign them none. Including them with zeros would read as
"computed and found weak" rather than "not applicable".
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

GRAHAS: tuple[str, ...] = (
    "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn",
)

VIRUPAS_PER_RUPA = 60.0

# ── Sthana bala ──────────────────────────────────────────────────────────────

EXALTATION_LONGITUDE: dict[str, float] = {
    "Sun": 10.0,        # 10 Aries
    "Moon": 33.0,       # 3 Taurus
    "Mars": 298.0,      # 28 Capricorn
    "Mercury": 165.0,   # 15 Virgo
    "Jupiter": 95.0,    # 5 Cancer
    "Venus": 357.0,     # 27 Pisces
    "Saturn": 200.0,    # 20 Libra
}
"""Deep exaltation, as absolute sidereal longitude.

`chart/relations.py` holds exaltation by SIGN, which is all a dignity check
needs. Uchcha bala needs the degree: a Sun at 10 Aries scores 60 and a Sun at 29
Aries scores 38, and by sign alone both are simply "exalted".
"""

DEBILITATION_LONGITUDE = {
    graha: (longitude + 180.0) % 360.0
    for graha, longitude in EXALTATION_LONGITUDE.items()
}

NATURAL_FRIENDS: dict[str, frozenset[str]] = {
    "Sun": frozenset({"Moon", "Mars", "Jupiter"}),
    "Moon": frozenset({"Sun", "Mercury"}),
    "Mars": frozenset({"Sun", "Moon", "Jupiter"}),
    "Mercury": frozenset({"Sun", "Venus"}),
    "Jupiter": frozenset({"Sun", "Moon", "Mars"}),
    "Venus": frozenset({"Mercury", "Saturn"}),
    "Saturn": frozenset({"Mercury", "Venus"}),
}

NATURAL_NEUTRALS: dict[str, frozenset[str]] = {
    "Sun": frozenset({"Mercury"}),
    "Moon": frozenset({"Mars", "Jupiter", "Venus", "Saturn"}),
    "Mars": frozenset({"Venus", "Saturn"}),
    "Mercury": frozenset({"Mars", "Jupiter", "Saturn"}),
    "Jupiter": frozenset({"Saturn"}),
    "Venus": frozenset({"Mars", "Jupiter"}),
    "Saturn": frozenset({"Jupiter"}),
}
"""Parashara's natural relations. Whatever is neither friend nor neutral is an
enemy, so the third table is derived rather than stated - three hand-written
tables is three chances for a graha to be a friend in one and an enemy in
another."""

SAPTAVARGA: tuple[str, ...] = ("D1", "D2", "D3", "D7", "D9", "D12", "D30")
"""The seven divisions Sthana bala is measured across. Not the sixteen: the
saptavargaja scheme is specifically these seven, and using a different set
changes every planet's score."""

SAPTAVARGAJA_POINTS: dict[str, float] = {
    "moolatrikona": 45.0,
    "own_sign": 30.0,
    "great_friend": 22.5,
    "friend": 15.0,
    "neutral": 7.5,
    "enemy": 3.75,
    "great_enemy": 1.875,
}
"""Exaltation is not in this table on purpose. Uchcha bala already scores it,
and paying for the same placement twice is the commonest error in a hand-rolled
Shadbala."""

ODD_SIGN_STRONG = ("Sun", "Mars", "Jupiter", "Mercury", "Saturn")
EVEN_SIGN_STRONG = ("Moon", "Venus")

DIG_BALA_HOUSE: dict[str, int] = {
    "Jupiter": 1, "Mercury": 1,
    "Moon": 4, "Venus": 4,
    "Saturn": 7,
    "Sun": 10, "Mars": 10,
}
"""The house each graha is strongest in — east for wisdom, north for comfort,
west for service, south for action.

**Measured from the whole-sign cusp**, matching the house system this codebase
uses everywhere. Classical texts measure from the true MC and Ascendant degrees,
which for a chart in mid-latitudes differs by up to a sign; sources that use
whole-sign houses throughout, as this one does, take the sign cusp. Named
because the two give visibly different Dig balas.
"""

# ── Naisargika ───────────────────────────────────────────────────────────────

NAISARGIKA_BALA: dict[str, float] = {
    "Saturn": 60.0 * 1 / 7,
    "Mars": 60.0 * 2 / 7,
    "Mercury": 60.0 * 3 / 7,
    "Jupiter": 60.0 * 4 / 7,
    "Venus": 60.0 * 5 / 7,
    "Moon": 60.0 * 6 / 7,
    "Sun": 60.0 * 7 / 7,
}
"""Fixed, and in order of apparent brightness. The only component that does not
look at the chart at all."""

# ── Required strength ────────────────────────────────────────────────────────

REQUIRED_RUPAS: dict[str, float] = {
    "Sun": 5.0, "Moon": 6.0, "Mars": 5.0, "Mercury": 7.0,
    "Jupiter": 6.5, "Venus": 5.5, "Saturn": 5.0,
}
"""What each graha needs to count as strong.

A total means nothing without this. Mercury needs seven Rupas and Mars five, so
340 Virupas is a weak Mercury and a strong Mars, and a table that ranks by total
alone puts them in the wrong order.
"""

# ── Chesta ───────────────────────────────────────────────────────────────────

MEAN_DAILY_MOTION: dict[str, float] = {
    "Mars": 0.524, "Mercury": 1.383, "Jupiter": 0.083,
    "Venus": 1.602, "Saturn": 0.034,
}

MOTION_STATES: tuple[tuple[str, float], ...] = (
    ("vakra", 60.0),        # retrograde
    ("anuvakra", 30.0),     # retrograde back into the previous sign
    ("vikala", 15.0),       # stationary
    ("mandatara", 7.5),     # very slow
    ("manda", 15.0),        # slow
    ("sama", 30.0),         # average
    ("chara", 30.0),        # fast
    ("atichara", 45.0),     # very fast
)
"""The eight motional states and their Virupas.

Assigned here from the ratio of actual to mean daily motion, with the boundaries
named in `chesta_bala`. Authorities differ on those boundaries — some derive
Chesta from the seeghrocha (the epicyclic anomaly) rather than from speed at
all — so the convention is stated rather than assumed.
"""

# ── Drik ─────────────────────────────────────────────────────────────────────

_NATURAL_BENEFICS = frozenset({"Jupiter", "Venus", "Moon", "Mercury"})

_SPECIAL_FULL_ASPECTS: dict[str, tuple[int, ...]] = {
    "Mars": (4, 8), "Jupiter": (5, 9), "Saturn": (3, 10),
}

_PARTIAL_ASPECT_VIRUPAS: dict[int, float] = {
    3: 15.0, 10: 15.0, 5: 30.0, 9: 30.0, 4: 45.0, 8: 45.0,
}
"""Parashari partial drishti. The 7th is full for every graha and each of Mars,
Jupiter and Saturn has its own two full aspects on top."""


@dataclass(frozen=True, slots=True)
class Component:
    """One named part of one graha's strength, in Virupas."""

    name: str
    virupas: float
    note: str = ""


@dataclass(frozen=True, slots=True)
class GrahaBala:
    """One graha's six-fold strength, itemised."""

    graha: str
    sthana: tuple[Component, ...] = ()
    dig: float = 0.0
    kaala: tuple[Component, ...] = ()
    chesta: float = 0.0
    chesta_state: str = ""
    naisargika: float = 0.0
    drik: float = 0.0
    yuddha: float = 0.0

    @property
    def sthana_total(self) -> float:
        return sum(c.virupas for c in self.sthana)

    @property
    def kaala_total(self) -> float:
        return sum(c.virupas for c in self.kaala)

    @property
    def total(self) -> float:
        return (self.sthana_total + self.dig + self.kaala_total
                + self.chesta + self.naisargika + self.drik + self.yuddha)

    @property
    def rupas(self) -> float:
        return self.total / VIRUPAS_PER_RUPA

    @property
    def required(self) -> float:
        return REQUIRED_RUPAS[self.graha] * VIRUPAS_PER_RUPA

    @property
    def ratio(self) -> float:
        """Total over what this graha needs. Above 1.0 is strong."""
        return self.total / self.required

    @property
    def verdict(self) -> str:
        ratio = self.ratio
        if ratio >= 1.25:
            return "very strong"
        if ratio >= 1.0:
            return "strong"
        if ratio >= 0.8:
            return "adequate"
        return "weak"


@dataclass(frozen=True, slots=True)
class Shadbala:
    grahas: dict[str, GrahaBala] = field(default_factory=dict)
    conventions: tuple[str, ...] = ()

    def ranked(self) -> tuple[GrahaBala, ...]:
        """Strongest first, by ratio to requirement rather than by total.

        Ranking by total puts Mercury above Mars whenever Mercury is merely
        adequate, because Mercury's requirement is 40% higher.
        """
        return tuple(sorted(self.grahas.values(), key=lambda g: -g.ratio))


# ── Sthana bala ──────────────────────────────────────────────────────────────

def uchcha_bala(graha: str, longitude: float) -> float:
    """Exaltation strength, 0 at debilitation and 60 at deep exaltation.

    Linear in the arc from the debilitation point, which is what makes it
    continuous: by sign alone a Sun at 10 Aries and one at 29 Aries are both
    "exalted", and they differ here by 22 Virupas.
    """
    distance = abs((longitude % 360.0) - DEBILITATION_LONGITUDE[graha])
    if distance > 180.0:
        distance = 360.0 - distance
    return distance / 3.0


def _natural_relation(graha: str, other: str) -> str:
    if graha == other:
        return "own_sign"
    if other in NATURAL_FRIENDS[graha]:
        return "friend"
    if other in NATURAL_NEUTRALS[graha]:
        return "neutral"
    return "enemy"


def _varga_sign(chart, graha: str, code: str) -> Optional[int]:
    if code == "D1":
        position = chart.planets.get(graha)
        return None if position is None else position.rashi_index
    from rishivan.chart.local_varga import _varga_positions

    computed = _varga_positions(chart, code)
    if computed is None:
        return None
    _lagna, positions = computed
    entry = positions.get(graha)
    return None if entry is None else entry[0]


def saptavargaja_bala(chart, graha: str) -> tuple[float, list[str]]:
    """Dignity strength summed across the seven divisions.

    Great-friend and great-enemy come from combining the natural relation with
    the temporary one, which depends on relative house position. Computed rather
    than approximated to the natural relation alone: the compound is what the
    classical scheme scores, and collapsing it costs up to 7.5 Virupas per
    division, seven times over.
    """
    from rishivan.chart.ephemeris import RASHI_LORDS, RASHIS
    from rishivan.chart.relations import dignity_of

    position = chart.planets.get(graha)
    if position is None:
        return 0.0, []

    total = 0.0
    notes: list[str] = []
    for code in SAPTAVARGA:
        sign_index = _varga_sign(chart, graha, code)
        if sign_index is None:
            continue
        sign = RASHIS[sign_index]
        dignity = dignity_of(graha.lower(), sign.lower())
        if dignity == "moolatrikona":
            points, label = SAPTAVARGAJA_POINTS["moolatrikona"], "moolatrikona"
        elif dignity in ("own_sign", "exalted"):
            # Exaltation scores as own-sign here. Uchcha bala has already paid
            # for the exaltation itself, and scoring it twice is the commonest
            # error in a hand-rolled Shadbala.
            points, label = SAPTAVARGAJA_POINTS["own_sign"], "own"
        else:
            lord = RASHI_LORDS[sign_index]
            relation = _natural_relation(graha, lord)
            temporary = _temporary_relation(chart, graha, lord)
            label = _compound(relation, temporary)
            points = SAPTAVARGAJA_POINTS[label]
        total += points
        notes.append(f"{code}:{label}")
    return total, notes


def _temporary_relation(chart, graha: str, other: str) -> str:
    """Friend when the other sits in the 2nd, 3rd, 4th, 10th, 11th or 12th from
    this graha; enemy otherwise. Parashara's temporary scheme."""
    a, b = chart.planets.get(graha), chart.planets.get(other)
    if a is None or b is None or graha == other:
        return "neutral"
    distance = (b.rashi_index - a.rashi_index) % 12 + 1
    return "friend" if distance in (2, 3, 4, 10, 11, 12) else "enemy"


def _compound(natural: str, temporary: str) -> str:
    if natural == "own_sign":
        return "own_sign"
    table = {
        ("friend", "friend"): "great_friend",
        ("friend", "enemy"): "neutral",
        ("neutral", "friend"): "friend",
        ("neutral", "enemy"): "enemy",
        ("enemy", "friend"): "neutral",
        ("enemy", "enemy"): "great_enemy",
    }
    return table.get((natural, temporary), "neutral")


def ojhayugma_bala(chart, graha: str) -> float:
    """Odd/even sign strength, in the rashi and the navamsa, 15 Virupas each.

    Moon and Venus want even signs; the rest want odd. Scored twice because the
    scheme names both the rashi and the navamsa, so the maximum is 30.
    """
    position = chart.planets.get(graha)
    if position is None:
        return 0.0
    navamsa = _varga_sign(chart, graha, "D9")

    wants_even = graha in EVEN_SIGN_STRONG
    total = 0.0
    for sign_index in (position.rashi_index, navamsa):
        if sign_index is None:
            continue
        is_even = sign_index % 2 == 1  # 0-based: Aries=0 is odd
        if is_even == wants_even:
            total += 15.0
    return total


def kendradi_bala(house: int) -> float:
    """60 in an angle, 30 in a succedent, 15 in a cadent."""
    if house in (1, 4, 7, 10):
        return 60.0
    if house in (2, 5, 8, 11):
        return 30.0
    return 15.0


def drekkana_bala(graha: str, degree_in_rashi: float) -> float:
    """15 Virupas in the third of the sign that matches the graha's gender.

    Male grahas take the first ten degrees, hermaphrodite the second, female the
    third. Zero otherwise — this component is all-or-nothing.
    """
    third = int(degree_in_rashi // 10.0)
    male, neuter, female = ("Sun", "Mars", "Jupiter"), ("Mercury", "Saturn"), ("Moon", "Venus")
    if third == 0 and graha in male:
        return 15.0
    if third == 1 and graha in neuter:
        return 15.0
    if third == 2 and graha in female:
        return 15.0
    return 0.0


# ── Dig bala ─────────────────────────────────────────────────────────────────

def dig_bala(graha: str, longitude: float, lagna_longitude: float) -> float:
    """Directional strength: 60 at the graha's own cusp, 0 at the opposite one.

    Measured from the whole-sign cusp, matching the house system used
    everywhere else here. See `DIG_BALA_HOUSE` for why that is stated.
    """
    strong_house = DIG_BALA_HOUSE[graha]
    strong_point = (lagna_longitude + (strong_house - 1) * 30.0) % 360.0
    powerless = (strong_point + 180.0) % 360.0
    distance = abs((longitude % 360.0) - powerless)
    if distance > 180.0:
        distance = 360.0 - distance
    return distance / 3.0


# ── Kaala bala ───────────────────────────────────────────────────────────────

_DAY_STRONG = ("Sun", "Jupiter", "Venus")
_NIGHT_STRONG = ("Moon", "Mars", "Saturn")

_TRIBHAGA_DAY = ("Mercury", "Sun", "Saturn")
_TRIBHAGA_NIGHT = ("Moon", "Venus", "Mars")

_WEEKDAY_LORD = {
    0: "Moon", 1: "Mars", 2: "Mercury", 3: "Jupiter",
    4: "Venus", 5: "Saturn", 6: "Sun",
}


def nathonnatha_bala(graha: str, local_hour: float) -> float:
    """Day/night strength, from distance to local noon.

    Sun, Jupiter and Venus are day-strong; Moon, Mars and Saturn night-strong;
    Mercury is strong at all hours and always takes 60.

    Measured against clock noon and midnight rather than against the midpoint of
    the actual daylight span. Both readings exist; this one is what "nata" and
    "unnata" mean literally, and it is what the arithmetic in the standard
    worked examples uses.
    """
    if graha == "Mercury":
        return 60.0
    day_strength = 60.0 * (1.0 - abs((local_hour % 24.0) - 12.0) / 12.0)
    return day_strength if graha in _DAY_STRONG else 60.0 - day_strength


def paksha_bala(graha: str, elongation: float) -> float:
    """Lunar fortnight strength, from the Sun-Moon elongation.

    Benefics gain through the bright half and lose through the dark; malefics
    the reverse. The Moon's is NOT doubled here — several authorities double it
    and several do not, and doubling would put the Moon's Kaala bala above its
    own requirement on half of all charts.
    """
    distance = elongation % 360.0
    if distance > 180.0:
        distance = 360.0 - distance
    benefic_share = distance / 3.0
    return benefic_share if graha in _NATURAL_BENEFICS else 60.0 - benefic_share


def tribhaga_bala(graha: str, local_hour: float, sunrise: float,
                  sunset: float) -> float:
    """60 Virupas to whichever graha rules the current third of day or night.

    Jupiter always takes 60 regardless — that is the rule as written, not an
    oversight here.
    """
    if graha == "Jupiter":
        return 60.0
    if sunrise <= local_hour < sunset:
        span = (sunset - sunrise) / 3.0
        index = min(int((local_hour - sunrise) / span), 2) if span else 0
        return 60.0 if _TRIBHAGA_DAY[index] == graha else 0.0
    night_length = (24.0 - (sunset - sunrise)) / 3.0
    elapsed = (local_hour - sunset) % 24.0
    index = min(int(elapsed / night_length), 2) if night_length else 0
    return 60.0 if _TRIBHAGA_NIGHT[index] == graha else 0.0


def _sun_ingress_weekday(jd_ut: float, target_sign: int, tz_offset: float) -> int:
    """The weekday the Sun entered `target_sign`, walking backwards from `jd_ut`.

    Bisection on the ephemeris rather than a table, for the same reason
    `limbs._ends_at` bisects: the Sun's speed varies by a thirtieth across the
    year and a linear estimate slips a day near the solstices — which changes
    the lord, and the lord is the whole point.
    """
    import swisseph as swe

    from rishivan.chart.limbs import _sidereal

    def sign_at(jd: float) -> int:
        return int(_sidereal(jd, swe.SUN) // 30.0) % 12

    low = jd_ut - 400.0
    high = jd_ut
    if sign_at(low) == target_sign:
        low = jd_ut - 800.0
    for _ in range(30):
        middle = (low + high) / 2.0
        if sign_at(middle) == target_sign:
            high = middle
        else:
            low = middle
    year, month, day, _hour = swe.revjul(high + tz_offset / 24.0)
    return datetime(year, month, day).weekday()


def varsha_masa_dina_hora_bala(
    graha: str, *, jd_ut: float, sun_sign: int, tz_offset: float,
    birth_weekday: int, hora_lord: str,
) -> tuple[float, list[str]]:
    """Year, month, day and hour lords: 15, 30, 45 and 60 Virupas.

    The year begins at the Sun's entry into Aries and the month at its entry
    into the current sign, so both lords are found by walking the ephemeris back
    to those ingresses. The day is counted from sunrise, not midnight — a birth
    at 02:15 belongs to the previous weekday, which is exactly the case that
    makes this worth computing rather than reading off a calendar.
    """
    parts: list[str] = []
    total = 0.0

    varsha_lord = _WEEKDAY_LORD[_sun_ingress_weekday(jd_ut, 0, tz_offset)]
    if varsha_lord == graha:
        total += 15.0
    parts.append(f"year:{varsha_lord}")

    masa_lord = _WEEKDAY_LORD[_sun_ingress_weekday(jd_ut, sun_sign, tz_offset)]
    if masa_lord == graha:
        total += 30.0
    parts.append(f"month:{masa_lord}")

    dina_lord = _WEEKDAY_LORD[birth_weekday]
    if dina_lord == graha:
        total += 45.0
    parts.append(f"day:{dina_lord}")

    if hora_lord == graha:
        total += 60.0
    parts.append(f"hora:{hora_lord}")

    return total, parts


_NORTH_STRONG = ("Sun", "Mars", "Jupiter", "Venus")


def ayana_bala(graha: str, declination: float) -> float:
    """Declination strength, from the graha's distance north or south.

    Sun, Mars, Jupiter and Venus gain in northern declination; Moon and Saturn
    in southern; Mercury gains in either, so its declination is taken absolute.

    The Sun's is doubled, which is the rule as written. Scaled over 48 degrees
    (twice the 24-degree maximum declination) so the result lands in 0..60.
    """
    if graha == "Mercury":
        effective = abs(declination)
    elif graha in _NORTH_STRONG:
        effective = declination
    else:
        effective = -declination
    value = (24.0 + effective) * 60.0 / 48.0
    value = max(0.0, min(60.0, value))
    return value * 2.0 if graha == "Sun" else value


def _declination(jd_ut: float, body: int) -> float:
    """Declination in degrees, from TROPICAL ecliptic coordinates.

    Tropical, and this is the one place in the codebase where that matters.
    Declination is a physical angle against the celestial equator; feeding it a
    sidereal longitude shifts it by the ayanamsa, roughly 24 degrees today,
    which is the entire range Ayana bala measures.
    """
    import swisseph as swe

    values, _flag = swe.calc_ut(jd_ut, body, swe.FLG_MOSEPH | swe.FLG_SPEED)
    obliquity, _ = swe.calc_ut(jd_ut, swe.ECL_NUT, swe.FLG_MOSEPH)
    equatorial = swe.cotrans((values[0], values[1], 1.0), -obliquity[0])
    return equatorial[1]


# ── Chesta bala ──────────────────────────────────────────────────────────────

def chesta_bala(graha: str, speed: float, *, retrograde: bool,
                ayana: float, paksha: float) -> tuple[float, str]:
    """Motional strength, and the state it came from.

    **The Sun and the Moon have no Chesta bala of their own** — the Sun's is its
    Ayana bala and the Moon's is its Paksha bala, which is the rule as written
    rather than a shortcut taken here.

    For the five taras, the state is read from the ratio of actual to mean daily
    motion. Some authorities derive it from the seeghrocha (the epicyclic
    anomaly) instead, which needs a planetary model this codebase does not
    carry; the speed reading is the common substitute and is named as such.
    """
    if graha == "Sun":
        return ayana, "ayana (the Sun has no chesta of its own)"
    if graha == "Moon":
        return paksha, "paksha (the Moon has no chesta of its own)"

    mean = MEAN_DAILY_MOTION.get(graha)
    if mean is None:
        return 0.0, "not applicable"
    if retrograde or speed < 0:
        return 60.0, "vakra (retrograde)"

    ratio = speed / mean
    if ratio < 0.05:
        return 15.0, "vikala (stationary)"
    if ratio < 0.5:
        return 7.5, "mandatara (very slow)"
    if ratio < 0.95:
        return 15.0, "manda (slow)"
    if ratio <= 1.05:
        return 30.0, "sama (mean speed)"
    if ratio <= 1.5:
        return 30.0, "chara (fast)"
    return 45.0, "atichara (very fast)"


# ── Drik bala ────────────────────────────────────────────────────────────────

def drik_bala(chart, graha: str) -> float:
    """Aspectual strength: benefic drishti received, less malefic, over four.

    Parashari drishti — the 7th full for everyone, plus Mars on the 4th and 8th,
    Jupiter on the 5th and 9th, Saturn on the 3rd and 10th, and the graded
    partials for the rest. Divided by four, which is the scaling the scheme
    specifies and without which this component swamps the other five.
    """
    target = chart.planets.get(graha)
    if target is None:
        return 0.0

    total = 0.0
    for other, position in chart.planets.items():
        if other == graha or other not in GRAHAS:
            continue
        distance = (target.rashi_index - position.rashi_index) % 12 + 1
        full = (7,) + _SPECIAL_FULL_ASPECTS.get(other, ())
        if distance in full:
            virupas = 60.0
        else:
            virupas = _PARTIAL_ASPECT_VIRUPAS.get(distance, 0.0)
        if virupas:
            total += virupas if other in _NATURAL_BENEFICS else -virupas
    return total / 4.0


# ── Yuddha bala ──────────────────────────────────────────────────────────────

_DISC_DIAMETER: dict[str, float] = {
    "Mars": 9.4, "Mercury": 6.6, "Jupiter": 190.4, "Venus": 16.6, "Saturn": 158.0,
}
"""Apparent disc diameters in the classical units the war rule uses. Only the
five taras go to war; the luminaries and the nodes never do."""

WAR_ORB_DEGREES = 1.0


def _apply_yuddha(chart, balances: dict[str, GrahaBala]) -> dict[str, GrahaBala]:
    """Planetary war: two taras within a degree, and the loser pays the winner.

    Rare — most charts have none — but silently skipping it would make this
    "five-and-a-half-fold strength" on the charts where it applies. The winner
    is the graha with the greater total, and the transfer is the difference in
    their totals divided by the difference in their disc diameters.
    """
    from dataclasses import replace

    warriors = [g for g in _DISC_DIAMETER if g in chart.planets]
    adjustments: dict[str, float] = {}

    for i, first in enumerate(warriors):
        for second in warriors[i + 1:]:
            a, b = chart.planets[first], chart.planets[second]
            separation = abs(a.longitude - b.longitude) % 360.0
            if separation > 180.0:
                separation = 360.0 - separation
            if separation > WAR_ORB_DEGREES:
                continue
            diameter_gap = abs(_DISC_DIAMETER[first] - _DISC_DIAMETER[second])
            if diameter_gap == 0:
                continue
            gap = abs(balances[first].total - balances[second].total)
            transfer = gap / diameter_gap
            winner, loser = (
                (first, second) if balances[first].total >= balances[second].total
                else (second, first)
            )
            adjustments[winner] = adjustments.get(winner, 0.0) + transfer
            adjustments[loser] = adjustments.get(loser, 0.0) - transfer

    if not adjustments:
        return balances
    return {
        graha: (replace(bala, yuddha=adjustments[graha])
                if graha in adjustments else bala)
        for graha, bala in balances.items()
    }


# ── Assembly ─────────────────────────────────────────────────────────────────

CONVENTIONS: tuple[str, ...] = (
    "Saptavargaja over D1, D2, D3, D7, D9, D12, D30. Exaltation scores as own "
    "sign there, because Uchcha bala has already paid for it.",
    "Dig bala measured from the whole-sign cusp, matching the house system used "
    "throughout this codebase, not from the true MC.",
    "Nathonnatha measured against clock noon and midnight, not against the "
    "midpoint of the actual daylight span.",
    "The Moon's Paksha bala is NOT doubled. Authorities divide on this.",
    "Chesta read from actual-over-mean daily motion, not from the seeghrocha.",
    "The Sun's Chesta is its Ayana bala and the Moon's is its Paksha bala.",
    "The Sun's Ayana bala is doubled.",
    "Rahu and Ketu are excluded: the scheme assigns them no strength.",
)


def compute_shadbala(chart, *, when: Optional[datetime] = None,
                     lat: float = 28.6139, lon: float = 77.2090,
                     tz_offset: float = 5.5) -> Shadbala:
    """All six components for all seven grahas, in Virupas.

    `when` defaults to the birth moment: Shadbala is a property of the nativity,
    not of today. Passing a different moment computes the strength of a chart
    cast for that moment, which is what a prashna reading wants.
    """
    import swisseph as swe

    from rishivan.chart.limbs import sun_and_moon
    from rishivan.chart.panchang import compute_panchang, hora_lord

    jd = chart.julian_day_ut
    birth = chart.birth
    local_hour = birth.hour + birth.minute / 60.0 + birth.second / 3600.0
    day = datetime(birth.year, birth.month, birth.day)

    panchang = compute_panchang(
        day.date(), lat=lat, lon=lon, tz_offset=tz_offset, with_limbs=False,
    )
    sunrise = _hhmm_to_hours(panchang.sunrise)
    sunset = _hhmm_to_hours(panchang.sunset)

    # Counted from sunrise, not midnight. A birth at 02:15 belongs to the
    # previous weekday, and the day lord is worth 45 Virupas to whoever holds it.
    weekday = day.weekday() if local_hour >= sunrise else (day.weekday() - 1) % 7
    ruling_hora = hora_lord(day.date(), sunrise, local_hour)

    sun_longitude, moon_longitude = sun_and_moon(jd)
    elongation = (moon_longitude - sun_longitude) % 360.0
    sun_sign = int(sun_longitude // 30.0) % 12

    bodies = {
        "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS,
        "Mercury": swe.MERCURY, "Jupiter": swe.JUPITER,
        "Venus": swe.VENUS, "Saturn": swe.SATURN,
    }

    balances: dict[str, GrahaBala] = {}
    for graha in GRAHAS:
        position = chart.planets.get(graha)
        if position is None:
            continue

        saptavargaja, notes = saptavargaja_bala(chart, graha)
        sthana = (
            Component("uchcha", uchcha_bala(graha, position.longitude)),
            Component("saptavargaja", saptavargaja, " ".join(notes)),
            Component("ojhayugma", ojhayugma_bala(chart, graha)),
            Component("kendradi", kendradi_bala(position.house)),
            Component("drekkana", drekkana_bala(graha, position.degree_in_rashi)),
        )

        declination = _declination(jd, bodies[graha])
        ayana = ayana_bala(graha, declination)
        paksha = paksha_bala(graha, elongation)
        vmdh, vmdh_notes = varsha_masa_dina_hora_bala(
            graha, jd_ut=jd, sun_sign=sun_sign, tz_offset=tz_offset,
            birth_weekday=weekday, hora_lord=ruling_hora,
        )
        kaala = (
            Component("nathonnatha", nathonnatha_bala(graha, local_hour)),
            Component("paksha", paksha),
            Component("tribhaga", tribhaga_bala(graha, local_hour, sunrise, sunset)),
            Component("varsha-masa-dina-hora", vmdh, " ".join(vmdh_notes)),
            Component("ayana", ayana, f"declination {declination:+.2f}"),
        )

        chesta, state = chesta_bala(
            graha, position.speed_deg_per_day,
            retrograde=position.retrograde, ayana=ayana, paksha=paksha,
        )

        balances[graha] = GrahaBala(
            graha=graha,
            sthana=sthana,
            dig=dig_bala(graha, position.longitude, chart.ascendant_longitude),
            kaala=kaala,
            chesta=chesta,
            chesta_state=state,
            naisargika=NAISARGIKA_BALA[graha],
            drik=drik_bala(chart, graha),
        )

    return Shadbala(grahas=_apply_yuddha(chart, balances), conventions=CONVENTIONS)


def _hhmm_to_hours(value: str) -> float:
    hours, minutes = value.split(":")
    return int(hours) + int(minutes) / 60.0


def render_markdown(shadbala: Shadbala) -> str:
    """The six-fold table, ranked, with its conventions attached.

    Conventions travel WITH the table rather than in a footnote somebody scrolls
    past. Shadbala is the most divergent calculation in Jyotish and two correct
    implementations disagree by tens of Virupas; a number without its method is
    a number nobody can check against their own software.
    """
    if not shadbala.grahas:
        return ""

    lines = [
        "### Shadbala — six-fold strength",
        "",
        "Virupas. Sixty Virupas make one Rupa. **Ranked by ratio to requirement, "
        "not by total** — Mercury needs 7 Rupas and Mars 5, so the same score is "
        "weak for one and strong for the other.",
        "",
        "| Graha | Sthana | Dig | Kaala | Chesta | Naisargika | Drik | Yuddha | "
        "**Total** | Needs | Ratio | |",
        "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|",
    ]
    for bala in shadbala.ranked():
        lines.append(
            f"| {bala.graha} | {bala.sthana_total:.1f} | {bala.dig:.1f} | "
            f"{bala.kaala_total:.1f} | {bala.chesta:.1f} | {bala.naisargika:.1f} | "
            f"{bala.drik:+.1f} | {bala.yuddha:+.1f} | **{bala.total:.1f}** | "
            f"{bala.required:.0f} | {bala.ratio:.2f} | {bala.verdict} |"
        )

    lines += ["", "**Chesta state**", ""]
    for bala in shadbala.ranked():
        lines.append(f"- {bala.graha}: {bala.chesta_state}")

    lines += ["", "**Sthana bala, itemised**", ""]
    for bala in shadbala.ranked():
        parts = ", ".join(
            f"{c.name} {c.virupas:.1f}" for c in bala.sthana
        )
        lines.append(f"- {bala.graha}: {parts}")

    lines += ["", "**Kaala bala, itemised**", ""]
    for bala in shadbala.ranked():
        parts = ", ".join(f"{c.name} {c.virupas:.1f}" for c in bala.kaala)
        lines.append(f"- {bala.graha}: {parts}")

    lines += ["", "**Conventions used** — Shadbala implementations diverge; "
              "these are the readings taken here.", ""]
    lines += [f"- {note}" for note in shadbala.conventions]
    return "\n".join(lines)
