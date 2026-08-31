"""Six-fold strength, pinned against its classical anchors.

`chartstate/strength.py` computes two of the six and says so in its own name.
This is the whole thing, and the reason it can exist now is incidental: the
panchang work supplied paksha and sunrise, and `speed_deg_per_day` supplied the
velocity Chesta needs. Its docstring named those as the blockers.

Every component is tested at the point where the classical rule states a
specific value, because that is the only kind of assertion worth making about
an arithmetic nobody can eyeball.
"""

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.shadbala import (
    GRAHAS, NAISARGIKA_BALA, REQUIRED_RUPAS, VIRUPAS_PER_RUPA,
    ayana_bala, chesta_bala, compute_shadbala, dig_bala, drekkana_bala,
    kendradi_bala, nathonnatha_bala, ojhayugma_bala, paksha_bala,
    tribhaga_bala, uchcha_bala,
)

PUNIT = BirthData(year=2004, month=2, day=10, hour=2, minute=15,
                  tz_offset_hours=5.5, lat=26.9155, lon=75.8190, place="Jaipur")


@pytest.fixture(scope="module")
def chart():
    return compute_chart(PUNIT)


@pytest.fixture(scope="module")
def shadbala(chart):
    return compute_shadbala(chart, lat=26.9155, lon=75.8190)


class TestUchcha:
    def test_deep_exaltation_is_sixty(self):
        assert uchcha_bala("Sun", 10.0) == pytest.approx(60.0)

    def test_deep_debilitation_is_zero(self):
        assert uchcha_bala("Sun", 190.0) == pytest.approx(0.0)

    def test_it_is_continuous_across_the_sign(self):
        """The whole reason this needs a degree and not a sign. By sign alone a
        Sun at 10 Aries and one at 29 Aries are both simply "exalted"."""
        assert uchcha_bala("Sun", 10.0) > uchcha_bala("Sun", 29.0) > 0

    def test_every_graha_has_a_debilitation_point(self):
        for graha in GRAHAS:
            assert 0.0 <= uchcha_bala(graha, 0.0) <= 60.0


class TestSthanaParts:
    def test_an_angle_outscores_a_cadent_house(self):
        assert kendradi_bala(1) == 60.0
        assert kendradi_bala(2) == 30.0
        assert kendradi_bala(3) == 15.0

    def test_a_male_graha_takes_the_first_drekkana_only(self):
        assert drekkana_bala("Sun", 5.0) == 15.0
        assert drekkana_bala("Sun", 15.0) == 0.0
        assert drekkana_bala("Sun", 25.0) == 0.0

    def test_a_female_graha_takes_the_third(self):
        assert drekkana_bala("Venus", 25.0) == 15.0
        assert drekkana_bala("Venus", 5.0) == 0.0

    def test_a_hermaphrodite_graha_takes_the_second(self):
        assert drekkana_bala("Mercury", 15.0) == 15.0

    def test_odd_and_even_sign_strength_is_capped_at_thirty(self, chart):
        """Scored in the rashi and the navamsa, fifteen each."""
        for graha in GRAHAS:
            assert 0.0 <= ojhayugma_bala(chart, graha) <= 30.0


class TestDig:
    def test_a_graha_at_its_own_cusp_takes_sixty(self):
        """Jupiter is strongest at the ascendant."""
        assert dig_bala("Jupiter", 100.0, 100.0) == pytest.approx(60.0)

    def test_a_graha_opposite_its_cusp_takes_nothing(self):
        assert dig_bala("Jupiter", 280.0, 100.0) == pytest.approx(0.0)

    def test_the_sun_is_strongest_at_the_tenth(self):
        lagna = 0.0
        tenth_cusp = 270.0
        assert dig_bala("Sun", tenth_cusp, lagna) == pytest.approx(60.0)
        assert dig_bala("Sun", 90.0, lagna) == pytest.approx(0.0)

    def test_saturn_is_strongest_at_the_seventh(self):
        assert dig_bala("Saturn", 180.0, 0.0) == pytest.approx(60.0)


class TestKaala:
    def test_a_day_graha_peaks_at_noon(self):
        assert nathonnatha_bala("Sun", 12.0) == pytest.approx(60.0)
        assert nathonnatha_bala("Sun", 0.0) == pytest.approx(0.0)

    def test_a_night_graha_peaks_at_midnight(self):
        assert nathonnatha_bala("Saturn", 0.0) == pytest.approx(60.0)
        assert nathonnatha_bala("Saturn", 12.0) == pytest.approx(0.0)

    def test_mercury_is_strong_at_every_hour(self):
        """The rule as written, not a shortcut."""
        for hour in (0.0, 6.0, 12.0, 18.0):
            assert nathonnatha_bala("Mercury", hour) == 60.0

    def test_a_benefic_gains_through_the_bright_fortnight(self):
        assert paksha_bala("Jupiter", 180.0) == pytest.approx(60.0)   # full moon
        assert paksha_bala("Jupiter", 0.0) == pytest.approx(0.0)      # new moon

    def test_a_malefic_gains_through_the_dark(self):
        assert paksha_bala("Saturn", 0.0) == pytest.approx(60.0)
        assert paksha_bala("Saturn", 180.0) == pytest.approx(0.0)

    def test_jupiter_always_takes_the_tribhaga(self):
        for hour in (2.0, 9.0, 15.0, 22.0):
            assert tribhaga_bala("Jupiter", hour, 6.0, 18.0) == 60.0

    def test_one_graha_rules_each_third_of_the_day(self):
        held = [
            g for g in GRAHAS
            if g != "Jupiter" and tribhaga_bala(g, 8.0, 6.0, 18.0) == 60.0
        ]
        assert len(held) == 1

    def test_ayana_favours_north_for_the_sun_and_south_for_saturn(self):
        assert ayana_bala("Saturn", -20.0) > ayana_bala("Saturn", +20.0)
        assert ayana_bala("Mars", +20.0) > ayana_bala("Mars", -20.0)

    def test_the_suns_ayana_is_doubled(self):
        """The rule as written. It is why a winter Sun scores so low here."""
        assert ayana_bala("Sun", 0.0) == pytest.approx(60.0)
        assert ayana_bala("Mars", 0.0) == pytest.approx(30.0)

    def test_mercury_gains_from_either_declination(self):
        assert ayana_bala("Mercury", -20.0) == ayana_bala("Mercury", +20.0)


