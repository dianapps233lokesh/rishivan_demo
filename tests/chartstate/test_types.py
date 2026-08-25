"""The diagnosis value types.

Frozen throughout, because `ChartState` is computed once and read by every Rishi
(spec C1). A Rishi that can mutate it can make its colleagues disagree about a
fact rather than about an interpretation, and that argument is unresolvable.
"""

import dataclasses

import pytest

from rishivan.chartstate.types import (
    Band,
    ChartState,
    HouseDiagnosis,
    PlanetDiagnosis,
    StrengthReading,
)


class TestStrengthReading:
    def test_an_estimated_reading_says_so(self):
        r = StrengthReading(value=0.6, band=Band.MODERATE,
                            system="parashari.partial.v1", is_estimated=True)
        assert r.is_estimated

    def test_an_estimated_scalar_is_withheld_from_claims(self):
        """A wrong strength number is worse than none, because everything
        downstream weights by it. The band is safe to show; the scalar is not,
        until the system is validated against a reference set."""
        r = StrengthReading(value=0.61, band=Band.MODERATE,
                            system="parashari.partial.v1", is_estimated=True)
        assert r.claimable_value is None
        assert r.claimable_band is Band.MODERATE

    def test_a_validated_scalar_is_claimable(self):
        r = StrengthReading(value=0.61, band=Band.MODERATE,
                            system="shadbala.full.v1", is_estimated=False)
        assert r.claimable_value == 0.61

    def test_the_system_is_always_named(self):
        """"The selected strength system" is a config decision, so a reading
        that does not say which system produced it is unauditable."""
        with pytest.raises(ValueError, match="system"):
            StrengthReading(value=0.5, band=Band.MODERATE, system="",
                            is_estimated=True)


class TestBands:
    def test_bands_order_from_weak_to_strong(self):
        assert Band.VERY_WEAK < Band.WEAK < Band.MODERATE < Band.STRONG < Band.VERY_STRONG

    def test_band_values_match_the_koonji_registry(self):
        """`registry.BANDS` is the vocabulary rules are written against. A band
        this module spells differently is a band no rule can match."""
        from rishivan.koonji.registry import BANDS

        assert {b.value for b in Band} == set(BANDS)


class TestImmutability:
    def test_every_type_is_frozen(self):
        for cls in (StrengthReading, PlanetDiagnosis, HouseDiagnosis, ChartState):
            assert dataclasses.fields(cls) is not None
            assert cls.__dataclass_params__.frozen, cls.__name__


class TestChartStateLookups:
    def test_a_planet_is_found_by_its_registry_symbol(self, sample_state):
        assert sample_state.planet("graha.sun").graha == "graha.sun"

    def test_a_house_is_found_by_number(self, sample_state):
        assert sample_state.house(10).bhava == 10

    def test_an_unknown_planet_raises_rather_than_returning_none(self, sample_state):
        """A None here becomes an AttributeError three frames away, in a Rishi."""
        with pytest.raises(KeyError):
            sample_state.planet("graha.nibiru")

    def test_a_house_out_of_range_raises(self, sample_state):
        with pytest.raises(KeyError):
            sample_state.house(13)


@pytest.fixture
def sample_state():
    strength = StrengthReading(value=0.5, band=Band.MODERATE,
                               system="parashari.partial.v1", is_estimated=True)
    planet = PlanetDiagnosis(
        graha="graha.sun", natural_nature="malefic", functional_nature="benefic",
        functional_reason="lord of the 9th (trikona)", rashi="rashi.leo",
        dignity="dignity.own_sign", dispositor="graha.sun",
        dispositor_chain=("graha.sun",), dispositor_cycle=True, bhava=1,
        lordships=(1,), conjunctions=(), aspects_cast=("bhava.07",),
        aspects_received=(), combust=False, retrograde=False, vargottama=False,
        strength=strength, varga_dignity={}, varga_confirms={},
        nakshatra="nakshatra.magha", nakshatra_lord="graha.ketu",
        nakshatra_lord_chain=("graha.ketu",), yogas=(),
    )
    house = HouseDiagnosis(
        bhava=10, rashi="rashi.taurus", lord="graha.venus", lord_placement=3,
        lord_strength=strength, lord_dispositor="graha.mercury", occupants=(),
        aspects_received=(), karakas=("graha.saturn",), benefic_influence=0.2,
        influence_reason=("aspected by Jupiter",), yogas=(), varga_confirms={},
        dasha_active=False, transit_active=(),
    )
    return ChartState(
        lagna="rashi.leo", planets=(planet,), houses=(house,),
        framework="parashari", strength_system="parashari.partial.v1",
        chart_digest="deadbeef", when=None,
    )
