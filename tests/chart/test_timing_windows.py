"""Which upcoming periods can actually carry this question's event.

The failure this closes, in full. A Scorpio-lagna chart was asked "when will I
get married". Venus rules its 7th. The prompt printed, verbatim:

    - Venus: 2027-08-03 to 2028-01-23 [future]

the Venus pratyantardasha inside the running Saturn antardasha. The model walked
past it and named the Rahu/VENUS ANTARDASHA in 2033 instead - the same lord, six
years further out, because it was the bigger period. A competing product read
the same chart and answered "August 2027 to January 2028".

Nothing was miscomputed. The model was handed a search it had no rule for, so
this computes the candidates and ranks them.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.timing_windows import candidate_windows, significators_for

PUNIT = BirthData(
    year=2004, month=2, day=10, hour=2, minute=15,
    tz_offset_hours=5.5, lat=26.9155, lon=75.8190, place="Jaipur",
)
NOW = datetime(2026, 8, 30)


@pytest.fixture
def chart():
    return compute_chart(PUNIT)


class TestSignificators:
    def test_marriage_rests_on_the_seventh_lord_and_the_karaka(self, chart):
        """`prema` names Venus and Jupiter; the 7th lord is whichever graha the
        lagna assigned. For Scorpio that is Venus, so the two coincide - which
        is exactly why the model found a Venus period and then chose the wrong
        one."""
        lords = significators_for(chart, "domain.relationship")
        assert lords["Venus"][1] == "primary"
        assert "7th lord" in lords["Venus"][0]

    def test_career_rests_on_a_different_set(self, chart):
        assert set(significators_for(chart, "domain.career")) != set(
            significators_for(chart, "domain.relationship")
        )

    def test_the_supporting_houses_are_not_ignored(self, chart):
        """The bug this closes. `karma` declares supporting_houses = [1,2,6,11]
        and this function read only `primary_houses`, so "when will I get a job"
        searched the 10th lord alone and answered January 2028. The 11th lord
        ruled a window fourteen months earlier, and in Vedic terms the 6th house
        IS employment and the 11th is where income arrives."""
        lords = significators_for(chart, "domain.career")
        assert lords["Sun"] == ("10th lord", "primary")
        assert lords["Mercury"][1] == "supporting"
        assert "11th lord" in lords["Mercury"][0]
        assert "6th lord" in lords["Mars"][0]

    def test_a_graha_that_rules_both_stays_primary(self, chart):
        """A lord counted twice would be ranked by whichever loop ran last."""
        for why, tier in significators_for(chart, "domain.career").values():
            assert tier in ("primary", "supporting")
        primaries = [
            lord for lord, (_why, tier)
            in significators_for(chart, "domain.career").items()
            if tier == "primary"
        ]
        assert primaries == ["Sun"]


class TestCandidates:
    def test_the_window_the_reading_missed_is_found(self, chart):
        """The whole point. Aug 2027 - Jan 2028, the Venus pratyantardasha."""
        found = candidate_windows(chart, "domain.relationship", NOW)
        matched = [
            w for w in found
            if w.start.strftime("%Y-%m-%d") == "2027-08-03"
            and w.level == "pratyantar"
        ]
        assert matched, [str(w.start.date()) for w in found[:6]]
        assert matched[0].lord == "Venus"

    def test_it_is_ranked_ahead_of_the_same_lords_antardasha_years_later(self, chart):
        """Nearest first, and that ordering IS the fix. Both windows are ruled by
        the 7th lord; one is a year away and one is six. A seeker asking "when"
        wants the next real opportunity, not the largest one in the timeline."""
        found = candidate_windows(chart, "domain.relationship", NOW)
        starts = [w.start.strftime("%Y-%m-%d") for w in found]
        assert starts.index("2027-08-03") < starts.index("2033-01-06")

    def test_both_levels_are_offered(self, chart):
        found = candidate_windows(chart, "domain.relationship", NOW)
        assert {w.level for w in found} >= {"antar", "pratyantar"}

    def test_nothing_in_the_past_is_offered(self, chart):
        for window in candidate_windows(chart, "domain.relationship", NOW):
            assert window.end > NOW

    def test_every_window_says_which_significator_rules_it(self, chart):
        for window in candidate_windows(chart, "domain.relationship", NOW):
            assert window.lord
            assert window.because
            assert window.tier in ("primary", "supporting")

    def test_the_career_window_a_narrow_search_missed_is_found(self, chart):
        """Rahu/Saturn/Mercury, Jan-Jun 2027 - the 11th lord's pratyantardasha.
        Searching the 10th lord alone put the answer in January 2028."""
        found = candidate_windows(chart, "domain.career", NOW)
        assert found[0].start.strftime("%Y-%m-%d") == "2027-01-07"
        assert found[0].lord == "Mercury"
        assert found[0].tier == "supporting"

    def test_the_primary_lord_window_is_still_offered_and_marked(self, chart):
        found = candidate_windows(chart, "domain.career", NOW)
        sun = next(w for w in found if w.lord == "Sun")
        assert sun.tier == "primary"
        assert sun.start.strftime("%Y-%m-%d") == "2028-01-23"

    def test_the_horizon_is_respected(self, chart):
        found = candidate_windows(chart, "domain.relationship", NOW, years=5)
        assert found
        for window in found:
            assert window.start.year <= NOW.year + 5

    def test_a_chart_whose_significator_never_rules_returns_nothing(self, chart):
        """Empty is an answer: it means no upcoming period is ruled by anything
        that carries this question, and the reading should say the window is
        beyond the horizon rather than inventing a nearer one."""
        assert candidate_windows(chart, "domain.relationship", NOW, years=0) == ()
