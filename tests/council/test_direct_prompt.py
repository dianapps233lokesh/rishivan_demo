"""The direct lane's prompt, assembled from the constitution and nothing else.

Every test here runs with no network, no client and no database. That is the
property the lane exists to have, and `test_no_network` pins it explicitly.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.facts import derive_facts
from rishivan.council.direct_prompt import (
    constitution_for, framing_block, method_block, scoped_chart,
)

BIRTH = BirthData(
    year=1990, month=1, day=1, hour=12, minute=0,
    tz_offset_hours=5.5, lat=28.6139, lon=77.2090, place="New Delhi",
)
WHEN = datetime(2026, 8, 25, 12, 0)


@pytest.fixture(scope="module")
def facts():
    return derive_facts(compute_chart(BIRTH), when=WHEN)


def _block(text: str, heading: str) -> str:
    """The text under one heading, up to the next heading."""
    start = text.index(heading)
    rest = text[start + len(heading):]
    ends = [rest.index(h) for h in (
        "CHART FRAMEWORK", "PRIMARY EVIDENCE", "COMPUTED PERIODS", "WIDER CHART",
    ) if h in rest]
    return rest[:min(ends)] if ends else rest


class TestDomainResolution:
    def test_a_relationship_question_resolves_to_prema(self):
        assert constitution_for("domain.relationship").domain == "prema"

    def test_a_career_question_resolves_to_karma(self):
        assert constitution_for("domain.career").domain == "karma"

    def test_the_first_life_domain_wins_when_a_domain_maps_to_two(self):
        """`domain.status` maps to ("karma", "vansh"). The hierarchy weights the
        first, and so does this — a question routed to two domains is primarily
        about the first."""
        assert constitution_for("domain.status").domain == "karma"

    def test_an_unknown_domain_falls_back_to_atma(self):
        """Atma's protocol is the whole-chart one, which is the right default for
        a question the router could not place. Falling back to nothing would mean
        a prompt with no method block at all."""
        assert constitution_for("domain.nonsense").domain == "atma"
        assert constitution_for("").domain == "atma"


class TestMethodBlock:
    def test_the_protocol_steps_appear_numbered_and_in_order(self):
        block = method_block(constitution_for("domain.relationship"))
        assert "1. promise" in block
        assert "4. D9 confirmation" in block
        assert block.index("1. promise") < block.index("4. D9 confirmation")

    def test_the_step_count_matches_the_constitution(self):
        c = constitution_for("domain.relationship")
        block = method_block(c)
        for index, step in enumerate(c.protocol, start=1):
            assert f"{index}. {step}" in block

    def test_the_dimension_names_what_is_being_read(self):
        assert "Love / Marriage / Relationships" in method_block(
            constitution_for("domain.relationship")
        )

    def test_an_unsupported_step_must_be_declared_not_skipped(self):
        """The failure mode is a model that quietly drops the step it has no
        facts for, which reads as a complete reading."""
        block = method_block(constitution_for("domain.career"))
        assert "unsupported" in block.lower()


class TestFramingBlock:
    def test_it_names_the_text_families_from_the_constitution(self):
        block = framing_block(constitution_for("domain.relationship"))
        assert "BPHS" in block
        assert "Phaladeepika" in block

    def test_citation_is_forbidden_outright(self):
        """The panel is gone in this lane, so a citation cannot be checked
        against anything, and an uncheckable citation is worse than none."""
        block = framing_block(constitution_for("domain.relationship"))
        assert "page number" in block.lower()
        assert "chapter" in block.lower()

    def test_forbidden_claims_are_carried_through(self):
        c = constitution_for("domain.health")
        block = framing_block(c)
        assert c.forbidden_claims  # guard: the fixture must be meaningful
        for claim in c.forbidden_claims:
            assert claim in block

    def test_it_does_not_mention_this_repos_corpus_gaps(self):
        """`unavailable_sources` and `blocked_concepts` describe gaps in THIS
        repo's corpus. A model reading from its own knowledge has no such gaps,
        and telling it about them would suppress knowledge it does have."""
        c = constitution_for("domain.temperament")
        block = framing_block(c)
        assert c.unavailable_sources  # guard
        for missing in c.unavailable_sources:
            assert f"do not have {missing}" not in block

    def test_no_persona_leaks_in(self):
        block = framing_block(constitution_for("domain.relationship"))
        for word in ("Rishi", "seeker", "ancient sage", "warm"):
            assert word not in block


class TestScopedChart:
    def test_all_four_blocks_are_present(self, facts):
        text = scoped_chart(facts, constitution_for("domain.relationship"))
        for heading in ("CHART FRAMEWORK", "PRIMARY EVIDENCE",
                        "COMPUTED PERIODS", "WIDER CHART"):
            assert heading in text

    def test_the_lagna_and_birth_nakshatra_are_always_framework(self, facts):
        text = scoped_chart(facts, constitution_for("domain.career"))
        framework = _block(text, "CHART FRAMEWORK")
        assert "Ascendant (Lagna)" in framework
        assert "Birth nakshatra" in framework

    def test_the_luminaries_are_always_framework(self, facts):
        """Every §4-11 protocol opens on the chart framework, and no reading of
        any domain proceeds without the Sun and the Moon."""
        framework = _block(
            scoped_chart(facts, constitution_for("domain.wealth")),
            "CHART FRAMEWORK",
        )
        assert "Sun is in" in framework
        assert "Moon is in" in framework

    def test_a_marriage_question_puts_the_seventh_house_in_primary(self, facts):
        primary = _block(
            scoped_chart(facts, constitution_for("domain.relationship")),
            "PRIMARY EVIDENCE",
        )
        assert "The 7th house" in primary

    def test_a_marriage_question_puts_venus_and_jupiter_in_primary(self, facts):
        primary = _block(
            scoped_chart(facts, constitution_for("domain.relationship")),
            "PRIMARY EVIDENCE",
        )
        assert "Venus is in" in primary
        assert "Jupiter is in" in primary

    def test_a_career_question_puts_the_tenth_house_in_primary(self, facts):
        primary = _block(
            scoped_chart(facts, constitution_for("domain.career")),
            "PRIMARY EVIDENCE",
        )
        assert "The 10th house" in primary

    def test_a_career_question_leaves_an_uncovered_house_in_the_wider_chart(self, facts):
        """House 12, not house 7: `karma`'s coverage genuinely includes the 7th
        (§7 reads it for partnership in business), so asserting on 7 would prove
        nothing about whether the gate works."""
        primary = _block(
            scoped_chart(facts, constitution_for("domain.career")),
            "PRIMARY EVIDENCE",
        )
        assert "The 12th house" not in primary

    def test_the_house_a_fact_is_about_beats_the_house_a_planet_sits_in(self):
        """"Mars is in Virgo in the 7th house" is ABOUT Mars, not about the 7th.
        Filing it under house 7 is the bug `_SUBJECT_HOUSE`'s anchor exists to
        prevent, and this pins it from the direct lane's side.

        Synthetic facts, not the real chart: the real one puts these planets
        wherever the ephemeris puts them, and a test whose assertion depends on
        that is a test that passes for the wrong reason.

        The 7th lord here is Venus, deliberately not Mars — making Mars the lord
        would promote it legitimately and this test would prove nothing."""
        planet_in_seventh = (
            "Mars is in Virgo in the 7th house (Chitra nakshatra, pada 1)."
        )
        seventh_itself = (
            "The 7th house (marriage, spouse, partnerships) is ruled by Venus, "
            "placed in the 7th house."
        )
        text = scoped_chart(
            ["Ascendant (Lagna) is Pisces.", planet_in_seventh, seventh_itself],
            constitution_for("domain.relationship"),
        )
        primary = _block(text, "PRIMARY EVIDENCE")
        wider = _block(text, "WIDER CHART")
        # The house fact is about house 7, which prema owns.
        assert seventh_itself in primary
        # Mars is not in prema's planet set (venus, jupiter), so sitting in the
        # 7th must not promote it.
        assert planet_in_seventh in wider
        assert planet_in_seventh not in primary

    def test_the_lord_of_a_covered_house_is_promoted_with_its_own_placement(self, facts):
        """The spec asks for the domain's houses "with their lords", and the
        house line only names the lord — "ruled by Mercury, placed in the 11th".
        Mercury's OWN line carries the sign, nakshatra, pada and retrogression,
        which is what judging a 7th lord actually requires. Leaving it in the
        wider block hands the model the lord's name and hides its condition.

        For this chart the 7th lord is Mercury, which is NOT in prema's planet
        set (venus, jupiter) — so this can only pass if lordship promotes it.
        """
        text = scoped_chart(facts, constitution_for("domain.relationship"))
        primary = _block(text, "PRIMARY EVIDENCE")
        assert "The 7th house (marriage, spouse, partnerships) is ruled by Mercury" in primary
        assert "Mercury is in" in primary

    def test_a_lord_of_an_uncovered_house_is_not_promoted(self, facts):
        """Ketu rules nothing and is in no domain's planet set, so nothing may
        lift it out of the wider chart. Without this the promotion rule could
        quietly admit everything and still look like it worked."""
        wider = _block(
            scoped_chart(facts, constitution_for("domain.relationship")),
            "WIDER CHART",
        )
        assert "Ketu is in" in wider

    def test_the_mahadasha_timeline_lands_in_computed_periods(self, facts):
        periods = _block(
            scoped_chart(facts, constitution_for("domain.relationship")),
            "COMPUTED PERIODS",
        )
        assert "Mahadasha timeline from birth" in periods
        assert "Currently running" in periods

    def test_computed_periods_says_boundaries_not_predictions(self, facts):
        text = scoped_chart(facts, constitution_for("domain.relationship"))
        assert "not predictions" in text.lower()

    def test_the_wider_chart_is_labelled_but_not_withheld(self, facts):
        """Every protocol ends in whole-chart synthesis, so nothing is dropped —
        it is demoted and labelled."""
        text = scoped_chart(facts, constitution_for("domain.relationship"))
        assert "do not lead from these" in text.lower()
        wider = _block(text, "WIDER CHART")
        assert "The 3rd house" in wider

    def test_every_fact_appears_exactly_once(self, facts):
        """A fact in two blocks is a fact with two priorities."""
        text = scoped_chart(facts, constitution_for("domain.relationship"))
        for fact in facts:
            assert text.count(fact) == 1, f"appears {text.count(fact)}x: {fact}"

    def test_no_facts_is_stated_rather_than_rendered_empty(self):
        text = scoped_chart([], constitution_for("domain.relationship"))
        assert "no chart" in text.lower()
        assert "CHART FRAMEWORK" not in text
