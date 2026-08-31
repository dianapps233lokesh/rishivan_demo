"""The five limbs of the panchang.

Four of them were never computed. A reading that stated a tithi produced it from
the model's training data, which is the one place in this system an answer could
still come from a cutoff rather than from an ephemeris.

The classical rules are pure arithmetic on two longitudes, so they are tested
with exact inputs rather than against a chart — a test that needs Swiss
Ephemeris to check a modulo is testing the wrong thing.
"""

import pytest

from rishivan.chart.limbs import (
    KARANA_FIXED, KARANA_MOVABLE, NAKSHATRAS, TITHI_NAMES, YOGA_NAMES,
    karana_of, nakshatra_of, tithi_of, yoga_of,
)


class TestTithi:
    def test_the_sun_and_moon_together_is_the_first_tithi(self):
        """Elongation zero — the new moon has just happened."""
        tithi = tithi_of(0.0)
        assert tithi.index == 0
        assert tithi.number == 1
        assert tithi.paksha == "Shukla"
        assert tithi.name == "Shukla Pratipada"

    def test_each_tithi_is_twelve_degrees(self):
        assert tithi_of(11.99).index == 0
        assert tithi_of(12.0).index == 1
        assert tithi_of(23.99).index == 1

    def test_opposition_is_purnima(self):
        """180 degrees of elongation is the full moon, the 15th of the bright
        fortnight — and the boundary is where the dark fortnight starts."""
        tithi = tithi_of(179.9)
        assert tithi.name == "Purnima"
        assert tithi.paksha == "Shukla"
        assert tithi.number == 15

    def test_just_past_opposition_is_the_dark_fortnight(self):
        tithi = tithi_of(180.1)
        assert tithi.paksha == "Krishna"
        assert tithi.number == 1
        assert tithi.name == "Krishna Pratipada"

    def test_the_last_tithi_is_amavasya(self):
        tithi = tithi_of(359.9)
        assert tithi.name == "Amavasya"
        assert tithi.paksha == "Krishna"

    def test_it_wraps_rather_than_running_off_the_end(self):
        assert tithi_of(360.0).index == 0
        assert tithi_of(-1.0).index == 29

    def test_there_are_thirty(self):
        assert len({tithi_of(d * 12 + 1).index for d in range(30)}) == 30

    def test_rikta_tithis_are_flagged(self):
        """The 4th, 9th and 14th of either fortnight are avoided for beginnings.
        Flagged rather than judged: the reading decides what it means."""
        for number in (4, 9, 14):
            assert tithi_of((number - 1) * 12 + 1).rikta
        for number in (1, 5, 10, 15):
            assert not tithi_of((number - 1) * 12 + 1).rikta


class TestYoga:
    def test_it_divides_the_circle_into_twenty_seven(self):
        assert yoga_of(0.0).index == 0
        assert yoga_of(13.3).index == 0
        assert yoga_of(13.4).index == 1
        assert len(YOGA_NAMES) == 27

    def test_it_is_the_sum_not_the_difference(self):
        """The one limb where the ayanamsa does NOT cancel. Tithi and karana are
        differences of two longitudes so the sidereal offset drops out; a yoga
        adds them, so it must be computed sidereally or it is 24 degrees wrong —
        two whole yogas."""
        assert yoga_of(100.0).index == yoga_of(100.0).index
        assert yoga_of(359.9).index == 26

    def test_the_inauspicious_pair_are_flagged(self):
        """Vyatipata and Vaidhriti. Named because they are the two a muhurta
        selection actually rejects on."""
        assert yoga_of(YOGA_NAMES.index("Vyatipata") * (360 / 27) + 1).inauspicious
        assert yoga_of(YOGA_NAMES.index("Vaidhriti") * (360 / 27) + 1).inauspicious
        assert not yoga_of(YOGA_NAMES.index("Siddhi") * (360 / 27) + 1).inauspicious


class TestKarana:
    def test_a_karana_is_half_a_tithi(self):
        assert karana_of(0.0).index == 0
        assert karana_of(5.9).index == 0
        assert karana_of(6.0).index == 1

    def test_the_first_half_tithi_is_the_fixed_one(self):
        """Kimstughna opens the lunar month and never recurs."""
        assert karana_of(0.0).name == "Kimstughna"
        assert karana_of(0.0).fixed

    def test_the_last_three_are_fixed_too(self):
        names = [karana_of(n * 6 + 1).name for n in (57, 58, 59)]
        assert names == list(KARANA_FIXED[1:])
        assert all(karana_of(n * 6 + 1).fixed for n in (57, 58, 59))

    def test_the_seven_movable_cycle_eight_times(self):
        """56 movable slots between the fixed ones: seven karanas, eight rounds."""
        movable = [karana_of(n * 6 + 1).name for n in range(1, 57)]
        assert set(movable) == set(KARANA_MOVABLE)
        assert movable[:7] == list(KARANA_MOVABLE)
        assert movable[7:14] == list(KARANA_MOVABLE)
        assert len(movable) == 56

    def test_vishti_is_flagged(self):
        """Bhadra. The one karana a muhurta selection rejects outright."""
        vishti = next(
            karana_of(n * 6 + 1) for n in range(1, 57)
            if karana_of(n * 6 + 1).name == "Vishti"
        )
        assert vishti.inauspicious
        assert not karana_of(6.0).inauspicious


class TestNakshatra:
    def test_it_divides_the_circle_into_twenty_seven(self):
        assert nakshatra_of(0.0).index == 0
        assert nakshatra_of(13.4).index == 1
        assert len(NAKSHATRAS) == 27

    def test_each_has_four_padas(self):
        assert nakshatra_of(0.1).pada == 1
        assert nakshatra_of(3.4).pada == 2
        assert nakshatra_of(13.2).pada == 4

    def test_the_name_matches_the_chart_engine(self):
        """A second spelling of Ashlesha is a second thing to drift, and the two
        would be printed in the same prompt."""
        from rishivan.chart.ephemeris import NAKSHATRAS as ENGINE

        assert list(NAKSHATRAS) == list(ENGINE)


class TestRouting:
    """A question about a limb must reach the block that now contains it.

    These terms were correctly absent while nothing computed the limbs: routing
    "what is today's tithi" to a panchang block with no tithi in it would have
    handed the model the wrong facts and invited it to supply the right one.
    """

    def test_a_limb_question_reaches_the_panchang_path(self):
        from rishivan.chart.panchang import mentions_panchang

        for question in (
            "what is today's tithi?",
            "is it ekadashi today?",
            "when is amavasya?",
            "what is the karana right now?",
            "what is today's nakshatra?",
        ):
            assert mentions_panchang(question), question

    def test_a_natal_question_does_not(self):
        """A bare "nakshatra" is usually "what is MY nakshatra", and a bare
        "yoga" collides with the astrological yogas. Routing either to the daily
        windows answers a question nobody asked."""
        from rishivan.chart.panchang import mentions_panchang

        for question in (
            "what is my nakshatra?",
            "which yogas do I have in my chart?",
            "tell me about my moon nakshatra",
        ):
            assert not mentions_panchang(question), question

    def test_a_limb_question_is_treated_as_a_date_question(self):
        from rishivan.council.question_profile import QuestionKind, profile_for

        profile = profile_for("what is today's tithi?", koonji_domain="")
        assert profile.kind is QuestionKind.OK_ON_DATE
        assert profile.needs("block.panchang")
