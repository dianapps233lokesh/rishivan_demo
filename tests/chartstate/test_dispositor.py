"""Dispositor and nakshatra-lord chains.

Every test here is really about one thing: the chain must terminate. Mutual
disposition is common — Sun in Cancer with Moon in Leo is a 2-cycle — and a
walker without a visited set hangs the request rather than failing it, which is
the worst way for this to go wrong.
"""

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chartstate.dispositor import (
    dispositor_chain,
    dispositor_of,
    nakshatra_lord_chain,
    nakshatra_lord_of,
)

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


class TestDispositor:
    def test_a_planet_in_its_own_sign_disposits_itself(self, chart):
        """The simplest terminus, and a 1-cycle."""
        from rishivan.chart.relations import OWN_SIGNS

        for name, p in chart.planets.items():
            if p.rashi.lower() in OWN_SIGNS.get(name.lower(), ()):
                assert dispositor_of(chart, f"graha.{name.lower()}") == f"graha.{name.lower()}"
                break

    def test_every_planet_has_a_dispositor(self, chart):
        for name in chart.planets:
            assert dispositor_of(chart, f"graha.{name.lower()}").startswith("graha.")

    def test_the_dispositor_is_the_lord_of_the_occupied_sign(self, chart):
        from rishivan.astro.constants import RASHI_LORDS, RASHIS

        sun = chart.planets["Sun"]
        expected = RASHI_LORDS[RASHIS.index(sun.rashi)]
        assert dispositor_of(chart, "graha.sun") == f"graha.{expected}"

    def test_an_unknown_graha_raises(self, chart):
        with pytest.raises(KeyError):
            dispositor_of(chart, "graha.nibiru")


class TestChainTermination:
    def test_every_chain_terminates(self, chart):
        """The property that matters. Not "usually terminates"."""
        for name in chart.planets:
            chain = dispositor_chain(chart, f"graha.{name.lower()}")
            assert chain.path
            assert len(chain.path) <= len(chart.planets) + 1

    def test_a_chain_never_repeats_a_planet(self, chart):
        for name in chart.planets:
            path = dispositor_chain(chart, f"graha.{name.lower()}").path
            assert len(path) == len(set(path)), f"{name}: {path}"

    def test_a_self_dispositing_planet_is_a_cycle_of_one(self, chart):
        from rishivan.chart.relations import OWN_SIGNS

        for name, p in chart.planets.items():
            if p.rashi.lower() in OWN_SIGNS.get(name.lower(), ()):
                chain = dispositor_chain(chart, f"graha.{name.lower()}")
                assert chain.cycle
                assert chain.path == (f"graha.{name.lower()}",)
                return
        pytest.skip("no planet in its own sign in this chart")

    def test_a_mutual_pair_is_detected_as_a_cycle(self, chart):
        """Constructed rather than found: mutual disposition is common enough to
        matter and rare enough that a fixed birth chart may not have one."""
        import copy

        from rishivan.astro.constants import RASHI_LORDS, RASHIS

        c = copy.deepcopy(chart)
        # Sun into Cancer (Moon's sign), Moon into Leo (Sun's sign).
        c.planets["Sun"].rashi = RASHIS[RASHIS.index("Cancer")]
        c.planets["Moon"].rashi = RASHIS[RASHIS.index("Leo")]
        assert RASHI_LORDS[RASHIS.index("Cancer")] == "moon"
        assert RASHI_LORDS[RASHIS.index("Leo")] == "sun"

        chain = dispositor_chain(c, "graha.sun")
        assert chain.cycle
        assert set(chain.path) == {"graha.sun", "graha.moon"}

    def test_a_terminating_chain_names_its_terminus(self, chart):
        for name in chart.planets:
            chain = dispositor_chain(chart, f"graha.{name.lower()}")
            assert chain.terminus == chain.path[-1]

    def test_the_chain_starts_at_the_planet_asked_about(self, chart):
        assert dispositor_chain(chart, "graha.mars").path[0] == "graha.mars"


class TestNodes:
    def test_rahu_and_ketu_have_dispositors(self, chart):
        """They own no sign in the Parashari scheme, so they can never terminate
        a chain themselves — but they are disposited like anything else."""
        for node in ("graha.rahu", "graha.ketu"):
            assert dispositor_of(chart, node).startswith("graha.")

    def test_a_node_never_appears_as_a_terminus(self, chart):
        for name in chart.planets:
            chain = dispositor_chain(chart, f"graha.{name.lower()}")
            if not chain.cycle:
                assert chain.terminus not in ("graha.rahu", "graha.ketu")


class TestNakshatraChain:
    def test_every_planet_has_a_nakshatra_lord(self, chart):
        for name in chart.planets:
            assert nakshatra_lord_of(chart, f"graha.{name.lower()}").startswith("graha.")

    def test_the_nakshatra_chain_terminates(self, chart):
        for name in chart.planets:
            chain = nakshatra_lord_chain(chart, f"graha.{name.lower()}")
            assert chain.path
            assert len(chain.path) == len(set(chain.path))

    def test_the_lunar_framework_is_reachable_from_the_moon(self, chart):
        """§11's Nakshatra Rishi reasons over exactly this."""
        chain = nakshatra_lord_chain(chart, "graha.moon")
        assert chain.path[0] == "graha.moon"


class TestDeterminism:
    def test_the_same_chart_gives_the_same_chains(self, chart):
        a = [dispositor_chain(chart, f"graha.{n.lower()}") for n in chart.planets]
        b = [dispositor_chain(chart, f"graha.{n.lower()}") for n in chart.planets]
        assert a == b
