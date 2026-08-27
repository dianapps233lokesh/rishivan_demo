"""Tara bala and chandra bala.

`facts.py` has carried a comment noting these were missing since before the
direct lane existed. They are what a "should I do this on Tuesday" question is
actually judged on, and their absence is why "Can I travel foreign tomorrow?"
was answered with dasha boundaries running to 2060 — the reading used the facts
it had rather than the ones the question needed.

Both are index arithmetic over lists this repo already holds.
"""

import pytest

from rishivan.astro.constants import NAKSHATRAS
from rishivan.chart.bala import (
    TARA_NAMES, chandra_bala, tara_bala,
)

NAMES = [n.name for n in NAKSHATRAS]


class TestTaraBala:
    def test_the_birth_nakshatra_itself_is_janma_and_unfavourable(self):
        """Counting is inclusive: the janma nakshatra is the first tara, not the
        zeroth. Off-by-one here shifts every verdict by one house."""
        tara = tara_bala("Bharani", "Bharani")
        assert tara.number == 1
        assert tara.name == "Janma"
        assert tara.is_favourable is False

    def test_the_next_nakshatra_is_sampat_and_favourable(self):
        tara = tara_bala("Bharani", "Krittika")
        assert tara.number == 2
        assert tara.name == "Sampat"
        assert tara.is_favourable is True

    def test_the_cycle_of_nine_repeats_three_times_across_twenty_seven(self):
        """Ninth from janma is Ati-Mitra; tenth is Janma again. A tara table that
        ran 1..27 rather than 1..9 would call the tenth nakshatra favourable."""
        assert tara_bala(NAMES[0], NAMES[8]).name == "Ati-Mitra"
        assert tara_bala(NAMES[0], NAMES[9]).name == "Janma"
        assert tara_bala(NAMES[0], NAMES[18]).name == "Janma"

    def test_it_wraps_past_the_end_of_the_list(self):
        """Birth in Revati, transit in Ashwini: one forward, not twenty-six back."""
        assert tara_bala("Revati", "Ashwini").number == 2

    def test_all_nine_taras_are_reachable_and_named(self):
        seen = {tara_bala(NAMES[0], name).name for name in NAMES}
        assert seen == set(TARA_NAMES)

    def test_the_four_unfavourable_taras_are_the_traditional_ones(self):
        """Janma, Vipat, Pratyari, Vadha. Getting this set wrong inverts the
        advice on more than a third of all dates."""
        unfavourable = {
            tara_bala(NAMES[0], NAMES[i]).name for i in range(9)
            if not tara_bala(NAMES[0], NAMES[i]).is_favourable
        }
        assert unfavourable == {"Janma", "Vipat", "Pratyari", "Vadha"}

    def test_an_unknown_nakshatra_returns_none_rather_than_guessing(self):
        assert tara_bala("Nonsense", "Bharani") is None
        assert tara_bala("Bharani", "Nonsense") is None


class TestChandraBala:
    def test_the_moon_over_its_own_natal_sign_is_the_first_house(self):
        bala = chandra_bala("Aquarius", "Aquarius")
        assert bala.house == 1
        assert bala.verdict == "favourable"

    def test_the_traditionally_strong_houses_are_favourable(self):
        signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
                 "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius",
                 "Pisces"]
        for house in (1, 3, 6, 7, 10, 11):
            transit = signs[(0 + house - 1) % 12]
            assert chandra_bala("Aries", transit).verdict == "favourable", house

    def test_the_dusthana_houses_are_unfavourable(self):
        signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
                 "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius",
                 "Pisces"]
        for house in (4, 8, 12):
            transit = signs[(0 + house - 1) % 12]
            assert chandra_bala("Aries", transit).verdict == "unfavourable", house

    def test_the_contested_houses_are_reported_middling_not_forced(self):
        """2, 5 and 9 are read differently across schools. Three states rather
        than a boolean, because collapsing a genuine disagreement into
        "favourable" states something the tradition does not."""
        signs = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
                 "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius",
                 "Pisces"]
        for house in (2, 5, 9):
            transit = signs[(0 + house - 1) % 12]
            assert chandra_bala("Aries", transit).verdict == "middling", house

    def test_it_wraps(self):
        assert chandra_bala("Pisces", "Aries").house == 2

    def test_an_unknown_sign_returns_none(self):
        assert chandra_bala("Nonsense", "Aries") is None
