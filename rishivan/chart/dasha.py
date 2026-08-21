"""DEMO ONLY — Vimshottari Dasha, the timing engine (which period runs when).

Derived deterministically from the Moon's nakshatra at birth. Pure arithmetic;
no LLM. Produces the mahadasha timeline and the currently-running
periods running at a given moment, from mahadasha down to prana.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from rishivan.chart.ephemeris import _VIM_CYCLE, NAKSHATRA_ARC, Chart

DASHA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}
TOTAL_YEARS = 120           # sum of DASHA_YEARS
DAYS_PER_YEAR = 365.2425
ORDER = _VIM_CYCLE          # Ketu, Venus, Sun, Moon, Mars, Rahu, Jupiter, Saturn, Merc


@dataclass
class Period:
    lord: str
    start: datetime
    end: datetime
    level: str              # one of DASHA_LEVELS

    def contains(self, when: datetime) -> bool:
        return self.start <= when < self.end


def _birth_instant(chart: Chart) -> datetime:
    b = chart.birth
    return datetime(b.year, b.month, b.day, b.hour, b.minute, b.second)


def _sequence_from(lord: str) -> list[str]:
    i = ORDER.index(lord)
    return ORDER[i:] + ORDER[:i]


def mahadasha_timeline(chart: Chart) -> list[Period]:
    """Full sequence of mahadashas from birth (first one is the balance at birth)."""
    moon_lon = chart.planets["Moon"].longitude
    nak_index = int(moon_lon // NAKSHATRA_ARC) % 27
    start_lord = ORDER[nak_index % 9]

    fraction_traversed = (moon_lon % NAKSHATRA_ARC) / NAKSHATRA_ARC
    balance_years = DASHA_YEARS[start_lord] * (1.0 - fraction_traversed)

    periods: list[Period] = []
    cursor = _birth_instant(chart)
    for k, lord in enumerate(_sequence_from(start_lord)):
        years = balance_years if k == 0 else DASHA_YEARS[lord]
        end = cursor + timedelta(days=years * DAYS_PER_YEAR)
        periods.append(Period(lord=lord, start=cursor, end=end, level="maha"))
        cursor = end
    return periods


def _sub_periods(parent: Period, level: str) -> list[Period]:
    """Antar/pratyantar within a parent period, proportional to Vimshottari years."""
    span = parent.end - parent.start
    subs: list[Period] = []
    cursor = parent.start
    for lord in _sequence_from(parent.lord):
        frac = DASHA_YEARS[lord] / TOTAL_YEARS
        end = cursor + span * frac
        subs.append(Period(lord=lord, start=cursor, end=end, level=level))
        cursor = end
    return subs


SUB_LEVELS: tuple[str, ...] = ("antar", "pratyantar", "sookshma", "prana")
DASHA_LEVELS: tuple[str, ...] = ("maha", *SUB_LEVELS)
"""Every level the rule corpus cites, coarsest first.

Not an arbitrary depth. Across the extracted corpus the activation atoms name maha 217
times, antar 277, pratyantar 51, sookshma 56 and prana 36 -- so stopping at pratyantar,
as this function used to, left 92 atoms addressing a period nothing computed.
"""


def current_periods(
    chart: Chart, when: datetime | None = None
) -> dict[str, Period | None]:
    """The periods running at `when` (default: now, naive local), by level.

    Every key in `DASHA_LEVELS` is always present; a level is None when no period at
    that depth contains `when`. Callers may therefore index a level without knowing how
    deep the subdivision went.

    Each level subdivides the one above in Vimshottari proportion, so this walks down
    rather than recomputing from birth. It stops at the first level that contains no
    period: at prana depth the spans are hours and the float arithmetic can land `when`
    on a boundary, and reporting nothing is honest where guessing a neighbour is not.
    """
    if when is None:
        when = datetime.now()

    running: dict[str, Period | None] = dict.fromkeys(DASHA_LEVELS, None)

    maha = next((p for p in mahadasha_timeline(chart) if p.contains(when)), None)
    if maha is None:
        return running

    running["maha"] = maha
    parent = maha
    for level in SUB_LEVELS:
        child = next((p for p in _sub_periods(parent, level) if p.contains(when)), None)
        if child is None:
            break
        running[level] = child
        parent = child

    return running
