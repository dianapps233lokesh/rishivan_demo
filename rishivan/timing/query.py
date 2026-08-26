"""Periods and windows at an arbitrary moment.

Blueprint §8: *"Support arbitrary date-time queries."* Which in practice means
one discipline - never read the clock inside a computation. A backtest asks about
1998 and a Prashna cast for a stated moment asks about that moment; an engine
that quietly answers about today is wrong in a way that produces plausible
output, which is the hard kind to notice.

The second half is `TimingReport`. Multiple dasha systems provide *independent*
evidence, and the blueprint is explicit that they must not be blended. So they
sit under their own keys and the report measures agreement rather than averaging
it - two systems agreeing is evidence a reviewer can weigh, two systems averaged
is a number nobody can check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from rishivan.chart.dasha import Period, current_periods
from rishivan.chart.ephemeris import Chart
from rishivan.chartstate.types import ChartState
from rishivan.timing.windows import EventWindow, event_window

PRIMARY_SYSTEM = "vimshottari"
"""Vimshottari first, and made extremely reliable, exactly as §8 orders. A
second system is added only once a research specification exists for it."""


def periods_at(chart: Chart, when: datetime) -> dict[str, Optional[Period]]:
    """Every Vimshottari level running at `when`.

    A thin pass-through to `chart/dasha.py`, which already walks five levels and
    stops honestly where float arithmetic lands a moment on a boundary.
    Re-deriving the boundaries here would be a second implementation of the one
    calculation the whole timing layer rests on.

    Deliberately not cached. The plan called for memoising on
    `(chart_digest, when)`, but the walk is a few dozen date comparisons and
    `Chart` is a mutable dataclass - keying a cache on a digest computed from a
    mutable object is how a stale answer outlives the edit that invalidated it.
    Revisit if it ever shows up in a profile.
    """
    return current_periods(chart, when)


def windows_between(
    chart: Chart,
    state: ChartState,
    domain: str,
    start: datetime,
    end: datetime,
    *,
    promise: bool,
) -> EventWindow:
    """The five-stage window for one domain across a horizon."""
    if end < start:
        # A caller bug. Swapping silently would surface it three layers away as
        # an empty window, which reads as "the chart says nothing".
        raise ValueError(f"horizon ends before it starts: {start} .. {end}")
    return event_window(
        chart, state, domain, start=start, end=end, promise=promise
    )


@dataclass(frozen=True, slots=True)
class TimingReport:
    """One window per dasha system, unblended."""

    by_system: dict[str, EventWindow] = field(default_factory=dict)

    @property
    def primary(self) -> Optional[str]:
        if PRIMARY_SYSTEM in self.by_system:
            return PRIMARY_SYSTEM
        return next(iter(self.by_system), None)

    def agreement(self) -> Optional[float]:
        """How far the systems concur, or None with fewer than two.

        Reported, never folded in. A second system that agrees is genuine
        corroboration and worth more than another restatement of the first; one
        that disagrees is exactly the thing a reader should see rather than have
        averaged away.
        """
        windows = list(self.by_system.values())
        if len(windows) < 2:
            return None

        promises = {w.promise for w in windows}
        if len(promises) > 1:
            return 0.0

        activations = {
            (w.activation.start, w.activation.end) if w.activation else None
            for w in windows
        }
        return 1.0 if len(activations) == 1 else 0.5
