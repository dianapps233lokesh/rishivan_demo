"""Chara karakas and the arudha padas — the two things `prema`'s protocol step 5
has always named and nothing has ever computed."""

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.jaimini import (
    KARAKA_ORDER, arudha_of, chara_karakas, upapada_lagna,
)

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.fixture
def chart():
    return compute_chart(BIRTH)


class TestCharaKarakas:
    def test_all_seven_are_assigned(self, chart):
        karakas = chara_karakas(chart)
        assert set(karakas) == set(KARAKA_ORDER)

    def test_each_karaka_names_exactly_one_graha(self, chart):
        karakas = chara_karakas(chart)
        assert len(set(karakas.values())) == 7

    def test_the_nodes_are_excluded(self, chart):
        """The seven-karaka Parashari scheme. Rahu enters only in the eight-karaka
        scheme and with its degree reversed, and mixing the two silently shifts
        every karaka below it by one."""
        assert "Rahu" not in chara_karakas(chart).values()
        assert "Ketu" not in chara_karakas(chart).values()

    def test_atmakaraka_holds_the_highest_degree(self, chart):
        karakas = chara_karakas(chart)
        atma = chart.planets[karakas["atma"]]
        for name in karakas.values():
            assert chart.planets[name].degree_in_rashi <= atma.degree_in_rashi

    def test_darakaraka_holds_the_lowest_degree(self, chart):
        """The spouse significator, and the reason any of this is here."""
        karakas = chara_karakas(chart)
        dara = chart.planets[karakas["dara"]]
        for name in karakas.values():
            assert chart.planets[name].degree_in_rashi >= dara.degree_in_rashi

    def test_the_order_runs_highest_to_lowest(self, chart):
        karakas = chara_karakas(chart)
        degrees = [chart.planets[karakas[k]].degree_in_rashi for k in KARAKA_ORDER]
        assert degrees == sorted(degrees, reverse=True)


class TestArudha:
    def test_the_arudha_is_the_same_distance_again(self):
        """Count from the house to its lord, then as far again from the lord.
        Aries ruled by a planet in Gemini — 3rd — puts the pada in Leo, the 3rd
        from Gemini and the 5th from Aries."""
        assert arudha_of(house_sign=0, lord_sign=2) == 4

    def test_it_wraps_the_zodiac(self):
        """Aquarius ruled by a planet in Aries: 3rd from Aquarius, so 3rd again
        lands on Gemini."""
        assert arudha_of(house_sign=10, lord_sign=0) == 2

    def test_a_lord_in_its_own_house_throws_to_the_tenth(self):
        """The classical exception. An arudha falling on the house itself or the
        7th from it is discarded and the 10th from it taken instead — otherwise
        the pada collapses onto the house it came from and carries nothing."""
        assert arudha_of(house_sign=0, lord_sign=0) == 9

    def test_a_lord_in_the_fourth_throws_to_the_tenth(self):
        """A lord in the 4th ALWAYS lands the pada on the 7th, so this exception
        is the common case rather than a corner. Aries/Cancer -> Libra, which is
        the 7th from Aries, so the 10th from Libra is taken: Cancer."""
        assert arudha_of(house_sign=0, lord_sign=3) == 3

    def test_a_lord_in_the_seventh_throws_to_the_tenth(self):
        """And a lord in the 7th always lands it back on the 1st."""
        assert arudha_of(house_sign=0, lord_sign=6) == 9

    def test_upapada_is_the_arudha_of_the_twelfth(self, chart):
        upapada = upapada_lagna(chart)
        assert upapada is not None
        assert 0 <= upapada["sign_index"] <= 11
        assert upapada["sign"]
        assert 1 <= upapada["house_from_lagna"] <= 12
