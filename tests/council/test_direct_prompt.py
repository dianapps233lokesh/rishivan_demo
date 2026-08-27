"""The direct lane's prompt, assembled from the constitution and nothing else.

Every test here runs with no network, no client and no database. That is the
property the lane exists to have, and `test_no_network` pins it explicitly.
"""

from datetime import datetime

import pytest

from rishivan.chart.ephemeris import BirthData, compute_chart
from rishivan.chart.facts import derive_facts
from rishivan.council.direct_prompt import (
    build_direct_prompt, constitution_for, framing_block, method_block,
    scoped_chart,
)
from rishivan.graph.state import initial_state

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


def _state(question="when will I marry?", **kw):
    s = initial_state(question, query_time=WHEN)
    s["koonji_domain"] = kw.pop("koonji_domain", "domain.relationship")
    s.update(kw)
    return s


@pytest.fixture(scope="module")
def chart_state():
    from rishivan.chartstate.build import build_chart_state
    return build_chart_state(compute_chart(BIRTH), when=WHEN)


class TestTransits:
    """The gap a competitor's answer exposed.

    Their timing derived entirely from a transit exit — "Jupiter transiting
    Cancer, house 7 from ascendant, until 31 Oct 2026 … Nov 2026 door opens
    after this transit ends." Our prompt carried no transit data at all beyond
    the transiting Moon's nakshatra, which moves every 2¼ days and is noise at
    the scale of a career or a marriage. So step 8 of every protocol either came
    back unsupported or was padded with the Moon.

    Swiss Ephemeris computes a full chart in 0.08 ms, so the ingress and egress
    dates that make a transit answerable cost nothing worth counting.
    """

    def test_the_block_is_present_with_a_chart(self, facts):
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        assert "TRANSITS NOW" in prompt

    def test_it_is_absent_without_a_chart(self):
        assert "TRANSITS NOW" not in build_direct_prompt(_state())

    def test_the_slow_movers_are_all_reported(self, facts):
        """Jupiter, Saturn and the nodes. The fast planets change too often to
        time anything a seeker asks about."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        block = prompt[prompt.index("TRANSITS NOW"):]
        for graha in ("Jupiter", "Saturn", "Rahu", "Ketu"):
            assert graha in block

    def test_each_transit_gives_its_house_from_the_natal_lagna(self, facts):
        """A transiting sign means nothing on its own; which house of THIS chart
        it is crossing is the whole content."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        block = prompt[prompt.index("TRANSITS NOW"):]
        assert "house" in block
        assert "from your lagna" in block

    def test_the_next_sign_change_is_dated(self, facts):
        """The date the competitor's whole answer hung on."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        block = prompt[prompt.index("TRANSITS NOW"):]
        assert "leaves" in block
        assert "20" in block  # some year

    def test_retrogression_is_flagged(self, facts):
        """Saturn is retrograde in Pisces on the test date, and a retrograde
        transit can re-enter the sign it just left - so a date computed by
        forward scan is the NEXT change, not a permanent exit."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        block = prompt[prompt.index("TRANSITS NOW"):]
        assert "retrograde" in block

    def test_sade_sati_is_named_when_it_applies(self, facts):
        """Natal Moon is Aquarius on the test chart and Saturn transits Pisces -
        the 2nd from the Moon, which is the setting leg. Naming it matters: it is
        the single most asked-about transit in the tradition, and a reading that
        misses it while the seeker's family is talking about it looks blind."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        assert "sade sati" in prompt.lower()

    def test_the_sade_sati_leg_is_stated(self, facts):
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        assert any(leg in prompt for leg in ("rising", "peak", "setting"))

    def test_transits_are_dated_to_the_reading_moment(self, facts):
        """Not to `datetime.now()`. A transit block computed for today inside a
        prompt whose chart was read for another date is two moments in one
        reading."""
        early = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
            query_time=datetime(2020, 1, 1, 12, 0),
        ))
        assert "TRANSITS NOW" in early
        assert early != build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))


class TestTheReadingKnowsWhatDayItIs:
    """The prompt carried period boundaries and never said which moment it was
    being read from.

    "Currently running: Sun Mahadasha, Venus Antardasha" names the period but not
    the date, so nothing in the prompt distinguished a period that had ended from
    one still to come. A real reading of "when will I get married?" duly offered
    `Saturn: 2024-06-12 to 2025-05-25` as "an earlier period of potential
    activation" - a window that closed sixteen months before the question was
    asked. `query_time` was in state the whole time and simply never rendered.
    """

    def test_todays_date_appears(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "2026-08-25" in prompt

    def test_the_weekday_is_given_since_the_rules_forbid_deriving_one(self, facts):
        """`ground_truth_rules` says "Copy the weekday from the Date line. Do not
        work it out yourself" - so there had better be a Date line."""
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert WHEN.strftime("%A") in prompt

    def test_it_says_a_closed_period_cannot_carry_a_future_event(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "cannot carry" in prompt.lower()

    def test_a_missing_query_time_does_not_invent_one(self):
        """Better no date than a fabricated one - and `datetime.now()` here would
        make the golden snapshot unpinnable as a side effect."""
        state = initial_state("when will I marry?")
        state["koonji_domain"] = "domain.relationship"
        state["query_time"] = None
        prompt = build_direct_prompt(state)
        assert "TODAY" not in prompt


class TestSubPeriodBoundaries:
    """Timing granularity, without a window that reads as a forecast.

    The CANDIDATE WINDOW block this replaces was copied straight out as a dated
    prediction: "You will receive your major career promotion during 2026-08-27
    to 2027-08-07." Its activation and trigger ranges were *identical* and both
    began on the query date, because `windows_between` anchors to `start=now` -
    so the block contained no event, only the horizon restated. A range that
    begins today reads as imminent whatever label sits above it.

    The mahadasha timeline alone is too coarse to time anything (spans of six to
    twenty years). The antardashas inside the running mahadasha, and the
    pratyantardashas inside the running antardasha, are the granularity a timing
    answer actually needs - and they are boundaries, not verdicts.
    """

    def test_the_running_antardashas_are_listed(self, facts):
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        assert "Antardashas within the running" in prompt

    def test_the_running_pratyantardashas_are_listed(self, facts):
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        assert "Pratyantardashas within the running" in prompt

    def test_the_candidate_window_block_is_gone(self, facts):
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        assert "CANDIDATE WINDOW" not in prompt
        assert "activation:" not in prompt

    def test_every_period_is_marked_past_running_or_future(self, facts):
        """The failure this fixes. Without a marker the model cannot tell a
        window that has closed from one still ahead, and it offered a closed one
        as a forecast."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        block = prompt[prompt.index("Antardashas within"):]
        assert "[past]" in block
        assert "[RUNNING NOW]" in block
        assert "[future]" in block

    def test_exactly_one_antardasha_is_marked_running(self, facts):
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        block = prompt[
            prompt.index("Antardashas within"):prompt.index("Pratyantardashas")
        ]
        assert block.count("[RUNNING NOW]") == 1

    def test_the_next_mahadasha_is_broken_down_too(self, facts):
        """A "when" question whose answer falls after the current mahadasha had
        nowhere to land: the model correctly named the next mahadasha and then
        could not time anything inside it, because no breakdown was supplied."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        # Saturn runs 2024-02-09 to 2043-02-08 on this chart; Mercury follows.
        assert "Antardashas within the following Mercury mahadasha" in prompt

    def test_the_following_mahadasha_periods_are_all_future(self, facts):
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        block = prompt[prompt.index("following Mercury mahadasha"):]
        head = block[:block.index("Pratyantardashas")] if "Pratyantardashas" in block else block
        assert "[past]" not in head
        assert "[RUNNING NOW]" not in head

    def test_sub_periods_need_a_chart_not_a_timing_report(self, facts):
        """Derived from the chart directly, so nothing depends on the timing
        node having run or on a promise flag having been fabricated."""
        assert "Antardashas within the running" not in build_direct_prompt(
            _state(chart_facts=facts)
        )

    def test_a_promise_verdict_is_required_before_any_date(self, facts):
        """The instruction that replaces the label the model ignored."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        assert "before you write any date" in prompt.lower()

    def test_certainty_is_forbidden_for_dated_claims_not_only_for_health(self, facts):
        """The old rule covered health and death only, and the model wrote "You
        will receive your major career promotion" with a peak window."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        lowered = prompt.lower()
        assert "will happen" in lowered or "never state that an event will" in lowered


class TestPlanetaryCondition:
    """What Swiss Ephemeris already worked out, sent instead of re-derived.

    `PlanetDiagnosis` carries dignity, combustion, strength, vargottama,
    functional nature and received aspects. None of it reached the prompt, so a
    real reading re-derived exaltation from raw signs (correctly, as it happens)
    and then asserted "there are no conflicting malefic afflictions to the 10th
    house or its ruler" - on a chart where the Sun and the Moon sat in the same
    nakshatra pada. It had no aspect data and no combustion flag to check
    against, so the claim was not a judgement, it was a guess in the shape of
    one.
    """

    def test_the_block_is_present_when_a_diagnosis_exists(self, facts, chart_state):
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart_state=chart_state,
        ))
        assert "PLANETARY CONDITION" in prompt

    def test_it_is_absent_without_a_diagnosis(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "PLANETARY CONDITION" not in prompt

    def test_every_graha_gets_a_line(self, facts, chart_state):
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart_state=chart_state,
        ))
        block = prompt[prompt.index("PLANETARY CONDITION"):]
        for graha in ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus",
                      "Saturn", "Rahu", "Ketu"):
            assert graha in block, f"{graha} has no condition line"

    def test_dignity_is_stated_not_left_to_be_inferred(self, facts, chart_state):
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart_state=chart_state,
        ))
        block = prompt[prompt.index("PLANETARY CONDITION"):]
        assert "dignity" in block.lower()

    def test_strength_bands_are_stated(self, facts, chart_state):
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart_state=chart_state,
        ))
        block = prompt[prompt.index("PLANETARY CONDITION"):]
        assert any(b in block for b in ("very_weak", "weak", "moderate",
                                        "strong", "very_strong"))

    def test_the_partial_system_caveat_is_stated_once(self, facts, chart_state):
        """`is_estimated` says the strength system ran partial. Sending the
        bands and hiding that would dress a partial calculation as a full one -
        but nine identical parentheticals is a caveat nobody reads, so it goes
        in the header once, naming the system."""
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart_state=chart_state,
        ))
        block = prompt[prompt.index("PLANETARY CONDITION"):]
        assert chart_state.strength_system in block
        assert block.count("estimates, not measurements") == 1

    def test_the_conventional_graha_order_is_used(self, facts, chart_state):
        """`ChartState.planets` arrives alphabetical, which no astrologer reads
        in - and which would not line up with the placement lines above it."""
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart_state=chart_state,
        ))
        block = prompt[prompt.index("PLANETARY CONDITION"):]
        positions = [
            block.index(f"- {graha}:")
            for graha in ("Sun", "Moon", "Mars", "Mercury", "Jupiter",
                          "Venus", "Saturn", "Rahu", "Ketu")
        ]
        assert positions == sorted(positions)

    def test_combustion_is_reported(self, facts, chart_state):
        """The failure this block exists for. A combust graha is a graha whose
        promise the tradition discounts, and no amount of sign-and-house data
        reveals it."""
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart_state=chart_state,
        ))
        block = prompt[prompt.index("PLANETARY CONDITION"):]
        assert "combust" in block.lower()

    def test_received_aspects_name_only_grahas(self, facts, chart_state):
        """`aspects_received` mixes grahas with karaka and lord symbols -
        `karaka.ayu`, `lord.bhava.09`. Those are internal join keys, and pasting
        them into a prompt asks the model to interpret this repo's vocabulary
        rather than a chart."""
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart_state=chart_state,
        ))
        block = prompt[prompt.index("PLANETARY CONDITION"):]
        assert "karaka." not in block
        assert "lord.bhava" not in block
        assert "graha." not in block
        assert "aspected by" in block

    def test_the_registry_symbols_are_humanised(self, facts, chart_state):
        """`dignity.neutral` and `graha.moon` are registry symbols. The rule
        engine needs them; a reading prompt does not."""
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart_state=chart_state,
        ))
        block = prompt[prompt.index("PLANETARY CONDITION"):]
        assert "dignity." not in block

    def test_it_tells_the_model_not_to_recompute_them(self, facts, chart_state):
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart_state=chart_state,
        ))
        assert "do not re-derive" in prompt.lower()


