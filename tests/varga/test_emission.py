"""Vargas reach the fact set per request, not as a fixed six.

The first test is the one that matters: the default must produce a byte-identical
fact set, because 519 Koonji tests rest on it and a refactor that quietly widens
retrieval is a refactor that quietly changes every answer.
"""

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.koonji.facts import EMITTED_VARGAS, compile_facts

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


class TestTheDefaultIsUnchanged:
    def test_the_default_fact_set_is_byte_identical(self, chart):
        """`vargas` becoming an argument must change nothing for every existing
        caller."""
        explicit = compile_facts(chart, vargas=EMITTED_VARGAS)
        implicit = compile_facts(chart)
        assert implicit.atom_names() == explicit.atom_names()

    def test_the_default_is_still_the_original_six(self):
        assert set(EMITTED_VARGAS) == {"D2", "D7", "D9", "D10", "D12", "D30"}


class TestPerRequestEmission:
    def test_a_narrower_selection_emits_fewer_atoms(self, chart):
        """16 vargas x 9 grahas is 144 atoms most questions never match, which
        is why the selection runs before compilation rather than after."""
        wide = compile_facts(chart, vargas=("D9", "D10", "D60"))
        narrow = compile_facts(chart, vargas=("D9",))
        assert len(narrow.atoms) < len(wide.atoms)

    def test_a_requested_varga_reaches_the_fact_set(self, chart):
        facts = compile_facts(chart, vargas=("D60",))
        assert any(a.startswith("varga_occupies(varga.d60,") for a in facts.atom_names())

    def test_an_unrequested_varga_does_not(self, chart):
        facts = compile_facts(chart, vargas=("D9",))
        assert not any("varga.d10" in a for a in facts.atom_names())

    def test_no_vargas_at_all_is_valid(self, chart):
        """An UNKNOWN birth time selects nothing but D1, and D1 is the rashi
        chart itself rather than a division."""
        facts = compile_facts(chart, vargas=())
        assert not any(a.startswith("varga_occupies(") for a in facts.atom_names())
        assert facts.atoms

    def test_d1_is_not_emitted_as_a_division(self, chart):
        """It is the rashi chart. `occupies_rashi` already carries it."""
        facts = compile_facts(chart, vargas=("D1",))
        assert not any("varga.d1," in a for a in facts.atom_names())


class TestVargottama:
    def test_vargottama_survives_a_narrow_selection(self, chart):
        """It is a D9 comparison against D1 and is computed independently of
        which divisions are emitted — dropping it with the varga list would
        silently retire every rule that matches on it."""
        narrow = compile_facts(chart, vargas=())
        wide = compile_facts(chart)
        assert (
            {a for a in narrow.atom_names() if a.startswith("vargottama(")}
            == {a for a in wide.atom_names() if a.startswith("vargottama(")}
        )
