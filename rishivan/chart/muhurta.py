"""Choosing a time, as arithmetic rather than as the model's opinion.

There was no muhurta engine. `QueryDomain.MUHURTA` cast a chart for the target
moment and computed Rahu Kaal, and then the model decided whether tomorrow was
good — a judgement standing exactly where a table belongs, unauditable and
sourced from training data.

This is that table. Three classical instruments, all pure arithmetic on sunrise,
sunset and the panchang limbs:

  * **Choghadiya** — the day and the night each in eight parts, each ruled by a
    graha and carrying that graha's verdict.
  * **Abhijit** — the eighth of fifteen day-muhurtas, straddling local noon, the
    one window classically held to override most objections.
  * **Collisions** — a Labh slot that overlaps Rahu Kaal is not a good hour, and
    the two tables know nothing about each other. Somebody has to intersect them
    and it should not be a language model.

**It ranks; it does not rule.** A muhurta engine that answers yes or no has
thrown away the reason, and the reason is what a seeker can act on. Every window
carries its verdict and every rejection carries its cause.

**Conventions are named, per the repo's standing rule that no method ships
without a source.** The Choghadiya construction and the Wednesday exception for
Abhijit both vary between lineages, so each says which reading it implements.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rishivan.chart.panchang import _CHALDEAN, _DAY_LORD, _fmt, Window

CHOGHADIYA_QUALITY: dict[str, str] = {
    "Amrit": "good",
    "Shubh": "good",
    "Labh": "good",
    "Chal": "neutral",
    "Udveg": "bad",
    "Kaal": "bad",
    "Rog": "bad",
}

GOOD = tuple(name for name, verdict in CHOGHADIYA_QUALITY.items()
             if verdict == "good")

_CHOGHADIYA_OF_LORD: dict[str, str] = {
    "Sun": "Udveg", "Venus": "Chal", "Mercury": "Labh", "Moon": "Amrit",
    "Saturn": "Kaal", "Jupiter": "Shubh", "Mars": "Rog",
}

CHOGHADIYA_METHOD = (
    "Day and night each divided into eight equal parts. The day's first part is "
    "ruled by the lord of the weekday and the rest follow in Chaldean order — "
    "the same cycle the hora uses. The night's first part is ruled by the lord "
    "of the FIFTH weekday counted from today, and then follows the same order."
)

ABHIJIT_METHOD = (
    "The eighth of fifteen equal day-muhurtas, so it straddles local noon by "
    "construction. Held void on Wednesday in the convention implemented here; "
    "some lineages do not make that exception."
)

_MUHURTAS_PER_DAY = 15
_ABHIJIT_INDEX = 7


@dataclass(frozen=True, slots=True)
class Slot:
    """One choghadiya part, or Abhijit, with everything against it."""

    name: str
    period: str
    """`day`, `night`, or `special` for Abhijit."""

    start: str
    end: str
    duration_minutes: int
    lord: str = ""
    collisions: tuple[str, ...] = field(default=())
    """Which computed inauspicious windows this overlaps. A good choghadiya
    inside Rahu Kaal is not a good hour."""

    reasons: tuple[str, ...] = field(default=())

    @property
    def quality(self) -> str:
        return CHOGHADIYA_QUALITY.get(self.name, "good")

    @property
    def recommended(self) -> bool:
        return self.quality == "good" and not self.collisions


@dataclass(frozen=True, slots=True)
class DayAssessment:
    """The day's windows, ranked, and what applies to the whole of it."""

    windows: tuple[Slot, ...]
    day_notes: tuple[str, ...] = ()
    """Factors that qualify the entire day rather than one window — a rikta
    tithi, Vishti karana, an inauspicious yoga. Reported, never used to veto:
    whether a rikta tithi rules out a particular undertaking is the reading's
    call."""

    def best(self, limit: int = 4) -> tuple[Slot, ...]:
        """The recommended daytime windows, earliest first."""
        return tuple(
            slot for slot in self.windows
            if slot.recommended and slot.period != "night"
        )[:limit]


def _to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _overlaps(start: str, end: str, window: Window) -> bool:
    """Do two clock spans intersect, tolerating a span that crosses midnight?"""
    a_start, a_end = _to_minutes(start), _to_minutes(end)
    b_start, b_end = _to_minutes(window.start), _to_minutes(window.end)
    if a_end <= a_start:
        a_end += 24 * 60
    if b_end <= b_start:
        b_end += 24 * 60
    return a_start < b_end and b_start < a_end


