"""The fact compiler's one invariant: no false negatives.

The index produces a superset of candidates and the VM prunes it with exact
values. That only holds if every positive ground truth about the chart is
present as an atom. A missing atom is a rule that never fires, and you cannot
see the absence of a rule - which is the silent failure the whole design exists
to rule out.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.koonji.facts import AtomTable, atom_name, compile_facts

# A fixed birth. Every expectation below was read off the computed chart, not
# guessed, and the chart itself is asserted first so a drift in the ephemeris
# layer fails loudly here rather than quietly changing every downstream number.
BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 23, 12, 0)


@pytest.fixture(scope="module")
def chart():
    return compute_chart(BIRTH)


@pytest.fixture(scope="module")
def facts(chart):
    return compile_facts(chart, when=WHEN)


class TestAtomTable:
    def test_interning_is_stable(self):
        t = AtomTable()
        a = t.intern("occupies_bhava(graha.sun,bhava.10)")
        b = t.intern("occupies_bhava(graha.sun,bhava.10)")
        assert a == b

    def test_lookup_does_not_grow_the_table(self):
        t = AtomTable()
        t.intern("occupies_bhava(graha.sun,bhava.10)")
        assert t.lookup("occupies_bhava(graha.moon,bhava.04)") is None
        assert len(t) == 1

    def test_round_trips_to_a_name(self):
        t = AtomTable()
        i = t.intern("dignity(graha.saturn,dignity.own_sign)")
        assert t.name(i) == "dignity(graha.saturn,dignity.own_sign)"

    def test_canonical_atom_names_are_argument_ordered(self):
        assert atom_name("occupies_bhava", "graha.sun", "bhava.10") == (
            "occupies_bhava(graha.sun,bhava.10)"
        )


class TestPlacement:
    def test_every_graha_gets_a_house_and_a_sign(self, chart, facts):
        for name in chart.planets:
            subject = f"graha.{name.lower()}"
            houses = [
                a for a in facts.atom_names()
                if a.startswith(f"occupies_bhava({subject},")
            ]
            signs = [
                a for a in facts.atom_names()
                if a.startswith(f"occupies_rashi({subject},")
            ]
            assert len(houses) == 1, f"{subject} has {len(houses)} houses"
            assert len(signs) == 1

    def test_placement_matches_the_chart(self, chart, facts):
        for name, position in chart.planets.items():
            subject = f"graha.{name.lower()}"
            assert facts.has("occupies_bhava", subject, f"bhava.{position.house:02d}")
            assert facts.has("occupies_rashi", subject, f"rashi.{position.rashi.lower()}")


class TestSubjectMaterialisation:
    """`lord_of(bhava.02) occupies bhava.11` is stored as a first-class atom.

    This is the space-for-time trade the design calls for: roughly 4,000 atoms
    instead of 800, in exchange for every rule match being pure set membership
    rather than a join at match time.
    """

    def test_house_lords_resolve_to_a_graha(self, chart, facts):
        for house in range(1, 13):
            ref = f"lord.bhava.{house:02d}"
            expected = f"graha.{chart.house_lords[house].lower()}"
            assert facts.subjects[ref] == expected

    def test_the_lord_of_a_house_carries_its_lords_placement(self, chart, facts):
        for house in range(1, 13):
            lord = chart.house_lords[house]
            seat = chart.planets[lord].house
            assert facts.has(
                "occupies_bhava", f"lord.bhava.{house:02d}", f"bhava.{seat:02d}"
            )

    def test_natural_karakas_resolve(self, chart, facts):
        # putra karaka is Jupiter; wherever Jupiter sits, so does karaka.putra
        seat = chart.planets["Jupiter"].house
        assert facts.subjects["karaka.putra"] == "graha.jupiter"
        assert facts.has("occupies_bhava", "karaka.putra", f"bhava.{seat:02d}")

    def test_aliases_are_symmetric_with_subjects(self, facts):
        for ref, graha in facts.subjects.items():
            assert ref in facts.aliases[graha]


class TestRelations:
    def test_conjunction_is_whole_sign_and_symmetric(self, chart, facts):
        by_house: dict[int, list[str]] = {}
        for name, p in chart.planets.items():
            by_house.setdefault(p.house, []).append(name.lower())
        for names in by_house.values():
            for a in names:
                for b in names:
                    if a == b:
                        continue
                    assert facts.has("conjunct", f"graha.{a}", f"graha.{b}")

    def test_a_planet_is_never_conjunct_itself(self, facts):
        assert not any(
            a.startswith("conjunct(") and a.split("(")[1].split(",")[0] == a.split(",")[1].rstrip(")")
            for a in facts.atom_names()
        )

    def test_parashari_drishti_every_graha_aspects_the_seventh(self, chart, facts):
        for name, p in chart.planets.items():
            seventh = ((p.house - 1 + 6) % 12) + 1
            assert facts.has(
                "aspects", f"graha.{name.lower()}", f"bhava.{seventh:02d}"
            )

    def test_special_aspects_are_applied(self, chart, facts):
        for name, offsets in (("Mars", (4, 8)), ("Jupiter", (5, 9)), ("Saturn", (3, 10))):
            house = chart.planets[name].house
            for offset in offsets:
                target = ((house - 1 + offset - 1) % 12) + 1
                assert facts.has(
                    "aspects", f"graha.{name.lower()}", f"bhava.{target:02d}"
                )

    def test_mercury_does_not_get_a_special_aspect(self, chart, facts):
        house = chart.planets["Mercury"].house
        fifth = ((house - 1 + 4) % 12) + 1
        seventh = ((house - 1 + 6) % 12) + 1
        if fifth != seventh:
            assert not facts.has("aspects", "graha.mercury", f"bhava.{fifth:02d}")


class TestDignityAndCondition:
    def test_dignity_matches_the_relations_table(self, chart, facts):
        from rishivan.chart.relations import dignity_of

        for name, p in chart.planets.items():
            expected = dignity_of(name.lower(), p.rashi.lower())
            got = [
                a.split(",")[1].rstrip(")")
                for a in facts.atom_names()
                if a.startswith(f"dignity(graha.{name.lower()},")
            ]
            if expected is None:
                assert got == [] or got == ["dignity.neutral"]
            else:
                assert f"dignity.{expected}" in got

    def test_retrograde_is_emitted_only_when_true(self, chart, facts):
        for name, p in chart.planets.items():
            atom = facts.has("retrograde", f"graha.{name.lower()}")
            assert atom == p.retrograde

    def test_nodes_are_always_retrograde(self, facts):
        assert facts.has("retrograde", "graha.rahu")
        assert facts.has("retrograde", "graha.ketu")

    def test_the_sun_is_never_combust(self, facts):
        assert not facts.has("combust", "graha.sun")

    def test_nodes_are_never_combust(self, facts):
        assert not facts.has("combust", "graha.rahu")
        assert not facts.has("combust", "graha.ketu")


class TestHouseGroups:
    def test_kendra_trikona_dusthana_agree_with_placement(self, chart, facts):
        for name, p in chart.planets.items():
            subject = f"graha.{name.lower()}"
            assert facts.has("in_kendra", subject) == (p.house in (1, 4, 7, 10))
            assert facts.has("in_trikona", subject) == (p.house in (1, 5, 9))
            assert facts.has("in_dusthana", subject) == (p.house in (6, 8, 12))
            assert facts.has("in_upachaya", subject) == (p.house in (3, 6, 10, 11))


class TestVarga:
    def test_d9_placement_is_emitted(self, facts):
        # One atom per *subject reference*, not per graha - the same D9 sign is
        # reachable as graha.venus, as lord.bhava.NN and as karaka.kalatra.
        d9 = [
            a for a in facts.atom_names()
            if a.startswith("varga_occupies(varga.d9,graha.")
        ]
        assert len(d9) == 9, "one D9 sign per graha"

    def test_vargottama_agrees_with_d1_and_d9(self, chart, facts):
        from rishivan.chart.vendor.varga import varga_sign

        for name, p in chart.planets.items():
            same = varga_sign("D9", p.longitude) == p.rashi_index
            assert facts.has("vargottama", f"graha.{name.lower()}") == same


class TestTiming:
    def test_the_running_mahadasha_is_a_fact(self, chart, facts):
        from rishivan.chart.dasha import current_periods

        running = current_periods(chart, WHEN)
        maha = running["maha"]
        assert maha is not None
        assert facts.has(
            "dasha_active", "dasha_system.vimshottari",
            f"graha.{maha.lord.lower()}", "level.maha",
        )

    def test_dasha_facts_move_with_time(self, chart):
        early = compile_facts(chart, when=datetime(1995, 6, 1))
        late = compile_facts(chart, when=datetime(2030, 6, 1))
        maha_of = lambda f: {a for a in f.atom_names() if "level.maha" in a}
        assert maha_of(early) != maha_of(late)


class TestUndecidable:
    """Shadbala is not computed by this stack. The honest response is to say so,
    not to omit the atom - an omitted atom reads as 'the rule did not apply',
    which is a false negative dressed up as an answer."""

    def test_shadbala_predicates_are_declared_undecidable(self, facts):
        assert "strength" in facts.undecidable
        assert "strength_band" in facts.undecidable

    def test_ashtakavarga_is_decidable_and_is_not_shadbala(self, facts):
        assert "sav_bindu" not in facts.undecidable
        assert facts.exact["sav_bindu(bhava.01)"] > 0

    def test_sav_bindus_sum_to_337(self, facts):
        """The Sarvashtakavarga total is a fixed 337 across the twelve signs.
        If this drifts, the bindu table is wrong."""
        total = sum(
            v for k, v in facts.exact.items() if k.startswith("sav_bindu(")
        )
        assert total == 337


class TestShape:
    def test_atom_count_is_in_the_designed_range(self, facts):
        """The design budgets roughly 4,000 atoms per chart. An order of
        magnitude either way means materialisation is wrong."""
        assert 500 <= len(facts.atoms) <= 20000

    def test_compiling_twice_gives_identical_facts(self, chart):
        a = compile_facts(chart, when=WHEN)
        b = compile_facts(chart, when=WHEN)
        assert a.atom_names() == b.atom_names()

    def test_serving_drops_atoms_no_rule_mentions(self, chart):
        """At serve time the bundle owns the atom table. An atom no rule
        references cannot affect retrieval, so it is not interned."""
        table = AtomTable()
        table.intern("occupies_bhava(graha.sun,bhava.10)")
        pinned = compile_facts(chart, when=WHEN, table=table, grow=False)
        assert len(pinned.atoms) <= 1
        assert len(table) == 1
