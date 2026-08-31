"""The five limbs of the panchang — pancha-anga, computed.

`chart/panchang.py` computes the daily WINDOWS: sunrise, sunset, Rahu Kaal,
Yamaganda, Gulika, the hora. Those are arithmetic on sunrise and they were
always right. What it never computed is the panchang itself — the five limbs the
word names:

    vara       the weekday          -- was already there
    tithi      the lunar day        -- NOT COMPUTED until now
    nakshatra  the Moon's asterism  -- reached the prompt only obliquely
    yoga       sun+moon, 27 parts   -- NOT COMPUTED until now
    karana     half a tithi         -- NOT COMPUTED until now

A reading that stated a tithi therefore produced one from the model's training
data. That is the single place in this system where an answer could still come
from a knowledge cutoff rather than from an ephemeris, and it is the one place a
reader would never catch it — a wrong Rahu Kaal is checkable against any almanac
and a wrong tithi reads exactly like a right one.

**The classical rules are pure functions of one or two longitudes**, kept apart
from the ephemeris lookups below them so they can be tested with exact inputs.
A test that needs Swiss Ephemeris to check a modulo is testing the wrong thing.

**One arithmetic trap, and it is easy to get backwards.** Tithi and karana are
DIFFERENCES of two longitudes, so the ayanamsa cancels and tropical or sidereal
give the same answer. A yoga is their SUM, so the ayanamsa does not cancel —
computed tropically it is off by twice the ayanamsa, roughly 48 degrees today,
which is nearly four whole yogas. Everything here is sidereal (Lahiri), matching
the rest of the chart engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from rishivan.chart.ephemeris import NAKSHATRAS

TITHI_BASE = (
    "Pratipada", "Dvitiya", "Tritiya", "Chaturthi", "Panchami", "Shashthi",
    "Saptami", "Ashtami", "Navami", "Dashami", "Ekadashi", "Dvadashi",
    "Trayodashi", "Chaturdashi",
)

TITHI_NAMES: tuple[str, ...] = tuple(
    [f"Shukla {name}" for name in TITHI_BASE] + ["Purnima"]
    + [f"Krishna {name}" for name in TITHI_BASE] + ["Amavasya"]
)

RIKTA = (4, 9, 14)
"""The 4th, 9th and 14th of either fortnight — avoided for beginnings.