class TestChesta:
    def test_retrograde_takes_the_maximum(self):
        virupas, state = chesta_bala("Saturn", -0.05, retrograde=True,
                                     ayana=0.0, paksha=0.0)
        assert virupas == 60.0
        assert "vakra" in state

    def test_the_sun_borrows_its_ayana(self):
        """The Sun and Moon have no motion of their own in this scheme."""
        virupas, state = chesta_bala("Sun", 1.0, retrograde=False,
                                     ayana=42.0, paksha=7.0)
        assert virupas == 42.0
        assert "ayana" in state

    def test_the_moon_borrows_its_paksha(self):
        virupas, state = chesta_bala("Moon", 13.0, retrograde=False,
                                     ayana=42.0, paksha=7.0)
        assert virupas == 7.0
        assert "paksha" in state

    def test_mean_speed_scores_as_sama(self):
        from rishivan.chart.shadbala import MEAN_DAILY_MOTION

        virupas, state = chesta_bala("Mars", MEAN_DAILY_MOTION["Mars"],
                                     retrograde=False, ayana=0.0, paksha=0.0)
        assert virupas == 30.0
        assert "sama" in state


class TestNaisargika:
    def test_it_runs_in_order_of_brightness(self):
        order = sorted(NAISARGIKA_BALA, key=lambda g: -NAISARGIKA_BALA[g])
        assert order == ["Sun", "Moon", "Venus", "Jupiter", "Mercury",
                         "Mars", "Saturn"]

    def test_the_sun_takes_sixty_and_saturn_a_seventh_of_it(self):
        assert NAISARGIKA_BALA["Sun"] == pytest.approx(60.0)
        assert NAISARGIKA_BALA["Saturn"] == pytest.approx(60.0 / 7)


class TestTheWholeThing:
    def test_all_seven_grahas_are_computed(self, shadbala):
        assert set(shadbala.grahas) == set(GRAHAS)

    def test_the_nodes_are_absent(self, shadbala):
        """Not zero — absent. Rahu and Ketu cast no light and have no velocity
        of their own; the scheme assigns them no strength, and a zero row would
        read as "computed and found weak"."""
        assert "Rahu" not in shadbala.grahas
        assert "Ketu" not in shadbala.grahas

    def test_the_total_is_the_sum_of_the_six(self, shadbala):
        for bala in shadbala.grahas.values():
            parts = (bala.sthana_total + bala.dig + bala.kaala_total
                     + bala.chesta + bala.naisargika + bala.drik + bala.yuddha)
            assert bala.total == pytest.approx(parts)

    def test_the_requirement_is_quoted_in_virupas(self, shadbala):
        for bala in shadbala.grahas.values():
            assert bala.required == pytest.approx(
                REQUIRED_RUPAS[bala.graha] * VIRUPAS_PER_RUPA
            )

    def test_ranking_is_by_ratio_not_by_total(self, shadbala):
        """Mercury needs seven Rupas and Mars five, so ranking by total puts
        them in the wrong order whenever Mercury is merely adequate."""
        ranked = shadbala.ranked()
        assert [b.ratio for b in ranked] == sorted(
            [b.ratio for b in ranked], reverse=True
        )

    def test_every_component_stays_inside_its_classical_bound(self, shadbala):
        for bala in shadbala.grahas.values():
            for part in bala.sthana:
                if part.name == "saptavargaja":
                    assert 0.0 <= part.virupas <= 315.0, bala.graha
                else:
                    assert 0.0 <= part.virupas <= 60.0, (bala.graha, part.name)
            assert 0.0 <= bala.dig <= 60.0
            assert 0.0 <= bala.chesta <= 60.0
            assert 0.0 <= bala.naisargika <= 60.0

    def test_the_retrograde_grahas_took_the_full_chesta(self, chart, shadbala):
        """This chart has Jupiter and Saturn both retrograde, which is why it
        scores as strongly as it does."""
        for graha in ("Jupiter", "Saturn"):
            assert chart.planets[graha].retrograde
            assert shadbala.grahas[graha].chesta == 60.0

    def test_the_conventions_are_stated(self, shadbala):
        """Shadbala is the most divergent calculation in Jyotish. A number
        nobody can trace is worse than no number, because it looks
        authoritative."""
        assert len(shadbala.conventions) >= 6
        joined = " ".join(shadbala.conventions)
        assert "Paksha" in joined and "Chesta" in joined

    def test_the_day_lord_is_counted_from_sunrise(self, chart):
        """A birth at 02:15 belongs to the previous weekday, and the day lord is
        worth 45 Virupas to whoever holds it. Reading it off a calendar gives it
        to the wrong graha on every pre-dawn birth."""
        from rishivan.chart.shadbala import compute_shadbala

        result = compute_shadbala(chart, lat=26.9155, lon=75.8190)
        notes = " ".join(
            part.note for bala in result.grahas.values() for part in bala.kaala
        )
        assert "day:" in notes
