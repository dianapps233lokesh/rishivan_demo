"""What a period lord actually touches.

This is what makes a dasha *relevant to a domain*, and it is what the Kala Rishi
reasons over. A period lord that owns the 10th activates career; one that merely
sits in the 3rd does not, however loudly its dasha is running.

Reads `ChartState`, not the chart — so it inherits Phase 2's functional verdicts
and lordships rather than recomputing them.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chartstate.build import build_chart_state
from rishivan.timing.activation import Strength, activates

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def state():
    return build_chart_state(compute_chart(BIRTH), when=WHEN)


class TestHouses:
    def test_a_lord_activates_the_houses_it_owns(self, state):
        """Ownership is the strongest tie a period has to a life area."""
        jupiter = state.planet("graha.jupiter")
        act = activates(state, "graha.jupiter")
        for house in jupiter.lordships:
            assert house in act.houses
            assert act.houses[house] is Strength.OWNS

    def test_a_lord_activates_the_house_it_occupies(self, state):
        jupiter = state.planet("graha.jupiter")
        act = activates(state, "graha.jupiter")
        assert jupiter.bhava in act.houses

    def test_ownership_outranks_occupation(self, state):
        """A planet in a house it also owns is recorded at the stronger tie, not
        twice and not at the weaker one."""
        for graha in (p.graha for p in state.planets):
            p = state.planet(graha)
            if p.bhava in p.lordships:
                assert activates(state, graha).houses[p.bhava] is Strength.OWNS

    def test_aspects_activate_more_weakly_than_occupation(self, state):
        act = activates(state, "graha.saturn")
        aspected = [h for h, s in act.houses.items() if s is Strength.ASPECTS]
        occupied = [h for h, s in act.houses.items() if s is Strength.OCCUPIES]
        assert Strength.ASPECTS < Strength.OCCUPIES < Strength.OWNS
        assert aspected or occupied  # Saturn aspects three houses in any chart

    def test_every_activated_house_is_in_range(self, state):
        for graha in (p.graha for p in state.planets):
            for house in activates(state, graha).houses:
                assert 1 <= house <= 12


class TestKarakas:
    def test_a_lord_carries_its_natural_significations(self, state):
        """Jupiter's period speaks to children and wealth whatever it owns,
        because a karaka travels with the graha."""
        assert 5 in activates(state, "graha.jupiter").karaka_houses

    def test_saturn_carries_longevity_and_career(self, state):
        karakas = activates(state, "graha.saturn").karaka_houses
        assert 8 in karakas or 10 in karakas


class TestNakshatraDispositorship:
    def test_a_lord_activates_grahas_whose_nakshatra_it_rules(self, state):
        """The lunar framework: a period lord reaches whatever sits in its
        nakshatras, which is often nothing and occasionally the whole chart."""
        touched = set()
        for graha in (p.graha for p in state.planets):
            touched |= set(activates(state, graha).nakshatra_dispositees)
        assert touched, "no graha lords another's nakshatra in this chart"

    def test_a_dispositee_is_never_the_lord_itself(self, state):
        for graha in (p.graha for p in state.planets):
            assert graha not in activates(state, graha).nakshatra_dispositees


class TestDomainRelevance:
    def test_a_tenth_lord_activates_career(self, state):
        from rishivan.timing.activation import activates_domain

        lord = state.house(10).lord
        assert activates_domain(state, lord, "domain.career")

    def test_a_graha_with_no_career_overlap_does_not_activate_it(self, state):
        """Overlap counts karaka houses as well as placements — a Mars period
        speaks to the 6th whatever Mars owns — so the graha has to be chosen by
        the same measure the function uses, not by placement alone."""
        from rishivan.timing.activation import activates_domain, domain_overlap

        unrelated = [
            p.graha for p in state.planets
            if not domain_overlap(state, p.graha, "domain.career")
        ]
        if not unrelated:
            pytest.skip("every graha reaches career in this chart")
        for graha in unrelated:
            assert not activates_domain(state, graha, "domain.career")

    def test_a_karaka_reaches_a_domain_its_placement_does_not(self, state):
        """The property that broke the test above, asserted deliberately."""
        from rishivan.timing.activation import domain_overlap

        act = activates(state, "graha.jupiter")
        overlap = set(domain_overlap(state, "graha.jupiter", "domain.wealth"))
        assert overlap & set(act.karaka_houses)

    def test_an_unmapped_domain_activates_nothing(self, state):
        from rishivan.timing.activation import activates_domain

        assert not activates_domain(state, "graha.sun", "domain.gardening")

    def test_relevance_reports_which_houses_matched(self, state):
        from rishivan.timing.activation import domain_overlap

        lord = state.house(10).lord
        assert 10 in domain_overlap(state, lord, "domain.career")


class TestReporting:
    def test_activation_explains_itself(self, state):
        act = activates(state, "graha.jupiter")
        assert act.reasons
        assert all(r.strip() for r in act.reasons)

    def test_it_is_deterministic(self, state):
        assert activates(state, "graha.mars") == activates(state, "graha.mars")

    def test_an_unknown_graha_raises(self, state):
        with pytest.raises(KeyError):
            activates(state, "graha.nibiru")
