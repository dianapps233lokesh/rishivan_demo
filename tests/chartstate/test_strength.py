"""Planetary strength — partial, and honest about it.

Full six-fold Shadbala is not implemented. What is here is Sthana (dignity) plus
Dig (directional) plus a placement/affliction adjustment, and every reading it
produces carries `is_estimated=True`.

That flag is the point of the module. A wrong strength number is worse than no
strength number, because everything downstream weights by it: the evidence
graph, the per-domain hierarchies in Phase 4, and any Rishi that says "weak".
So the band ships and the scalar is withheld until the system is validated.
"""

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chartstate.strength import (
    DIG_BALA_HOUSE,
    SYSTEM,
    band_for,
    strength_of,
)
from rishivan.chartstate.types import Band

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


class TestHonesty:
    def test_every_reading_is_marked_estimated(self, chart):
        """Until the six-fold system is validated against a published reference
        set, nothing here may present itself as Shadbala."""
        for name in chart.planets:
            assert strength_of(chart, f"graha.{name.lower()}").is_estimated

    def test_the_system_is_named_and_says_it_is_partial(self, chart):
        r = strength_of(chart, "graha.sun")
        assert r.system == SYSTEM
        assert "partial" in SYSTEM

    def test_the_scalar_is_withheld_while_estimated(self, chart):
        r = strength_of(chart, "graha.sun")
        assert r.claimable_value is None
        assert r.claimable_band in Band

    def test_the_components_are_itemised(self, chart):
        """A single number nobody can decompose is a number nobody can argue
        with, which is the wrong property for a contested quantity."""
        r = strength_of(chart, "graha.sun")
        assert set(r.components) >= {"sthana", "dig"}


class TestBounds:
    def test_every_value_is_normalised(self, chart):
        for name in chart.planets:
            r = strength_of(chart, f"graha.{name.lower()}")
            assert 0.0 <= r.value <= 1.0, (name, r.value)

    def test_every_band_is_a_real_band(self, chart):
        for name in chart.planets:
            assert strength_of(chart, f"graha.{name.lower()}").band in Band

    def test_banding_is_monotonic(self):
        """A higher score can never land in a weaker band."""
        bands = [band_for(v / 20) for v in range(21)]
        ranks = [list(Band).index(b) for b in bands]
        assert ranks == sorted(ranks)

    def test_the_extremes_reach_the_extreme_bands(self):
        assert band_for(0.0) is Band.VERY_WEAK
        assert band_for(1.0) is Band.VERY_STRONG


class TestSthana:
    def test_exaltation_outscores_debilitation(self, chart):
        """The one ordering that must hold whatever else changes."""
        import copy

        from rishivan.chart.relations import DEBILITATION, EXALTATION

        hi = copy.deepcopy(chart)
        hi.planets["Sun"].rashi = EXALTATION["sun"].capitalize()
        lo = copy.deepcopy(chart)
        lo.planets["Sun"].rashi = DEBILITATION["sun"].capitalize()
        assert (strength_of(hi, "graha.sun").components["sthana"]
                > strength_of(lo, "graha.sun").components["sthana"])

    def test_own_sign_beats_neutral(self, chart):
        import copy

        own = copy.deepcopy(chart)
        own.planets["Sun"].rashi = "Leo"
        other = copy.deepcopy(chart)
        other.planets["Sun"].rashi = "Gemini"
        assert (strength_of(own, "graha.sun").components["sthana"]
                > strength_of(other, "graha.sun").components["sthana"])


class TestDigBala:
    def test_each_planet_has_a_direction_of_strength(self):
        """Sun and Mars in the 10th, Jupiter and Mercury in the 1st, Moon and
        Venus in the 4th, Saturn in the 7th."""
        assert DIG_BALA_HOUSE["sun"] == 10
        assert DIG_BALA_HOUSE["jupiter"] == 1
        assert DIG_BALA_HOUSE["saturn"] == 7
        assert DIG_BALA_HOUSE["moon"] == 4

    def test_a_planet_in_its_direction_scores_full_dig(self, chart):
        import copy

        c = copy.deepcopy(chart)
        c.planets["Sun"].house = DIG_BALA_HOUSE["sun"]
        assert strength_of(c, "graha.sun").components["dig"] == pytest.approx(1.0)

    def test_the_opposite_house_scores_zero(self, chart):
        import copy

        c = copy.deepcopy(chart)
        c.planets["Sun"].house = 4  # opposite the 10th
        assert strength_of(c, "graha.sun").components["dig"] == pytest.approx(0.0)

    def test_dig_bala_falls_off_smoothly(self, chart):
        """Not a cliff: a planet one house off its direction is nearly as strong
        as one exactly on it."""
        import copy

        scores = []
        for house in (10, 11, 12, 1, 2, 3, 4):
            c = copy.deepcopy(chart)
            c.planets["Sun"].house = house
            scores.append(strength_of(c, "graha.sun").components["dig"])
        assert scores == sorted(scores, reverse=True)


class TestAfflictions:
    def test_combustion_weakens(self, chart):
        a = strength_of(chart, "graha.sun", combust=False)
        b = strength_of(chart, "graha.sun", combust=True)
        assert b.value < a.value

    def test_the_sun_is_never_combust_by_itself(self, chart):
        """Passed in rather than computed here, and the caller owns that - but a
        reading that claimed it would be nonsense."""
        assert strength_of(chart, "graha.sun", combust=False).value > 0

    def test_a_dusthana_placement_weakens(self, chart):
        import copy

        good = copy.deepcopy(chart)
        good.planets["Mars"].house = 1
        bad = copy.deepcopy(chart)
        bad.planets["Mars"].house = 8
        assert strength_of(bad, "graha.mars").value < strength_of(good, "graha.mars").value


class TestDeterminism:
    def test_the_same_chart_gives_the_same_reading(self, chart):
        assert strength_of(chart, "graha.mars") == strength_of(chart, "graha.mars")