class TestBuildDirectPrompt:
    def test_the_blocks_appear_in_order(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        order = [
            "expert Vedic (Jyotish) astrologer",
            "READING METHOD",
            "CHART FRAMEWORK",
            "OUTPUT",
            "THE QUESTION",
        ]
        positions = [prompt.index(marker) for marker in order]
        assert positions == sorted(positions), prompt[:400]

    def test_the_question_is_last_and_present(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert prompt.rstrip().endswith("when will I marry?")

    def test_the_ground_truth_rules_are_carried_over(self, facts):
        """The copy-times-verbatim discipline exists because the model got it
        wrong in production. Every reason for it still holds here."""
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "CHARACTER FOR CHARACTER" in prompt
        assert "Copy the weekday from the Date line" in prompt
        assert "Never convert, round, shift, or re-derive a time." in prompt

    def test_it_does_not_warn_about_pages_that_do_not_exist(self, facts):
        """`_GROUND_TRUTH_WARNING` tells the model that "the classical pages
        further down" carry no times for this date. There are no classical pages
        in this lane, so that line points at nothing — and an instruction
        referring to absent material teaches the model that the instructions
        describe a prompt other than the one it was given."""
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "classical pages further down" not in prompt
        assert "pages" not in prompt.lower()

    def test_every_other_line_of_the_warning_survives(self, facts):
        """Only the pages line is dropped. Filtering by content rather than
        rewriting the block keeps the two lanes from drifting on the lines they
        still share."""
        from rishivan.council.prompts import _GROUND_TRUTH_WARNING

        prompt = build_direct_prompt(_state(chart_facts=facts))
        dropped = [
            line for line in _GROUND_TRUTH_WARNING.splitlines()
            if line.strip() and line not in prompt
        ]
        assert len(dropped) == 1, f"expected only the pages line, got {dropped}"
        assert "pages" in dropped[0]

    def test_the_output_shape_asks_for_the_falsifier(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "falsif" in prompt.lower()

    def test_the_output_shape_asks_for_confidence(self, facts):
        assert "confidence" in build_direct_prompt(
            _state(chart_facts=facts)
        ).lower()

    def test_a_chartless_question_still_builds_a_prompt(self):
        prompt = build_direct_prompt(_state("what is a nakshatra?", chart_facts=None))
        assert "READING METHOD" in prompt
        assert "No chart was computed" in prompt

    def test_selected_vargas_are_rendered_with_their_placements(self, facts):
        """A varga CODE tells the model nothing. `varga_facts` gives the actual
        divisional placements, which is what a D9 confirmation step needs."""
        from rishivan.varga.confidence import BirthConfidence
        from rishivan.varga.select import VargaSelection

        chart = compute_chart(BIRTH)
        prompt = build_direct_prompt(_state(
            chart_facts=facts,
            chart=chart,
            vargas=VargaSelection(
                selected=("D9",), withheld=(),
                confidence=BirthConfidence.MINUTE,
            ),
        ))
        assert "(D9)" in prompt
        assert "Ascendant is" in prompt

    def test_d1_is_not_repeated_as_a_division(self, facts):
        """D1 *is* the chart. The framework and primary blocks already carry
        "Sun is in Sagittarius in the 10th house"; emitting "Rashi chart (D1):
        Sun is in Sagittarius in the house 10" beside it states every placement
        twice in two wordings, which spends the prompt on making the model
        wonder whether they are the same fact."""
        from rishivan.varga.confidence import BirthConfidence
        from rishivan.varga.select import VargaSelection

        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart=compute_chart(BIRTH),
            vargas=VargaSelection(
                selected=("D1", "D9"), withheld=(),
                confidence=BirthConfidence.MINUTE,
            ),
        ))
        assert "Rashi chart (D1)" not in prompt
        assert "(D9)" in prompt

    def test_a_selection_of_only_d1_emits_no_division_block(self, facts):
        from rishivan.varga.confidence import BirthConfidence
        from rishivan.varga.select import VargaSelection

        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart=compute_chart(BIRTH),
            vargas=VargaSelection(
                selected=("D1",), withheld=(),
                confidence=BirthConfidence.MINUTE,
            ),
        ))
        assert "DIVISIONAL CHARTS" not in prompt

    def test_a_withheld_varga_does_not_leak_its_facts_in(self, facts):
        """The prompt must not supply evidence it forbids in the same breath.

        `chart_natal_node` appends varga facts for whatever `relevant_vargas`
        the intake classifier named; `varga_select` decides admissibility
        independently from birth-time precision. When they disagree the facts
        arrive anyway, so a real prompt carried ten D10 placements under WIDER
        CHART and, below them, "D10: I have not used it. Do not reason from
        these." The model has no way to referee that, and should not have to.
        """
        from rishivan.varga.confidence import BirthConfidence
        from rishivan.varga.select import VargaSelection, WithheldVarga

        d10 = [
            "In your Dashamsha chart (D10): Ascendant is Sagittarius.",
            "Dashamsha chart (D10): Sun is in Virgo in the house 10 "
            "(Hasta nakshatra, pada 2).",
        ]
        prompt = build_direct_prompt(_state(
            "will I get a promotion?",
            koonji_domain="domain.career",
            chart=compute_chart(BIRTH),
            chart_facts=facts + d10,
            vargas=VargaSelection(
                selected=(), withheld=(WithheldVarga(
                    code="D10", required=BirthConfidence.MINUTE,
                    actual=BirthConfidence.HOUR,
                    reason="birth time recorded to the hour",
                ),),
                confidence=BirthConfidence.HOUR,
            ),
        ))
        assert "Dashamsha chart (D10)" not in prompt
        # Still SAID it was withheld, and why. Dropping the facts silently
        # would be the other half of the same mistake.
        assert "D10" in prompt
        assert "not used" in prompt.lower()

    def test_an_admitted_varga_keeps_its_facts(self, facts):
        """The filter must key on the withheld list, not on being a varga."""
        from rishivan.varga.confidence import BirthConfidence
        from rishivan.varga.select import VargaSelection

        d9 = ["Navamsha chart (D9): Venus is in Leo in the house 3."]
        prompt = build_direct_prompt(_state(
            chart_facts=facts + d9,
            chart=compute_chart(BIRTH),
            vargas=VargaSelection(
                selected=("D9",), withheld=(),
                confidence=BirthConfidence.MINUTE,
            ),
        ))
        assert "Navamsha chart (D9): Venus is in Leo" in prompt

    def test_withheld_vargas_are_stated_not_silent(self, facts):
        from rishivan.varga.confidence import BirthConfidence
        from rishivan.varga.select import VargaSelection, WithheldVarga

        withheld = WithheldVarga(
            code="D60", required=BirthConfidence.EXACT,
            actual=BirthConfidence.HOUR,
            reason="birth time recorded to the hour",
        )
        prompt = build_direct_prompt(_state(
            chart_facts=facts, chart=compute_chart(BIRTH),
            vargas=VargaSelection(
                selected=("D9",), withheld=(withheld,),
                confidence=BirthConfidence.HOUR,
            ),
        ))
        assert "D60" in prompt
        assert "not used" in prompt.lower()

    def test_conversation_history_is_included_when_present(self, facts):
        """Dropping it would make every follow-up answer as though asked cold,
        and the comparison would read that as a grounding failure."""
        from rishivan.council.conversation import Conversation

        conversation = Conversation()
        conversation.add("will I marry?", "Marriage is close.", rishi="medhan")
        prompt = build_direct_prompt(_state(
            "tell me more", chart_facts=facts, conversation=conversation,
        ))
        assert "Marriage is close." in prompt

    def test_no_history_block_on_a_first_turn(self, facts):
        assert "EARLIER IN THIS CONVERSATION" not in build_direct_prompt(
            _state(chart_facts=facts)
        )

    def test_the_history_block_carries_no_voice_instructions(self, facts):
        """`continuity_instruction` — the retrieval lane's version — ends with
        "End on a NEW hook, never the same one twice", which is a persona
        instruction. This lane has no persona and does not end on a hook."""
        from rishivan.council.conversation import Conversation

        conversation = Conversation()
        conversation.add("will I marry?", "Marriage is close.", rishi="medhan")
        prompt = build_direct_prompt(_state(
            "tell me more", chart_facts=facts, conversation=conversation,
        ))
        assert "hook" not in prompt.lower()
        assert "greet" not in prompt.lower()

    def test_no_persona_language_anywhere(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        for banned in ("Rishi", "seeker asks", "seven movements", "sign-off"):
            assert banned not in prompt

    def test_it_is_deterministic(self, facts):
        state = _state(chart_facts=facts)
        assert build_direct_prompt(state) == build_direct_prompt(state)


def test_no_network(monkeypatch, facts):
    """The proof the retrieval dependency is gone.

    Any stray import of the vector store or the database raises here rather than
    quietly working in a dev environment that happens to have credentials. This
    is the only test that would catch a re-introduction.
    """
    import builtins

    real_import = builtins.__import__
    forbidden = ("qdrant_client", "sqlalchemy", "psycopg", "google.genai")

    def guarded(name, *args, **kwargs):
        if any(name == f or name.startswith(f + ".") for f in forbidden):
            raise AssertionError(f"direct prompt assembly imported {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    prompt = build_direct_prompt(_state(chart_facts=facts))
    assert "READING METHOD" in prompt
