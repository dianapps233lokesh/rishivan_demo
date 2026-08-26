"""Periods and windows at an arbitrary moment.

Blueprint §8: "Support arbitrary date-time queries." Which mostly means: never
read the clock inside a computation, because a backtest and a Prashna cast for a
stated moment both need to ask about a time that is not now.

The other half is `TimingReport`, which keeps dasha systems apart. Averaging two
systems produces a number no tradition endorses and no reviewer can check.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chartstate.build import build_chart_state
from rishivan.timing.query import TimingReport, periods_at, windows_between

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


class TestPeriodsAt:
    def test_it_answers_for_a_stated_moment(self, chart):
        periods = periods_at(chart, WHEN)
        assert periods["maha"] is not None
        assert periods["maha"].contains(WHEN)

    def test_it_answers_for_the_past(self, chart):
        """A backtest asks about 1998, and the engine must not quietly answer
        about today."""
        past = periods_at(chart, datetime(1998, 6, 1))
        now = periods_at(chart, WHEN)
        assert past["maha"].lord != now["maha"].lord or past["antar"] != now["antar"]

    def test_it_returns_every_level(self, chart):
        from rishivan.chart.dasha import DASHA_LEVELS

        assert set(periods_at(chart, WHEN)) == set(DASHA_LEVELS)

    def test_levels_nest(self, chart):
        periods = periods_at(chart, WHEN)
        maha, antar = periods["maha"], periods["antar"]
        assert maha.start <= antar.start and antar.end <= maha.end

    def test_it_never_reads_the_clock(self, chart):
        """Two calls a moment apart must agree, or nothing built on this is
        reproducible."""
        assert periods_at(chart, WHEN) == periods_at(chart, WHEN)


class TestWindowsBetween:
    def test_it_produces_a_window_for_a_promised_domain(self, chart, state):
        w = windows_between(chart, state, "domain.career", WHEN, HORIZON, promise=True)
        assert w.promise is True

    def test_an_unpromised_domain_gets_nothing(self, chart, state):
        w = windows_between(chart, state, "domain.career", WHEN, HORIZON, promise=False)
        assert w.activation is None

    def test_an_inverted_horizon_raises_rather_than_swapping(self, chart, state):
        """Silently swapping hides a caller bug that would otherwise surface
        here rather than three layers downstream."""
        with pytest.raises(ValueError):
            windows_between(chart, state, "domain.career", HORIZON, WHEN, promise=True)


class TestCaching:
    def test_repeat_queries_agree(self, chart):
        """Cached on (digest, when), so a Rishi asking twice gets one answer."""
        assert periods_at(chart, WHEN) == periods_at(chart, WHEN)

    def test_a_different_chart_is_not_served_a_cached_answer(self, chart):
        other = compute_chart(BirthData(
            year=1985, month=6, day=15, hour=4, minute=30,
            tz_offset_hours=5.5, lat=19.0760, lon=72.8777,
        ))
        assert periods_at(chart, WHEN)["maha"].lord != periods_at(other, WHEN)["maha"].lord \
            or periods_at(chart, WHEN)["maha"].start != periods_at(other, WHEN)["maha"].start


class TestTimingReport:
    def test_systems_are_kept_apart(self, chart, state):
        """Chara Dasha, when it arrives, is a second opinion under its own key —
        not an average."""
        w = windows_between(chart, state, "domain.career", WHEN, HORIZON, promise=True)
        report = TimingReport(by_system={"vimshottari": w})
        assert set(report.by_system) == {"vimshottari"}

    def test_the_primary_system_is_named(self, chart, state):
        w = windows_between(chart, state, "domain.career", WHEN, HORIZON, promise=True)
        report = TimingReport(by_system={"vimshottari": w})
        assert report.primary == "vimshottari"

    def test_it_reports_agreement_rather_than_blending_it(self, chart, state):
        """Two systems agreeing is evidence; two systems averaged is a number
        nobody can check."""
        w = windows_between(chart, state, "domain.career", WHEN, HORIZON, promise=True)
        report = TimingReport(by_system={"vimshottari": w, "chara": w})
        assert report.agreement() == 1.0

    def test_disagreement_is_visible(self, chart, state):
        promised = windows_between(chart, state, "domain.career", WHEN, HORIZON, promise=True)
        silent = windows_between(chart, state, "domain.career", WHEN, HORIZON, promise=False)
        report = TimingReport(by_system={"vimshottari": promised, "chara": silent})
        assert report.agreement() < 1.0

    def test_a_single_system_has_nothing_to_agree_with(self, chart, state):
        w = windows_between(chart, state, "domain.career", WHEN, HORIZON, promise=True)
        assert TimingReport(by_system={"vimshottari": w}).agreement() is None

    def test_an_empty_report_names_no_primary(self):
        assert TimingReport(by_system={}).primary is None
