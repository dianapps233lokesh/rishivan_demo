"""Mangal dosha — the first thing any classical marriage reading checks, and the
one the direct lane has never once mentioned."""

import pytest

from rishivan.chart.dosha import KUJA_HOUSES, kuja_dosha
from rishivan.chart.ephemeris import BirthData, compute_chart

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.fixture
def chart():
    return compute_chart(BIRTH)


class TestKujaDosha:
    def test_it_checks_all_three_reference_points(self, chart):
        """From the lagna, from the Moon and from Venus. A chart clear from the
        lagna and afflicted from the Moon is the common case, and checking only
        the first is how a reading declares a marriage unobstructed when the
        tradition would not."""
        result = kuja_dosha(chart)
        assert set(result["from"]) == {"lagna", "moon", "venus"}

    def test_each_reference_point_reports_the_house_mars_occupies(self, chart):
        for entry in kuja_dosha(chart)["from"].values():
            assert 1 <= entry["house"] <= 12
            assert entry["afflicted"] is (entry["house"] in KUJA_HOUSES)

    def test_the_verdict_is_true_when_any_reference_point_is_afflicted(self, chart):
        result = kuja_dosha(chart)
        assert result["present"] == any(
            e["afflicted"] for e in result["from"].values()
        )

    def test_it_names_the_convention_it_used(self, chart):
        """Traditions differ on whether the 2nd counts. A dosha verdict that does
        not say which set of houses it used is a verdict nobody can check."""
        assert kuja_dosha(chart)["houses"] == KUJA_HOUSES
        assert kuja_dosha(chart)["convention"]

    def test_no_mars_means_no_verdict_rather_than_a_clear_one(self):
        """Absence of evidence. A chart with no Mars is a broken chart, and
        reporting it as free of dosha would be a false clearance."""
        class _Chart:
            planets = {}
            lagna_rashi_index = 0
        assert kuja_dosha(_Chart()) is None
