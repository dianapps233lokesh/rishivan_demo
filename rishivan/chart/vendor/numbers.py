"""Mulank, bhagyaank, and the zero-ephemeris solar-sign tables for the chips.

VENDORED from the main repo's app/astro/ankshastra/numbers.py — see
rishivan/chart/vendor/__init__.py for why. Keep this in sync manually.
"""

from __future__ import annotations

from datetime import date

TROPICAL_BOUNDARIES = (
    (1, 20, 10),
    (2, 19, 11),
    (3, 21, 0),
    (4, 20, 1),
    (5, 21, 2),
    (6, 21, 3),
    (7, 23, 4),
    (8, 23, 5),
    (9, 23, 6),
    (10, 23, 7),
    (11, 22, 8),
    (12, 22, 9),
)
"""(month, day, sign) — the first day each tropical sun sign begins."""

SIDEREAL_BOUNDARIES = (
    (1, 15, 9),
    (2, 13, 10),
    (3, 15, 11),
    (4, 14, 0),
    (5, 15, 1),
    (6, 15, 2),
    (7, 16, 3),
    (8, 17, 4),
    (9, 17, 5),
    (10, 18, 6),
    (11, 16, 7),
    (12, 16, 8),
)
"""(month, day, sign) — the first day each sidereal solar rashi begins."""

_BOUNDARIES = {"western": TROPICAL_BOUNDARIES, "vedic": SIDEREAL_BOUNDARIES}

CUSP_TOLERANCE_DAYS = 1
"""Boundaries drift ~1 day year to year; the chip is refined from the chart
once it is ready."""


def reduce_to_digit(value: int) -> int:
    """Repeatedly sum digits until a single digit 1-9 remains."""
    while value > 9:
        value = sum(int(char) for char in str(value))
    return value


def mulank(dob: date) -> int:
    """Birth (psychic) number — the day of month reduced to 1-9."""
    return reduce_to_digit(dob.day)


def bhagyaank(dob: date) -> int:
    """Destiny (life-path) number — all digits of ddmmyyyy summed, then reduced.

    Pinned convention. The alternative (reduce each component first, then sum)
    gives different answers on some dates and is deliberately not used.
    """
    digits = f"{dob.day:02d}{dob.month:02d}{dob.year:04d}"
    return reduce_to_digit(sum(int(char) for char in digits))


def solar_sign(dob: date, system: str) -> int:
    """0-based solar sign from a date table — no ephemeris, so always available."""
    boundaries = _BOUNDARIES[system]
    key = (dob.month, dob.day)
    # dates before January's boundary belong to the sign that began in December
    latest = boundaries[-1][2]
    for month, day, sign in boundaries:
        if key >= (month, day):
            latest = sign
    return latest
