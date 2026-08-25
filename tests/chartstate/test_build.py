"""Assembly, and the digest that catches calculation drift.

The end of Phase 2: a real chart in, a complete diagnosis out. The tests split
three ways — that every §6 field is populated, that the diagnosis never
contradicts the Koonji fact set built from the same chart, and that the whole
thing is reproducible.

That last one carries the digest. A mismatch on recomputation means readings are
silently changing under a stable question, which is the highest-severity alarm
in the system and the one nobody would otherwise notice.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chartstate.build import build_chart_state, chart_digest
from rishivan.chartstate.types import Band, ChartState

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
OTHER = BirthData(
    year=1985, month=6, day=15, hour=4, minute=30,
    tz_offset_hours=5.5, lat=19.0760, lon=72.8777, place="Mumbai",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


@pytest.fixture(scope="module")
def state(chart):
    return build_chart_state(chart, when=WHEN)


class TestShape:
    def test_it_returns_a_chart_state(self, state):
        assert isinstance(state, ChartState)

    def test_every_graha_is_diagnosed(self, state, chart):
        assert len(state.planets) == len(chart.planets)

    def test_all_twelve_houses_are_diagnosed(self, state):
        assert [h.bhava for h in state.houses] == list(range(1, 13))

    def test_the_framework_and_system_are_recorded(self, state):
        """Two configuration decisions the blueprint asks to be stated. A
        reading that does not carry them cannot be compared across releases."""
        assert state.framework == "parashari"
        assert "partial" in state.strength_system

    def test_the_lagna_is_a_registry_symbol(self, state):
        assert state.lagna.startswith("rashi.")


class TestPlanetLevel:
    """Blueprint §6's planet-level list, field by field."""

    def test_natural_and_functional_nature_are_both_present(self, state):
        for p in state.planets:
            assert p.natural_nature in ("benefic", "malefic", "neutral")
            assert p.functional_nature in ("benefic", "malefic", "neutral")

    def test_every_functional_verdict_carries_its_reason(self, state):
        for p in state.planets:
            assert p.functional_reason.strip(), p.graha

    def test_dignity_and_dispositor_are_present(self, state):
        for p in state.planets:
            assert p.dignity.startswith("dignity.")
            assert p.dispositor.startswith("graha.")
            assert p.dispositor_chain

    def test_placement_and_lordship_are_present(self, state):
        for p in state.planets:
            assert 1 <= p.bhava <= 12
            assert all(1 <= h <= 12 for h in p.lordships)

    def test_aspects_are_recorded_in_both_directions(self, state):
        """Cast and received. A planet that only knows what it aspects cannot
        answer "what is afflicting the 7th"."""
        assert any(p.aspects_cast for p in state.planets)
        assert any(p.aspects_received for p in state.planets)

    def test_conditions_are_present(self, state):
        for p in state.planets:
            assert isinstance(p.combust, bool)
            assert isinstance(p.retrograde, bool)
            assert isinstance(p.vargottama, bool)

    def test_strength_is_estimated_and_banded(self, state):
        for p in state.planets:
            assert p.strength.is_estimated
            assert p.strength.band in Band

    def test_varga_dignity_is_reported(self, state):
        assert any(p.varga_dignity for p in state.planets)

    def test_varga_confirmation_is_a_verdict_not_a_placement(self, state):
        """"Does D9 corroborate the D1 reading" is the question §7 asks. A raw
        varga sign does not answer it."""
        for p in state.planets:
            for code, confirms in p.varga_confirms.items():
                assert isinstance(confirms, bool), (p.graha, code)

    def test_the_nakshatra_lord_and_chain_are_present(self, state):
        for p in state.planets:
            assert p.nakshatra.startswith("nakshatra.")
            assert p.nakshatra_lord.startswith("graha.")
            assert p.nakshatra_lord_chain

    def test_yogas_are_declared_and_empty(self, state):
        """Phase 4 fills them — a yoga is a fired rule and the engine runs
        later. Declared now so that phase adds a value, not a migration."""
        assert all(p.yogas == () for p in state.planets)


class TestHouseLevel:
    def test_each_house_has_a_lord_and_its_placement(self, state):
        for h in state.houses:
            assert h.lord.startswith("graha.")
            assert 1 <= h.lord_placement <= 12

    def test_the_lord_strength_and_dispositor_are_present(self, state):
        for h in state.houses:
            assert h.lord_strength.band in Band
            assert h.lord_dispositor.startswith("graha.")

    def test_occupants_match_the_chart(self, state, chart):
        placed = sum(len(h.occupants) for h in state.houses)
        assert placed == len(chart.planets)

    def test_benefic_influence_is_signed_and_bounded(self, state):
        for h in state.houses:
            assert -1.0 <= h.benefic_influence <= 1.0

    def test_influence_always_carries_reasons(self, state):
        """Zero must mean "genuinely balanced", not "unexamined", and only the
        reasons tell those apart."""
        for h in state.houses:
            assert h.influence_reason, h.bhava

    def test_karakas_are_named_for_the_houses_that_have_them(self, state):
        assert any(h.karakas for h in state.houses)

    def test_dasha_activation_is_computed_when_a_time_is_given(self, state):
        assert any(h.dasha_active for h in state.houses)

    def test_transit_activation_is_declared_and_empty(self, state):
        """Phase 3 fills it — it needs the transit windows."""
        assert all(h.transit_active == () for h in state.houses)


@pytest.fixture(scope="module")
def facts(chart):
    from rishivan.koonji.facts import compile_facts

    return compile_facts(chart, when=WHEN)


class TestAgreementWithTheFactSet:
    """The diagnosis and the fact set derive from one chart and must never
    disagree. They are separate code paths for good reasons, and separate code
    paths drift."""

    def test_house_placements_agree(self, state, facts):
        for p in state.planets:
            assert facts.has("occupies_bhava", p.graha, f"bhava.{p.bhava:02d}"), p.graha

    def test_dignities_agree(self, state, facts):
        for p in state.planets:
            assert facts.has("dignity", p.graha, p.dignity), p.graha

    def test_retrogression_agrees(self, state, facts):
        for p in state.planets:
            assert facts.has("retrograde", p.graha) == p.retrograde, p.graha

    def test_combustion_agrees(self, state, facts):
        for p in state.planets:
            assert facts.has("combust", p.graha) == p.combust, p.graha

    def test_vargottama_agrees(self, state, facts):
        for p in state.planets:
            assert facts.has("vargottama", p.graha) == p.vargottama, p.graha


class TestDigest:
    def test_the_same_chart_gives_the_same_digest(self, chart):
        assert chart_digest(chart) == chart_digest(compute_chart(BIRTH))

    def test_a_different_chart_gives_a_different_digest(self, chart):
        assert chart_digest(chart) != chart_digest(compute_chart(OTHER))

    def test_the_state_carries_its_digest(self, state, chart):
        assert state.chart_digest == chart_digest(chart)

    def test_the_digest_covers_the_calculation_stack(self, chart):
        """Not just positions. A reading computed under a different ayanamsa is
        a different reading, and a digest that ignored it would call two
        different answers the same."""
        import copy

        drifted = copy.deepcopy(chart)
        drifted.ayanamsa += 0.01
        assert chart_digest(drifted) != chart_digest(chart)


class TestDeterminism:
    def test_the_whole_diagnosis_is_reproducible(self, chart):
        a = build_chart_state(chart, when=WHEN)
        b = build_chart_state(chart, when=WHEN)
        assert a == b

    def test_it_is_frozen(self, state):
        with pytest.raises(Exception):
            state.lagna = "rashi.aries"
