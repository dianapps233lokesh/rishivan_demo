"""The blueprint's five-stage timing output.

    promise → activation → trigger → peak → fading

**The promise gate is the point of the module.** A timing question about an
event the chart does not promise has no answer worth computing, and producing a
window anyway is the most common way an astrology product invents a prediction:
the dasha arithmetic always yields *a* period, so a pipeline that starts from the
periods will always produce a date. Starting from the promise means the honest
answer - "the chart does not indicate this, so there is no window to give you" -
is reachable.

So `promise=False` returns every stage as `None`. Not a low confidence. None.

**How the stages map onto Vimshottari:**

    activation  the mahadasha whose lord activates the domain
    trigger     an antardasha inside it whose lord also activates the domain
    peak        the pratyantar inside the trigger that does the same
    fading      the tail of the activation window after the trigger closes

Each level narrows the one above, which is what "trigger window" means: the
mahadasha says the decade, the antardasha says the year, the pratyantar says the
months. Exact boundaries come from `chart/dasha.py` and are never re-derived.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from rishivan.chart.dasha import Period, mahadasha_timeline, sub_periods
from rishivan.chart.ephemeris import Chart
from rishivan.chartstate.types import ChartState
from rishivan.timing.activation import activates_domain, domain_overlap


@dataclass(frozen=True, slots=True)
class DateRange:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end < self.start:
            # A bug upstream. Silently swapping them hides it, and a window
            # that runs backwards is the kind of thing that survives to
            # production because it looks like a formatting problem.
            raise ValueError(f"window ends before it starts: {self.start} .. {self.end}")

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    def __str__(self) -> str:
        return f"{self.start:%b %Y} – {self.end:%b %Y}"


@dataclass(frozen=True, slots=True)
class EventWindow:
    promise: bool
    promise_basis: tuple[str, ...]
    activation: Optional[DateRange]
    trigger: Optional[DateRange]
    peak: Optional[DateRange]
    fading: Optional[DateRange]
    confidence: float
    reasons: tuple[str, ...] = field(default=())


def _graha(period: Period) -> str:
    """`Period.lord` is capitalised ("Saturn"); registry symbols are not.

    Worth its own function rather than a `.lower()` at four call sites: the
    mismatch is invisible until `ChartState.planet` raises, and it would have
    read as "this chart activates nothing" if that lookup returned None.
    """
    return f"graha.{period.lord.lower()}"


def _overlaps(period: Period, start: datetime, end: datetime) -> bool:
    return period.end >= start and period.start <= end


def _clip(period: Period, start: datetime, end: datetime) -> DateRange:
    """A period as it falls inside the horizon.

    Clipped rather than reported whole: a mahadasha that began in 2011 is not a
    window a user asking about the next decade can act on.
    """
    return DateRange(start=max(period.start, start), end=min(period.end, end))


def event_window(
    chart: Chart,
    state: ChartState,
    domain: str,
    *,
    start: datetime,
    end: datetime,
    promise: bool,
) -> EventWindow:
    """The five stages, or an honest account of why there are none.

    `promise` is supplied by the caller rather than decided here - it comes from
    the Koonji reading, where a natal promise is a fired rule with a citation.
    This module times a promise; it does not adjudicate one.
    """
    if not promise:
        return EventWindow(
            promise=False, promise_basis=(), activation=None, trigger=None,
            peak=None, fading=None, confidence=0.0,
            reasons=(
                f"The chart carries no promise for {domain.removeprefix('domain.')}, "
                f"so there is no window to give. A period would be arithmetic, "
                f"not a prediction.",
            ),
        )

    reasons: list[str] = []

    maha = next(
        (p for p in mahadasha_timeline(chart)
         if _overlaps(p, start, end)
         and activates_domain(state, _graha(p), domain)),
        None,
    )
    if maha is None:
        return EventWindow(
            promise=True, promise_basis=(), activation=None, trigger=None,
            peak=None, fading=None, confidence=0.0,
            reasons=(
                f"The promise is present, but no mahadasha between "
                f"{start:%b %Y} and {end:%b %Y} activates "
                f"{domain.removeprefix('domain.')}. Stretching a period to fit "
                f"would be inventing the timing.",
            ),
        )

    activation = _clip(maha, start, end)
    houses = domain_overlap(state, _graha(maha), domain)
    reasons.append(
        f"{maha.lord} mahadasha activates "
        f"{', '.join(f'the {h}th' for h in houses)} — {activation}."
    )

    trigger_period = next(
        (p for p in sub_periods(maha, "antar")
         if _overlaps(p, start, end)
         and activates_domain(state, _graha(p), domain)),
        None,
    )
    if trigger_period is None:
        return EventWindow(
            promise=True, promise_basis=(), activation=activation, trigger=None,
            peak=None, fading=None, confidence=0.35,
            reasons=tuple(reasons + [
                "No antardasha inside it narrows the window further, so this "
                "stays a period rather than a date."
            ]),
        )

    trigger = _clip(trigger_period, activation.start, activation.end)
    reasons.append(f"{trigger_period.lord} antardasha sharpens it — {trigger}.")

    # Filtered by the CLIPPED trigger, not merely by membership in the
    # antardasha. The first activating pratyantar can sit entirely before the
    # horizon opens - the antardasha may have begun years earlier - and clipping
    # it then produced a window running backwards. `DateRange` refused it, which
    # is what that guard is for.
    peak_period = next(
        (p for p in sub_periods(trigger_period, "pratyantar")
         if _overlaps(p, trigger.start, trigger.end)
         and activates_domain(state, _graha(p), domain)),
        None,
    )
    peak = _clip(peak_period, trigger.start, trigger.end) if peak_period else None
    if peak:
        reasons.append(f"{peak_period.lord} pratyantar is the sharpest of it — {peak}.")

    fading = (
        DateRange(start=trigger.end, end=activation.end)
        if trigger.end < activation.end else None
    )
    if fading:
        reasons.append(f"The activation runs on afterwards, fading — {fading}.")

    # Three levels agreeing is the strongest this module claims on its own. The
    # evidence graph, not the calendar, is what raises it further.
    confidence = 0.45 + (0.15 if peak else 0.0)

    return EventWindow(
        promise=True,
        promise_basis=(),
        activation=activation,
        trigger=trigger,
        peak=peak,
        fading=fading,
        confidence=round(confidence, 2),
        reasons=tuple(reasons),
    )
