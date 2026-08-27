"""One table, frame as a column.

The reading that prompted this named Saturn in Pisces, Venus in Virgo, Mercury in
Leo, Moon conjunct Rahu in Aquarius and Jupiter in Cancer — every one of them a
TRANSIT position for that date, none of them natal. A natal chart matching the
sky on five planets would mean the seeker was born that day.

The cause was shape rather than disobedience. Five blocks carried planetary
positions and exactly one of them — the transit block — put planet, sign and
"which house of yours" on a single line. `PLANETARY CONDITION` carried dignity
with no sign and no house, so using it meant re-joining across blocks on planet
name. The most usable shape won, over an instruction four hundred characters
away that said the other block was authoritative.

So: one table. Frame is a column. Every row is complete enough to use without
looking anywhere else.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.transit import chart_for_moment
from rishivan.chartstate.build import build_chart_state
from rishivan.council.fact_table import (
    natal_rows, render_table, transit_rows,
)

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


@pytest.fixture(scope="module")
def chart_state(chart):
    return build_chart_state(chart, when=WHEN)


@pytest.fixture(scope="module")
def transiting():
    return chart_for_moment(WHEN, lat=28.6139, lon=77.2090, tz_offset=5.5)


class TestNatalRows:
    def test_every_graha_gets_a_row(self, chart, chart_state):
        rows = natal_rows(chart, chart_state)
        assert {r.planet for r in rows} == {
            "Sun", "Moon", "Mars", "Mercury", "Jupiter",
            "Venus", "Saturn", "Rahu", "Ketu",
        }

    def test_the_frame_is_natal(self, chart, chart_state):
        assert {r.frame for r in natal_rows(chart, chart_state)} == {"natal"}

    def test_a_row_carries_sign_house_dignity_and_strength_together(
        self, chart, chart_state
    ):
        """The whole point. A row that needs a second block to be usable is a row
        that will be joined to the wrong one."""
        saturn = next(r for r in natal_rows(chart, chart_state) if r.planet == "Saturn")
        assert saturn.sign
        assert saturn.house
        assert saturn.dignity
        assert saturn.strength

    def test_conditions_survive_as_flags(self, chart, chart_state):
        rows = natal_rows(chart, chart_state)
        flags = {f for r in rows for f in r.flags}
        assert "combust" in flags or "retrograde" in flags

    def test_it_degrades_without_a_diagnosis(self, chart):
        """Placements still render; the judgement columns are simply blank."""
        rows = natal_rows(chart, None)
        assert len(rows) == 9
        assert all(r.sign and r.house for r in rows)
        assert all(not r.dignity for r in rows)


class TestTransitRows:
    def test_houses_are_counted_from_the_natal_lagna(self, chart, transiting):
        """A transiting sign says nothing; which of THIS chart's houses it crosses
        is the entire content."""
        rows = transit_rows(chart, transiting)
        saturn = next(r for r in rows if r.planet == "Saturn")
        assert saturn.sign == "Pisces"
        assert saturn.house == 1  # Aquarius lagna on the test chart

    def test_the_frame_is_transit(self, chart, transiting):
        assert {r.frame for r in transit_rows(chart, transiting)} == {"transit"}

    def test_transit_rows_carry_no_natal_judgement(self, chart, transiting):
        """Dignity and strength are natal readings. Printing them beside a transit
        sign is precisely the fusion this table exists to prevent — it is how
        "Venus debilitated in Virgo" came to be written about a chart whose natal
        Venus is exalted in Pisces."""
        for row in transit_rows(chart, transiting):
            assert not row.dignity
            assert not row.strength

    def test_retrogression_still_shows(self, chart, transiting):
        rows = transit_rows(chart, transiting)
        saturn = next(r for r in rows if r.planet == "Saturn")
        assert "retrograde" in saturn.flags

    def test_only_the_slow_movers_are_included(self, chart, transiting):
        """The Moon changes sign every 2.25 days. A transiting Moon presented
        beside a natal chart is what produced an invented "Moon conjunct Rahu"
        conjunction."""
        planets = {r.planet for r in transit_rows(chart, transiting)}
        assert planets == {"Jupiter", "Saturn", "Rahu", "Ketu"}


class TestRenderTable:
    def test_both_frames_appear_in_one_table(self, chart, chart_state, transiting):
        rows = natal_rows(chart, chart_state) + transit_rows(chart, transiting)
        text = render_table(rows, primary=set())
        # One header row means one table. "FRAME" also appears in the preamble,
        # so count the header itself rather than the word.
        assert len([ln for ln in text.splitlines() if "PLANET" in ln]) == 1
        assert "natal" in text
        assert "transit" in text

    def test_there_are_no_per_frame_headings(self, chart, chart_state, transiting):
        """A heading is a section, and a section is a block, and blocks are what
        fused. The frame is data, not structure."""
        rows = natal_rows(chart, chart_state) + transit_rows(chart, transiting)
        text = render_table(rows, primary=set())
        for banned in ("CHART FRAMEWORK", "PRIMARY EVIDENCE", "WIDER CHART",
                       "PLANETARY CONDITION", "TRANSITS NOW"):
            assert banned not in text

    def test_the_same_planet_in_two_frames_is_unambiguous(
        self, chart, chart_state, transiting
    ):
        """Saturn appears twice. A reader — human or model — must be able to tell
        which is which from the row alone."""
        rows = natal_rows(chart, chart_state) + transit_rows(chart, transiting)
        text = render_table(rows, primary=set())
        # Saturn also appears inside other planets' "aspected by" notes, so match
        # on the PLANET column rather than anywhere in the line.
        saturn_lines = [
            ln for ln in text.splitlines()
            if len(ln.split()) > 1 and ln.split()[1] == "Saturn"
        ]
        assert len(saturn_lines) == 2
        assert sum("natal" in ln for ln in saturn_lines) == 1
        assert sum("transit" in ln for ln in saturn_lines) == 1

    def test_primary_planets_are_marked_not_relocated(
        self, chart, chart_state, transiting
    ):
        rows = natal_rows(chart, chart_state) + transit_rows(chart, transiting)
        text = render_table(rows, primary={"Venus", "Jupiter"})
        marked = [ln for ln in text.splitlines() if ln.startswith("*")]
        assert marked
        assert all(("Venus" in ln or "Jupiter" in ln) for ln in marked)

    def test_the_marker_is_explained(self, chart, chart_state):
        text = render_table(natal_rows(chart, chart_state), primary={"Venus"})
        assert "*" in text
        assert "bear" in text.lower() or "question" in text.lower()

    def test_an_empty_row_list_renders_nothing(self):
        assert render_table([], primary=set()) == ""
