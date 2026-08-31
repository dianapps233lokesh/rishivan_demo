"""Daily timing windows — Rahu Kaal, Yamaganda, Gulika, and the planetary hora.

Pure arithmetic on sunrise and sunset, not interpretation: the daylight span is
divided into eight equal parts and each weekday assigns fixed parts to the
inauspicious windows. Because these are computed, the model must never guess
them — it receives them as ground truth the way it receives chart placements.

Conventions match the rest of the chart engine: Swiss Ephemeris, local clock
time via an explicit UTC offset, disc-centre sunrise without refraction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import swisseph as swe

logger = logging.getLogger(__name__)

# Which eighth of the day belongs to each window, indexed by Python's
# weekday() (Monday=0 … Sunday=6). Parts are 0-based from sunrise.
_RAHU_PART = {0: 1, 1: 6, 2: 4, 3: 5, 4: 3, 5: 2, 6: 7}
_YAMAGANDA_PART = {0: 3, 1: 2, 2: 1, 3: 0, 4: 6, 5: 5, 6: 4}
_GULIKA_PART = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1, 5: 0, 6: 6}

# Hora lords cycle in Chaldean order, starting at sunrise with the day's lord.
_CHALDEAN = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury", "Moon"]
_DAY_LORD = {
    0: "Moon", 1: "Mars", 2: "Mercury", 3: "Jupiter",
    4: "Venus", 5: "Saturn", 6: "Sun",
}

_SUN_FLAGS = swe.BIT_DISC_CENTER | swe.BIT_NO_REFRACTION


@dataclass(frozen=True)
class Window:
    """An inauspicious span, as local clock times."""

    name: str
    start: str          # "HH:MM"
    end: str            # "HH:MM"
    duration_minutes: int


@dataclass(frozen=True)
class Panchang:
    day: date
    weekday: str
    place: str
    sunrise: str
    sunset: str
    day_length_minutes: int
    rahu_kaal: Window
    yamaganda: Window
    gulika: Window
    day_lord: str
    hora_lord_now: str | None = None
    limbs: object | None = None
    """The four computed limbs at sunrise - a `chart.limbs.Limbs`, or None when
    the ephemeris lookup failed.

    **This class was named `Panchang` while computing none of the panchang.** It
    held the windows: sunrise, sunset, Rahu Kaal, Yamaganda, Gulika, the hora.
    Every one of those is arithmetic on sunrise and every one was right. But the
    word names five limbs - vara, tithi, nakshatra, yoga, karana - and four were
    absent, so a reading that stated a tithi produced one from the model's
    training data. A wrong Rahu Kaal is checkable against any almanac; a wrong
    tithi reads exactly like a right one.

    Taken AT SUNRISE, which is the convention a panchang prints: the tithi
    running when the day begins is the day's tithi, however early it gives way.
    Each limb carries the moment it ends, because "Ekadashi today" is not
    actionable if it ended at 07:12."""

    def summary(self) -> str:
        """Ground-truth block for the prompt; every value here is computed."""
        lines = [
            f"Date: {self.day.isoformat()} ({self.weekday})"
            f"{f' at {self.place}' if self.place else ''}",
            f"Sunrise: {self.sunrise}   Sunset: {self.sunset}",
        ]
        if self.limbs is not None:
            lines += self._limb_lines()
        lines += [
            f"Rahu Kaal: {self.rahu_kaal.start} to {self.rahu_kaal.end}",
            f"Yamaganda: {self.yamaganda.start} to {self.yamaganda.end}",
            f"Gulika Kaal: {self.gulika.start} to {self.gulika.end}",
            f"Lord of the day: {self.day_lord}",
        ]
        return "\n".join(lines)

    def _limb_lines(self) -> list[str]:
        """The four limbs, each with the moment it gives way.

        The five are printed together and labelled, because "panchang" means
        these five and a block that prints two of them under that heading
        invites the model to supply the rest.
        """
        def _until(moment) -> str:
            """When it gives way, dated when that is not today.

            A bare "until 03:45" beside a 06:02 sunrise reads as already past,
            which inverts the fact: a nakshatra ending at 03:45 tomorrow runs
            for the whole of today. These are the values the model converts into
            "you have until...", so an off-by-a-day here becomes wrong advice.
            """
            if moment is None:
                return ""
            if moment.date() == self.day:
                return f" until {moment:%H:%M}"
            if (moment.date() - self.day).days == 1:
                return f" until {moment:%H:%M} tomorrow"
            return f" until {moment:%H:%M} on {moment:%Y-%m-%d}"

        limbs = self.limbs
        return [
            f"Tithi: {limbs.tithi.name}"
            f" ({limbs.tithi.paksha} paksha, {limbs.tithi.number} of 15)"
            f"{_until(limbs.tithi_ends)}",
            f"Nakshatra: {limbs.nakshatra.name} pada {limbs.nakshatra.pada}"
            f"{_until(limbs.nakshatra_ends)}",
            f"Yoga: {limbs.yoga.name}{_until(limbs.yoga_ends)}",
            f"Karana: {limbs.karana.name}{_until(limbs.karana_ends)}",
        ]


def _fmt(hours: float) -> str:
    """Fractional hours (0-24) as local HH:MM, rounding to the nearest minute."""
    total = int(round(hours * 60)) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _sun_event(jd_midnight: float, lat: float, lon: float, rising: bool,
               tz_offset: float) -> float:
    """Local fractional hour of the next sunrise/sunset after jd_midnight."""
    flag = (swe.CALC_RISE if rising else swe.CALC_SET) | _SUN_FLAGS
    _res, times = swe.rise_trans(
        jd_midnight, swe.SUN, rsmi=flag, geopos=(lon, lat, 0.0)
    )
    _y, _m, _d, ut_hour = swe.revjul(times[0])
    return (ut_hour + tz_offset) % 24


def _window(name: str, sunrise: float, part_len: float, part: int) -> Window:
    start = sunrise + part * part_len
    end = start + part_len
    return Window(name, _fmt(start), _fmt(end), int(round(part_len * 60)))


def compute_panchang(
    day: date,
    lat: float = 28.6139,
    lon: float = 77.2090,
    tz_offset: float = 5.5,
    place: str = "",
    now_hour: float | None = None,
    with_limbs: bool = True,
) -> Panchang:
    """Daily timing windows for one date and place.

    ``now_hour`` is the current local time in fractional hours; when given, the
    ruling hora for that moment is resolved too.
    """
    jd_midnight = swe.julday(day.year, day.month, day.day, 0.0) - tz_offset / 24.0
    sunrise = _sun_event(jd_midnight, lat, lon, True, tz_offset)
    sunset = _sun_event(jd_midnight, lat, lon, False, tz_offset)

    limbs = None
    if with_limbs:
        from rishivan.chart.limbs import limbs_at

        try:
            # At sunrise, in UT. The tithi running when the day begins is the
            # day's tithi, which is the convention every printed panchang uses.
            limbs = limbs_at(jd_midnight + sunrise / 24.0, tz_offset)
        except Exception:  # noqa: BLE001
            # A failed limb lookup must not cost the reader their windows, which
            # are computed and correct. It costs them four lines, and the block
            # simply omits them rather than guessing.
            logger.warning("could not compute the panchang limbs", exc_info=True)

    # Guard the polar / date-boundary case where sunset lands before sunrise.
    day_length = (sunset - sunrise) % 24
    part_len = day_length / 8.0
    wd = day.weekday()

    return Panchang(
        day=day,
        weekday=day.strftime("%A"),
        place=place,
        sunrise=_fmt(sunrise),
        sunset=_fmt(sunset),
        day_length_minutes=int(round(day_length * 60)),
        rahu_kaal=_window("Rahu Kaal", sunrise, part_len, _RAHU_PART[wd]),
        yamaganda=_window("Yamaganda", sunrise, part_len, _YAMAGANDA_PART[wd]),
        gulika=_window("Gulika Kaal", sunrise, part_len, _GULIKA_PART[wd]),
        day_lord=_DAY_LORD[wd],
        hora_lord_now=(
            hora_lord(day, sunrise, now_hour) if now_hour is not None else None
        ),
        limbs=limbs,
    )


def hora_lord(day: date, sunrise: float, local_hour: float) -> str:
    """Planetary hour ruler: one clock hour each, Chaldean order from sunrise."""
    elapsed = (local_hour - sunrise) % 24
    start = _CHALDEAN.index(_DAY_LORD[day.weekday()])
    return _CHALDEAN[(start + int(elapsed)) % 7]


# ── Question routing ─────────────────────────────────────────────────────────
# Matched deterministically rather than via the classifier: these windows are
# computed facts, and a routing miss makes the app deflect a question it can
# answer exactly.
_PANCHANG_TERMS = (
    "rahu kaal", "rahukaal", "rahu kal", "rahukal", "rahu-kaal",
    "yamaganda", "yamagandam", "gulika", "gulikai", "kuligai",
    "choghadiya", "chogadiya", "hora", "abhijit",
    "sunrise", "sunset", "panchang", "panchanga", "muhurat", "muhurta",
    "auspicious time", "shubh time", "shubh muhurat", "good time today",
    "inauspicious time", "राहु काल", "राहुकाल", "शुभ मुहूर्त", "पंचांग",
    # The limbs themselves. They are computed now, and until they were, routing
    # a question here would have handed back a block that did not contain the
    # answer - so the terms were correctly absent and are correctly here.
    "tithi", "करण", "karana", "paksha", "ekadashi", "amavasya", "purnima",
    "pournami", "तिथि",
    # Multi-word only. A bare "nakshatra" is usually "what is MY nakshatra",
    # which is a natal question, and a bare "yoga" collides with the
    # astrological yogas - "which yogas do I have" is not a question about
    # today. Routing either to the daily windows would answer the wrong one.
    "nakshatra today", "today's nakshatra", "nakshatra of the day",
    "yoga today", "today's yoga",
)

_RELATIVE_DAYS = {
    "day after tomorrow": 2, "parso": 2, "परसों": 2,
    "tomorrow": 1, "kal": 1, "कल": 1,
    "today": 0, "aaj": 0, "आज": 0, "tonight": 0,
}


def mentions_panchang(question: str) -> bool:
    """Whether the question asks for a computable daily timing window."""
    q = question.lower()
    return any(term in q for term in _PANCHANG_TERMS)


def relative_day_offset(question: str) -> int:
    """Day offset the question refers to; 0 (today) when nothing is said.

    Longest phrases are checked first so "day after tomorrow" is not read as
    "tomorrow".
    """
    q = question.lower()
    for phrase, offset in _RELATIVE_DAYS.items():
        if phrase in q:
            return offset
    return 0
