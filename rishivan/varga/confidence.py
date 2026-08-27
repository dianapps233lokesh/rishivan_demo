"""How much of a recorded birth time is actually known.

`BirthData` stores hour, minute and second and says nothing about precision -
a real gap, because the whole "no false precision" discipline needs that number.
So it is inferred from how *round* the recorded time is, and the caller may
override.

The inference is a heuristic over the digits, and it is labelled one. `4:37:00`
was read off something; `12:00` and `4:30` were almost certainly rounded to the
nearest convenient number. It is not always right - some people are born exactly
on the hour - but it errs toward caution, which is the direction that costs a
varga rather than fabricating one.

The gate itself is arithmetic. The ascendant moves about 15 degrees an hour, so
half an hour of uncertainty is 7.5 degrees. A D60 division is 0.5 degrees wide.
That is fifteen divisions of noise, and no amount of astrological skill recovers
a sign from it.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional

ASCENDANT_DEGREES_PER_HOUR = 15.0
"""360 degrees in roughly 24 hours. A mean, not a latitude-corrected figure -
the real rate swings with latitude and season, and the gate is a floor rather
than a measurement, so the mean is the honest input."""


class BirthConfidence(IntEnum):
    """Ordered, because the gate is `actual >= required`."""

    UNKNOWN = 0
    """No usable time. Noon assumed, and every time-sensitive varga withheld."""

    HOUR = 1
    """On the hour, or known to about half an hour."""

    QUARTER = 2
    """On a quarter or five-minute mark - rounded, but rounded finely."""

    MINUTE = 3
    """To the minute, or rectified."""

    EXACT = 4
    """Seconds recorded. Rare outside a hospital note."""


#: Half-width of the uncertainty each confidence implies, in minutes of clock
#: time. UNKNOWN is half a day: noon assumed against a birth anywhere in it.
_UNCERTAINTY_MINUTES: dict[BirthConfidence, float] = {
    BirthConfidence.UNKNOWN: 12 * 60.0,
    BirthConfidence.HOUR: 30.0,
    BirthConfidence.QUARTER: 15.0,
    BirthConfidence.MINUTE: 1.0,
    BirthConfidence.EXACT: 1.0 / 60.0,
}


def uncertainty_minutes(confidence: BirthConfidence) -> float:
    """How far the recorded clock time could be out, in minutes.

    The quantity every other uncertainty here is derived from. Public because
    the ascendant is not the only thing a wrong birth time moves: each graha
    moves at its own rate, and `varga.select` needs the clock error to work
    those out. It used to reach for `arc_uncertainty_degrees` instead, which is
    the ascendant's figure, and applied it to the grahas as well - a category
    error that made the varga rescue arithmetically unsatisfiable.
    """
    return _UNCERTAINTY_MINUTES[confidence]


def arc_uncertainty_degrees(confidence: BirthConfidence) -> float:
    """How far *the ascendant* could be wrong, given this confidence.

    Specific to the ascendant, despite the general name. Nothing else in a chart
    moves at 15 degrees an hour.
    """
    return uncertainty_minutes(confidence) / 60.0 * ASCENDANT_DEGREES_PER_HOUR


def drift_degrees(confidence: BirthConfidence, speed_deg_per_day: float) -> float:
    """How far a body moving at this speed could be out, given this confidence.

    The graha counterpart of `arc_uncertainty_degrees`. At quarter-hour
    precision the ascendant could be 3.75 degrees out; the Moon could be 0.13
    out and Saturn 0.001. Those are the numbers that decide whether a division
    is readable, and they differ by three orders of magnitude.
    """
    return abs(speed_deg_per_day) * uncertainty_minutes(confidence) / (24.0 * 60.0)


def min_confidence_for_arc(arc_degrees: float) -> BirthConfidence:
    """The coarsest confidence whose uncertainty fits inside one division.

    Arithmetic rather than a lookup table, so a varga this codebase has never
    heard of still gets a correct answer - which is what keeps the policy table
    maintainable as divisions are added.
    """
    for confidence in BirthConfidence:
        if arc_uncertainty_degrees(confidence) <= arc_degrees:
            return confidence
    return BirthConfidence.EXACT


def infer_confidence(birth) -> BirthConfidence:
    """Read precision off the roundness of the recorded time."""
    if birth is None:
        return BirthConfidence.UNKNOWN

    hour = getattr(birth, "hour", 0)
    minute = getattr(birth, "minute", 0)
    second = getattr(birth, "second", 0)

    if hour == 0 and minute == 0 and second == 0:
        # What a form defaults to when nobody entered anything. Treating it as a
        # real time is how a D60 reading gets built on a blank field.
        return BirthConfidence.UNKNOWN
    if second:
        return BirthConfidence.EXACT
    if minute % 60 == 0:
        return BirthConfidence.HOUR
    if minute % 5 == 0:
        # Includes the quarter hours. Somebody who says "twenty past" is
        # rounding, but rounding finely.
        return BirthConfidence.QUARTER
    return BirthConfidence.MINUTE


def resolve_confidence(
    birth, override: Optional[BirthConfidence] = None
) -> BirthConfidence:
    """The override if there is one, otherwise the inference.

    A rectified chart knows its own precision better than any heuristic over the
    digits can, and so does a user who was handed a hospital record.
    """
    if override is not None:
        return override
    return infer_confidence(birth)
