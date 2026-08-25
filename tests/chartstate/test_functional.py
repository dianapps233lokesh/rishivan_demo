"""Functional benefic/malefic under a named lagna framework.

The doctrine, stated once so the tests can be read against it:

  * kendras are 1/4/7/10, trikonas 1/5/9, dusthanas 6/8/12
  * lordship of a trikona is benefic; of 3/6/11 malefic
  * a NATURAL benefic owning a kendra is blemished by it (kendradhipatya);
    a natural malefic owning one is not
  * owning both a kendra and a trikona makes a planet yogakaraka
  * Rahu and Ketu own no sign, so they take the nature of their dispositor's
    functional verdict rather than a lordship of their own

Every verdict carries its reason. A functional malefic with no stated reason is
an assertion; with one it is an argument a reviewer can disagree with.
"""

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chartstate.functional import (
    FRAMEWORKS,
    KENDRAS,
    TRIKONAS,
    functional_natures,
    functional_nature_of,
)

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


class TestTheFrameworkIsNamed:
    def test_parashari_is_available(self):
        assert "parashari" in FRAMEWORKS

    def test_an_unknown_framework_raises_rather_than_defaulting(self):
        """A silent default would make two incompatible lineages look like one
        disagreement about a chart."""
        with pytest.raises(KeyError, match="framework"):
            functional_natures(None, framework="lal_kitab")

    def test_the_houses_match_the_classical_sets(self):
        assert KENDRAS == (1, 4, 7, 10)
        assert TRIKONAS == (1, 5, 9)


class TestVerdicts:
    def test_every_graha_gets_a_verdict(self, chart):
        verdicts = functional_natures(chart)
        assert len(verdicts) == len(chart.planets)

    def test_every_verdict_carries_a_reason(self, chart):
        for v in functional_natures(chart).values():
            assert v.reason.strip(), v

    def test_a_verdict_is_one_of_three_words(self, chart):
        for v in functional_natures(chart).values():
            assert v.nature in ("benefic", "malefic", "neutral")

    def test_the_lagna_lord_is_benefic(self, chart):
        """The 1st is both a kendra and a trikona, and its lord is universally
        held benefic for the chart."""
        lord = chart.house_lords[1]
        v = functional_nature_of(chart, f"graha.{lord.lower()}")
        assert v.nature == "benefic"

    def test_a_trikona_lord_is_benefic(self, chart):
        for house in (5, 9):
            lord = chart.house_lords[house]
            v = functional_nature_of(chart, f"graha.{lord.lower()}")
            if v.nature != "benefic":
                # Only acceptable if the same planet also owns 3/6/11.
                assert any(h in (3, 6, 11) for h in v.lordships), v

    def test_a_sixth_lord_is_not_benefic(self, chart):
        lord = chart.house_lords[6]
        v = functional_nature_of(chart, f"graha.{lord.lower()}")
        assert v.nature != "benefic" or 1 in v.lordships or 5 in v.lordships \
            or 9 in v.lordships


class TestYogakaraka:
    def test_owning_a_kendra_and_a_trikona_is_yogakaraka(self, chart):
        for v in functional_natures(chart).values():
            kendra = [h for h in v.lordships if h in KENDRAS and h != 1]
            trikona = [h for h in v.lordships if h in TRIKONAS and h != 1]
            if kendra and trikona:
                assert v.yogakaraka, v
                assert v.nature == "benefic"

    def test_a_yogakaraka_says_so_in_its_reason(self, chart):
        for v in functional_natures(chart).values():
            if v.yogakaraka:
                assert "yogakaraka" in v.reason.lower()
                return

    def test_the_lagna_lordship_alone_is_not_yogakaraka(self, chart):
        """The 1st counts as both, which would make every lagna lord a
        yogakaraka — the doctrine means two DIFFERENT houses."""
        for v in functional_natures(chart).values():
            if v.lordships == (1,):
                assert not v.yogakaraka


class TestKendradhipatya:
    def test_a_natural_benefic_owning_a_kendra_is_blemished(self, chart):
        """The subtlety of the doctrine: a kendra blemishes a natural benefic
        and does nothing to a natural malefic."""
        for v in functional_natures(chart).values():
            if v.kendradhipatya_dosha:
                assert v.natural_nature == "benefic"

    def test_a_natural_malefic_owning_a_kendra_is_not_blemished(self, chart):
        for v in functional_natures(chart).values():
            if v.natural_nature == "malefic":
                assert not v.kendradhipatya_dosha


class TestNodes:
    def test_the_nodes_own_no_house(self, chart):
        for node in ("graha.rahu", "graha.ketu"):
            assert functional_nature_of(chart, node).lordships == ()

    def test_a_node_takes_its_verdict_from_its_dispositor(self, chart):
        """They own no sign, so there is no lordship to judge them by. The
        classical answer is the dispositor's, and the reason says so."""
        v = functional_nature_of(chart, "graha.rahu")
        assert "dispositor" in v.reason.lower()


class TestDeterminism:
    def test_the_same_chart_gives_the_same_verdicts(self, chart):
        assert functional_natures(chart) == functional_natures(chart)


class TestVocabulary:
    def test_the_natures_match_the_koonji_registry(self):
        """`natural_nature` and `functional_nature` are registry predicates
        taking a `nature` argument. A word spelled differently here is a word no
        rule can match."""
        from rishivan.koonji.registry import NATURES

        assert {"benefic", "malefic", "neutral"} <= set(NATURES)
