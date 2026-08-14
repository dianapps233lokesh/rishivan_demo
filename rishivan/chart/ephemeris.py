"""DEMO ONLY — deterministic Vedic birth-chart computation via Swiss Ephemeris.

The LLM never does any of this — it is pure astronomy. Conventions are locked:
sidereal zodiac, Lahiri ayanamsa, whole-sign houses. Getting the sidereal/
ayanamsa part right is what generic AI gets wrong (tropical vs sidereal ~24 deg).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import swisseph as swe

# --- reference data --------------------------------------------------------
RASHIS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
# lord of each rashi (index-aligned with RASHIS)
RASHI_LORDS = [
    "Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury",
    "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter",
]
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishta", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]
# Vimshottari lord ruling each nakshatra, cycling Ketu..Mercury from Ashwini
_VIM_CYCLE = [
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
]
NAKSHATRA_LORDS = [_VIM_CYCLE[i % 9] for i in range(27)]

# Swiss Ephemeris planet ids we use (Rahu = mean node, Ketu = Rahu + 180)
_PLANETS = {
    "Sun": swe.SUN, "Moon": swe.MOON, "Mars": swe.MARS, "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER, "Venus": swe.VENUS, "Saturn": swe.SATURN,
    "Rahu": swe.MEAN_NODE,
}
# Moshier ephemeris: no external data files needed, accuracy ~arcseconds (ample here)
_FLAGS = swe.FLG_MOSEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED

NAKSHATRA_ARC = 360.0 / 27.0      # 13 deg 20'
PADA_ARC = NAKSHATRA_ARC / 4.0


@dataclass
class BirthData:
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int = 0
    tz_offset_hours: float = 5.5   # local time zone offset from UT (IST default)
    lat: float = 0.0
    lon: float = 0.0
    place: str = ""

    def to_utc(self) -> datetime:
        local = datetime(
            self.year, self.month, self.day, self.hour, self.minute, self.second
        )
        return local - timedelta(hours=self.tz_offset_hours)


@dataclass
class PlanetPosition:
    name: str
    longitude: float          # sidereal ecliptic longitude, 0..360
    rashi: str
    rashi_index: int          # 0-11
    degree_in_rashi: float
    house: int                # 1-12 (whole-sign, from lagna)
    nakshatra: str
    pada: int                 # 1-4
    retrograde: bool


@dataclass
class Chart:
    birth: BirthData
    julian_day_ut: float
    ayanamsa: float
    ascendant_longitude: float
    lagna_rashi: str
    lagna_rashi_index: int
    planets: dict[str, PlanetPosition] = field(default_factory=dict)
    house_lords: dict[int, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def _sidereal_setup() -> None:
    swe.set_sid_mode(swe.SIDM_LAHIRI, 0, 0)


def _rashi_of(longitude: float) -> tuple[int, float]:
    idx = int(longitude // 30) % 12
    return idx, longitude - idx * 30


def _nakshatra_of(longitude: float) -> tuple[str, int]:
    n = int(longitude // NAKSHATRA_ARC) % 27
    pada = int((longitude % NAKSHATRA_ARC) // PADA_ARC) + 1
    return NAKSHATRAS[n], pada


def compute_chart(birth: BirthData) -> Chart:
    """Birth details -> full sidereal Vedic chart (whole-sign houses)."""
    _sidereal_setup()
    utc = birth.to_utc()
    ut_hour = utc.hour + utc.minute / 60.0 + utc.second / 3600.0
    jd = swe.julday(utc.year, utc.month, utc.day, ut_hour)

    ayanamsa = swe.get_ayanamsa_ut(jd)

    # Ascendant / lagna via whole-sign houses, sidereal.
    _cusps, ascmc = swe.houses_ex(jd, birth.lat, birth.lon, b"W", swe.FLG_SIDEREAL)
    asc_lon = ascmc[0]
    lagna_idx, _ = _rashi_of(asc_lon)

    chart = Chart(
        birth=birth,
        julian_day_ut=jd,
        ayanamsa=ayanamsa,
        ascendant_longitude=asc_lon,
        lagna_rashi=RASHIS[lagna_idx],
        lagna_rashi_index=lagna_idx,
    )

    def add_planet(name: str, lon: float, speed: float) -> None:
        idx, deg = _rashi_of(lon)
        nak, pada = _nakshatra_of(lon)
        house = (idx - lagna_idx) % 12 + 1   # whole-sign: house counted from lagna sign
        chart.planets[name] = PlanetPosition(
            name=name, longitude=lon, rashi=RASHIS[idx], rashi_index=idx,
            degree_in_rashi=deg, house=house, nakshatra=nak, pada=pada,
            retrograde=speed < 0,
        )

    for name, pid in _PLANETS.items():
        pos, _ret = swe.calc_ut(jd, pid, _FLAGS)
        add_planet(name, pos[0], pos[3])

    # Ketu is exactly opposite Rahu; nodes are always retrograde by convention.
    rahu = chart.planets["Rahu"]
    ketu_lon = (rahu.longitude + 180.0) % 360.0
    add_planet("Ketu", ketu_lon, -1.0)

    # Whole-sign house lords: house n's sign is (lagna_idx + n - 1)
    for h in range(1, 13):
        sign_idx = (lagna_idx + h - 1) % 12
        chart.house_lords[h] = RASHI_LORDS[sign_idx]

    return chart


# Whether a question is a display request ("show me my chart") versus an
# interpretation question ("what sign is my moon in?") is decided by the
# classifier LLM call (rishivan.council.classifier — intent/chart_type/
# varga_code fields). The tables themselves are rendered by
# rishivan.chart.local_varga (all sixteen vargas, D1 included) and
# rishivan.chart.local_numerology — both compute locally via the main
# repo's pure-arithmetic engines.


def summarize(chart: Chart) -> str:
    """Human-readable one-screen chart summary (for the UI + sanity checking)."""
    lines = [
        f"Birth: {chart.birth.place or 'unknown'} "
        f"{chart.birth.year:04d}-{chart.birth.month:02d}-{chart.birth.day:02d} "
        f"{chart.birth.hour:02d}:{chart.birth.minute:02d} "
        f"(TZ {chart.birth.tz_offset_hours:+g})",
        f"Ayanamsa (Lahiri): {chart.ayanamsa:.4f} deg",
        f"Lagna (Ascendant): {chart.lagna_rashi} "
        f"({chart.ascendant_longitude:.2f} deg sidereal)",
        "",
        f"{'Planet':<8}{'Rashi':<12}{'Deg':>7}  {'House':>5}  "
        f"{'Nakshatra':<16}{'Pada':>4}  Retro",
    ]
    order = [
        "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu",
    ]
    for name in order:
        p = chart.planets[name]
        lines.append(
            f"{p.name:<8}{p.rashi:<12}{p.degree_in_rashi:>6.2f}  {p.house:>5}  "
            f"{p.nakshatra:<16}{p.pada:>4}  {'R' if p.retrograde else '-'}"
        )
    return "\n".join(lines)
