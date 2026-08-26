"""promise → activation → trigger → peak → fading.

The single most important assertion in this file is that `promise=False`
short-circuits everything. A timing question about an event the chart does not
promise has no answer worth computing, and producing a window anyway is the most
common way an astrology product invents a prediction. It is a hard gate, not a
low score.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chartstate.build import build_chart_state
from rishivan.timing.windows import DateRange, EventWindow, event_window

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)
HORIZON = datetime(2036, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


@pytest.fixture(scope="module")
def state(chart):
    return build_chart_state(chart, when=WHEN)


class TestThePromiseGate:
    def test_no_promise_means_no_windows_at_all(self, chart, state):
        """The gate. Every stage is None, not merely low-confidence."""
        w = event_window(chart, state, "domain.career",
                         start=WHEN, end=HORIZON, promise=False)
        assert w.promise is False
        assert w.activation is None
        assert w.trigger is None
        assert w.peak is None
        assert w.fading is None

    def test_no_promise_means_zero_confidence(self, chart, state):
        w = event_window(chart, state, "domain.career",
                         start=WHEN, end=HORIZON, promise=False)
        assert w.confidence == 0.0

    def test_no_promise_still_explains_itself(self, chart, state):
        """"The chart does not promise this" is the answer, and it has to be
        sayable."""
        w = event_window(chart, state, "domain.career",
                         start=WHEN, end=HORIZON, promise=False)
        assert w.reasons
        assert any("promise" in r.lower() for r in w.reasons)

    def test_a_promise_with_no_activating_period_yields_no_window(self, chart, state):
        """A promise the horizon never activates is honest silence, not a
        window stretched to fit."""
        w = event_window(chart, state, "domain.gardening",
                         start=WHEN, end=HORIZON, promise=True)
        assert w.promise is True
        assert w.activation is None


@pytest.fixture(scope="module")
def window(chart, state):
    return event_window(chart, state, "domain.career",
                        start=WHEN, end=HORIZON, promise=True)


class TestTheStages:

    def test_an_activation_window_is_found(self, window):
        assert window.activation is not None

    def test_the_trigger_sits_inside_the_activation(self, window):
        if window.trigger:
            assert window.activation.start <= window.trigger.start
            assert window.trigger.end <= window.activation.end

    def test_the_peak_sits_inside_the_trigger(self, window):
        if window.peak and window.trigger:
            assert window.trigger.start <= window.peak.start
            assert window.peak.end <= window.trigger.end

    def test_fading_follows_the_trigger(self, window):
        if window.fading and window.trigger:
            assert window.fading.start >= window.trigger.end

    def test_fading_stays_inside_the_activation(self, window):
        if window.fading:
            assert window.fading.end <= window.activation.end

    def test_every_stage_carries_a_reason(self, window):
        assert window.reasons
        assert len(window.reasons) >= 2

    def test_confidence_is_bounded(self, window):
        assert 0.0 <= window.confidence <= 1.0


class TestHorizon:
    def test_nothing_is_reported_outside_the_horizon(self, chart, state):
        w = event_window(chart, state, "domain.career",
                         start=WHEN, end=HORIZON, promise=True)
        if w.activation:
            assert w.activation.end >= WHEN
            assert w.activation.start <= HORIZON

    def test_a_narrow_horizon_may_find_nothing_and_says_so(self, chart, state):
        narrow = event_window(chart, state, "domain.career", start=WHEN,
                              end=datetime(2026, 8, 26), promise=True)
        if narrow.activation is None:
            assert narrow.reasons


class TestDateRange:
    def test_a_range_knows_its_span(self):
        r = DateRange(start=datetime(2026, 1, 1), end=datetime(2027, 1, 1))
        assert 360 <= r.days <= 370

    def test_a_range_rejects_an_inverted_span(self):
        """An end before a start is a bug upstream, and silently swapping them
        hides it."""
        with pytest.raises(ValueError):
            DateRange(start=datetime(2027, 1, 1), end=datetime(2026, 1, 1))

    def test_a_range_renders_for_a_reader(self):
        r = DateRange(start=datetime(2026, 4, 1), end=datetime(2028, 1, 31))
        assert "2026" in str(r) and "2028" in str(r)


class TestDeterminism:
    def test_the_same_inputs_give_the_same_window(self, chart, state):
        a = event_window(chart, state, "domain.career", start=WHEN, end=HORIZON, promise=True)
        b = event_window(chart, state, "domain.career", start=WHEN, end=HORIZON, promise=True)
        assert a == b

    def test_the_window_is_frozen(self, chart, state):
        w = event_window(chart, state, "domain.career", start=WHEN, end=HORIZON, promise=True)
        with pytest.raises(Exception):
            w.confidence = 0.9