Flagged rather than judged. Whether a rikta tithi rules out a particular
undertaking is a reading's call; this module's job is to say which one it is.
"""

YOGA_NAMES: tuple[str, ...] = (
    "Vishkambha", "Priti", "Ayushman", "Saubhagya", "Shobhana", "Atiganda",
    "Sukarma", "Dhriti", "Shula", "Ganda", "Vriddhi", "Dhruva", "Vyaghata",
    "Harshana", "Vajra", "Siddhi", "Vyatipata", "Variyana", "Parigha", "Shiva",
    "Siddha", "Sadhya", "Shubha", "Shukla", "Brahma", "Indra", "Vaidhriti",
)

INAUSPICIOUS_YOGAS = ("Vyatipata", "Vaidhriti")
"""The two a muhurta selection actually rejects on."""

KARANA_MOVABLE: tuple[str, ...] = (
    "Bava", "Balava", "Kaulava", "Taitila", "Gara", "Vanija", "Vishti",
)
"""Seven, cycling eight times through the 56 middle half-tithis."""

KARANA_FIXED: tuple[str, ...] = (
    "Kimstughna", "Shakuni", "Chatushpada", "Naga",
)
"""Four, and each occurs once a lunar month. Kimstughna opens it; the other
three close it."""

VISHTI = "Vishti"
"""Bhadra. The one karana classical muhurta rejects outright."""

_TITHI_ARC = 12.0
_KARANA_ARC = 6.0
_TWENTY_SEVENTH = 360.0 / 27.0
_PADA_ARC = _TWENTY_SEVENTH / 4.0


@dataclass(frozen=True, slots=True)
class Tithi:
    index: int
    """0-29 from the new moon."""

    name: str
    paksha: str
    number: int
    """1-15 within the fortnight, which is how a panchang prints it."""

    rikta: bool = False


@dataclass(frozen=True, slots=True)
class Yoga:
    index: int
    name: str
    inauspicious: bool = False


@dataclass(frozen=True, slots=True)
class Karana:
    index: int
    """0-59 half-tithis from the new moon."""

    name: str
    fixed: bool = False
    inauspicious: bool = False


@dataclass(frozen=True, slots=True)
class Nakshatra:
    index: int
    name: str
    pada: int


def tithi_of(elongation: float) -> Tithi:
    """The lunar day from the Moon's elongation from the Sun.

    Twelve degrees each, thirty to the lunar month. A difference of longitudes,
    so the ayanamsa cancels and this is correct on tropical or sidereal input.
    """
    index = int((elongation % 360.0) // _TITHI_ARC)
    number = index % 15 + 1
    return Tithi(
        index=index,
        name=TITHI_NAMES[index],
        paksha="Shukla" if index < 15 else "Krishna",
        number=number,
        rikta=number in RIKTA,
    )


def yoga_of(sum_of_longitudes: float) -> Yoga:
    """The yoga from the SUM of the sidereal Sun and Moon longitudes.

    Sidereal input is not optional here — see the module docstring. A yoga
    computed from tropical longitudes is about four yogas out.
    """
    index = int((sum_of_longitudes % 360.0) // _TWENTY_SEVENTH)
    name = YOGA_NAMES[index]
    return Yoga(index=index, name=name, inauspicious=name in INAUSPICIOUS_YOGAS)


def karana_of(elongation: float) -> Karana:
    """The karana — half a tithi, six degrees.

    Sixty half-tithis to the month, arranged as four fixed and seven movable:
    Kimstughna takes the first, the last three take Shakuni, Chatushpada and
    Naga, and the seven movable fill the 56 between by cycling eight times.
    """
    index = int((elongation % 360.0) // _KARANA_ARC)
    if index == 0:
        name, fixed = KARANA_FIXED[0], True
    elif index >= 57:
        name, fixed = KARANA_FIXED[index - 56], True
    else:
        name, fixed = KARANA_MOVABLE[(index - 1) % 7], False
    return Karana(index=index, name=name, fixed=fixed,
                  inauspicious=name == VISHTI)


def nakshatra_of(longitude: float) -> Nakshatra:
    """The Moon's asterism and pada, from its sidereal longitude."""
    value = longitude % 360.0
    index = int(value // _TWENTY_SEVENTH)
    pada = int((value % _TWENTY_SEVENTH) // _PADA_ARC) + 1
    return Nakshatra(index=index, name=NAKSHATRAS[index], pada=pada)


# ── ephemeris lookups ────────────────────────────────────────────────────────

def _sidereal(jd_ut: float, body: int) -> float:
    import swisseph as swe

    from rishivan.chart.ephemeris import _FLAGS, _sidereal_setup

    _sidereal_setup()
    values, _flag = swe.calc_ut(jd_ut, body, _FLAGS)
    return values[0] % 360.0


def sun_and_moon(jd_ut: float) -> tuple[float, float]:
    """Sidereal longitudes of the Sun and the Moon at a Julian day."""
    import swisseph as swe

    return _sidereal(jd_ut, swe.SUN), _sidereal(jd_ut, swe.MOON)


@dataclass(frozen=True, slots=True)
class Limbs:
    """The four computed limbs at one instant, plus when each of them ends."""

    tithi: Tithi
    nakshatra: Nakshatra
    yoga: Yoga
    karana: Karana
    tithi_ends: Optional[datetime] = None
    nakshatra_ends: Optional[datetime] = None
    yoga_ends: Optional[datetime] = None
    karana_ends: Optional[datetime] = None


def _ends_at(jd_ut: float, measure, arc: float, tz_offset: float,
             horizon_days: float = 2.0) -> Optional[datetime]:
    """When the current division ends, by bisection on the ephemeris.

    A panchang states the tithi running at sunrise AND the moment it gives way,
    because "Ekadashi today" is not actionable if it ended at 07:12. Bisection
    rather than a closed form: the Moon's speed varies by a fifth between apogee
    and perigee, so a linear extrapolation from its current rate drifts by tens
    of minutes near the ends of a long tithi.

    Returns None if the boundary is not reached inside the horizon, which for a
    two-day window means something is wrong rather than something is slow.
    """
    import swisseph as swe

    start_value = measure(jd_ut)
    target = (int(start_value // arc) + 1) * arc

    def crossed(jd: float) -> bool:
        # Compared in the frame of the starting value, so the 360 -> 0 wrap
        # does not read as "already past the target".
        return (measure(jd) - start_value) % 360.0 >= (target - start_value) % 360.0

    low, high = jd_ut, jd_ut + horizon_days
    if not crossed(high):
        return None
    # 24 halvings of a two-day window resolves to under a tenth of a second,
    # which is far past the minute these are printed to. 60 was 480 ephemeris
    # calls per panchang for no extra precision.
    for _ in range(24):
        middle = (low + high) / 2.0
        if crossed(middle):
            high = middle
        else:
            low = middle

    year, month, day, hour = swe.revjul(high + tz_offset / 24.0)
    minute_total = int(round(hour * 60.0))
    return datetime(year, month, day) + __import__("datetime").timedelta(
        minutes=minute_total
    )


def limbs_at(jd_ut: float, tz_offset: float = 5.5) -> Limbs:
    """All four computed limbs at an instant, with their end times."""
    sun, moon = sun_and_moon(jd_ut)
    elongation = (moon - sun) % 360.0

    def _elongation(jd: float) -> float:
        s, m = sun_and_moon(jd)
        return (m - s) % 360.0

    def _sum(jd: float) -> float:
        s, m = sun_and_moon(jd)
        return (s + m) % 360.0

    def _moon(jd: float) -> float:
        return sun_and_moon(jd)[1]

    return Limbs(
        tithi=tithi_of(elongation),
        nakshatra=nakshatra_of(moon),
        yoga=yoga_of(sun + moon),
        karana=karana_of(elongation),
        tithi_ends=_ends_at(jd_ut, _elongation, _TITHI_ARC, tz_offset),
        nakshatra_ends=_ends_at(jd_ut, _moon, _TWENTY_SEVENTH, tz_offset),
        yoga_ends=_ends_at(jd_ut, _sum, _TWENTY_SEVENTH, tz_offset),
        karana_ends=_ends_at(jd_ut, _elongation, _KARANA_ARC, tz_offset),
    )