def choghadiya(panchang) -> tuple[Slot, ...]:
    """The sixteen parts of the day and night, each with its ruler and verdict."""
    sunrise = _to_minutes(panchang.sunrise)
    sunset = _to_minutes(panchang.sunset)
    day_length = (sunset - sunrise) % (24 * 60) or 24 * 60
    night_length = 24 * 60 - day_length

    weekday = panchang.day.weekday()
    day_lord = _DAY_LORD[weekday]
    # The night opens on the lord of the FIFTH weekday from today, not on a
    # continuation of the day's cycle. Sunday night is Jupiter's because
    # Thursday is the fifth day from Sunday.
    night_lord = _DAY_LORD[(weekday + 4) % 7]

    slots: list[Slot] = []
    for period, first_lord, start, length in (
        ("day", day_lord, sunrise, day_length),
        ("night", night_lord, sunset, night_length),
    ):
        part = length / 8.0
        origin = _CHALDEAN.index(first_lord)
        for index in range(8):
            lord = _CHALDEAN[(origin + index) % 7]
            begins = start + index * part
            slots.append(Slot(
                name=_CHOGHADIYA_OF_LORD[lord],
                period=period,
                start=_fmt(begins / 60.0),
                end=_fmt((begins + part) / 60.0),
                duration_minutes=int(round(part)),
                lord=lord,
            ))
    return tuple(slots)


def abhijit_muhurta(panchang) -> Optional[Slot]:
    """The noon muhurta, or None where the convention withholds it."""
    if panchang.day.weekday() == 2:
        # Wednesday. See `ABHIJIT_METHOD` — named rather than silently applied.
        return None
    sunrise = _to_minutes(panchang.sunrise)
    part = panchang.day_length_minutes / _MUHURTAS_PER_DAY
    begins = sunrise + _ABHIJIT_INDEX * part
    return Slot(
        name="Abhijit",
        period="special",
        start=_fmt(begins / 60.0),
        end=_fmt((begins + part) / 60.0),
        duration_minutes=int(round(part)),
        reasons=("the noon muhurta, classically held to override most "
                 "objections short of a hard prohibition",),
    )


def assess_day(panchang, limbs) -> DayAssessment:
    """Every window of the day with its verdict, and what qualifies all of them.

    The intersection is the point. Rahu Kaal, Yamaganda and Gulika come from one
    table and the Choghadiya from another; neither knows the other exists, and
    until now nothing crossed them — so "Labh is running" could be said about an
    hour sitting squarely inside Rahu Kaal.
    """
    inauspicious = (panchang.rahu_kaal, panchang.yamaganda, panchang.gulika)

    windows: list[Slot] = []
    for slot in choghadiya(panchang):
        collisions = tuple(
            window.name for window in inauspicious
            if _overlaps(slot.start, slot.end, window)
        )
        reasons: list[str] = [
            f"{slot.name} ({slot.lord}) — {CHOGHADIYA_QUALITY[slot.name]}"
        ]
        reasons += [f"overlaps {name}" for name in collisions]
        windows.append(Slot(
            name=slot.name, period=slot.period, start=slot.start, end=slot.end,
            duration_minutes=slot.duration_minutes, lord=slot.lord,
            collisions=collisions, reasons=tuple(reasons),
        ))

    abhijit = abhijit_muhurta(panchang)
    if abhijit is not None:
        collisions = tuple(
            window.name for window in inauspicious
            if _overlaps(abhijit.start, abhijit.end, window)
        )
        windows.append(Slot(
            name=abhijit.name, period=abhijit.period, start=abhijit.start,
            end=abhijit.end, duration_minutes=abhijit.duration_minutes,
            collisions=collisions,
            reasons=abhijit.reasons + tuple(
                f"overlaps {name}" for name in collisions
            ),
        ))

    notes: list[str] = []
    if limbs is not None:
        if limbs.tithi.rikta:
            notes.append(
                f"{limbs.tithi.name} is a rikta tithi (the 4th, 9th and 14th of "
                f"a fortnight) — classically avoided for beginnings"
            )
        if limbs.karana.inauspicious:
            notes.append(
                f"the karana is Vishti (Bhadra), which classical muhurta rejects "
                f"outright while it runs"
            )
        if limbs.yoga.inauspicious:
            notes.append(
                f"the yoga is {limbs.yoga.name}, one of the two held "
                f"inauspicious for undertakings"
            )
    return DayAssessment(windows=tuple(windows), day_notes=tuple(notes))
