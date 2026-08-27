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
    """The text under one heading, up to the next block separator."""
    start = text.index(heading)
    rest = text[start + len(heading):]
    return rest[:rest.index("\n\n---\n\n")] if "\n\n---\n\n" in rest else rest


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

    def test_gaps_are_worked_but_their_announcement_is_budgeted(self):
        """This reverses the original rule, and the reversal was earned.

        The first version said to declare every step the facts could not settle.
        A real reading then announced three of ten steps unsupported — D9,
        Jaimini, transit — which reads as a broken machine rather than an honest
        one. `answer_plan.MUST_SAY_LIMIT` had already settled this for the
        retrieval lane at two disclosures, for the same reason: past the second
        caveat a reader stops reading caveats and discounts the whole answer.

        The step is still worked, and the gap still costs confidence. What
        changed is whether the seeker is told."""
        block = method_block(constitution_for("domain.career"))
        assert "Work every step" in block
        assert "at most two" in block


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


# `TestScopedChart` lived here and is deliberately gone. It asserted the
# four-block layout - CHART FRAMEWORK / PRIMARY EVIDENCE / COMPUTED PERIODS /
# WIDER CHART - which `fact_table.render_table` replaced with one table after a
# reading built an entire chart out of transit positions. What those tests
# checked (relevance marking, subject-versus-location, nothing withheld) is now
# checked in `tests/council/test_fact_table.py` against the shape that shipped.


def _state(question="when will I marry?", **kw):
    s = initial_state(question, query_time=WHEN)
    s["koonji_domain"] = kw.pop("koonji_domain", "domain.relationship")
    s.update(kw)
    return s


@pytest.fixture(scope="module")
def chart_state():
    from rishivan.chartstate.build import build_chart_state
    return build_chart_state(compute_chart(BIRTH), when=WHEN)


class TestNoFalsePrecision:
    """A predicted event gets a month, never a day.

    Astrology is a calculated inference, and `2027-03-29` asserts a confidence
    the method cannot carry. The competitor product understood this: its prose
    says "between November 2026 and September 2027" and "late 2026", and the only
    day-level dates it prints are transit boundaries in its reference footer.

    The exact dates stay in the FACTS blocks. They are inputs - the model needs
    them to reason without drifting, and `ground_truth_rules` needs them to stop
    it inventing any. Only the granularity of the reply changes.
    """

    def test_the_reply_rounds_predicted_dates_to_months(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        block = prompt[prompt.index("OUTPUT"):]
        assert "month and the year" in block or "month and year" in block

    def test_day_precision_on_an_event_is_forbidden(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        block = prompt[prompt.index("OUTPUT"):]
        assert "never a day" in block.lower()

    def test_the_facts_keep_their_exact_dates(self, facts):
        """Rounding the inputs would let the model drift, and would break the
        anti-invention rule that depends on verbatim copying."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        assert "2027-02-12" in prompt  # an antardasha boundary, to the day

    def test_it_explains_why_the_inputs_are_exact_and_the_output_is_not(self, facts):
        """Otherwise the two rules read as a contradiction and the model picks
        one at random."""
        prompt = build_direct_prompt(_state(chart_facts=facts))
        block = prompt[prompt.index("OUTPUT"):]
        assert "reason" in block.lower()

    def test_computed_clock_windows_keep_their_exact_times(self, facts):
        """Rahu Kaal and muhurta are arithmetic for a stated date, not claims
        about a life. `ground_truth_rules` exists because the model got those
        wrong in production, and a blanket rounding rule would undo it."""
        prompt = build_direct_prompt(_state(chart_facts=facts))
        block = prompt[prompt.index("OUTPUT"):]
        assert "Rahu Kaal" in block or "clock time" in block

    def test_guarantee_language_is_forbidden_outright(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        lowered = prompt.lower()
        assert "guarantee" in lowered
        assert "calculated inference" in lowered or "not a guarantee" in lowered

    def test_the_ledger_rounds_too(self, facts):
        """It is part of the answer the seeker reads, not a debug panel."""
        prompt = build_direct_prompt(_state(chart_facts=facts))
        block = prompt[prompt.index("ASTRO REFERENCE"):]
        assert "Nov 2026" in block or "month" in block.lower()


class TestTheOutputShape:
    """Rewritten after comparing against a competitor product.

    Ours led with ten numbered method paragraphs and reached the answer eleventh,
    each step opening on the method itself — "Marital harmony is evaluated
    through the interaction between the Lagna and 7th house occupants". Theirs
    opened: "The promotion comes between November 2026 and September 2027, not
    before. Nothing lands in these next three months, so stop reading the current
    silence as a rejection."

    Same underlying craft; ours was unreadable. Both faults were mine: I ordered
    the method before the answer, and I asked for the principle rather than the
    consequence.
    """

    def test_the_answer_must_come_first(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        block = prompt[prompt.index("OUTPUT"):]
        assert "first sentence" in block.lower()

    def test_it_asks_what_will_not_happen(self, facts):
        """The competitor's "not before … nothing lands in these next three
        months" is what makes a forecast falsifiable and reassuring at once."""
        block = build_direct_prompt(_state(chart_facts=facts))
        assert "will NOT" in block or "will not happen" in block

    def test_it_demands_consequences_not_principles(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        block = prompt[prompt.index("OUTPUT"):]
        assert "consequence" in block.lower()

    def test_it_forbids_narrating_the_method(self, facts):
        """The steps are how the reading is reached, not what it looks like -
        the same distinction the retrieval lane's seven movements made."""
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "never write" in prompt.lower()
        assert "is evaluated through" in prompt

    def test_the_method_block_says_the_steps_are_working_not_output(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        method = prompt[prompt.index("READING METHOD"):prompt.index("STOP AND READ")]
        assert "working" in method.lower() or "do not appear" in method.lower()

    def test_the_evidence_ledger_is_required(self, facts):
        """The competitor's "Astro Reference" footer, which is a better answer to
        the citation problem than dropping the panel was: it cites the CHART, not
        a book, so every line is checkable against the computed facts."""
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "ASTRO REFERENCE" in prompt

    def test_the_ledger_format_pairs_a_factor_with_a_consequence(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        block = prompt[prompt.index("ASTRO REFERENCE"):]
        assert "factor" in block.lower()
        assert "consequence" in block.lower()

    def test_divisional_charts_get_plain_names_in_the_prose(self, facts):
        """"D10" means nothing to a seeker; "career chart" does. The competitor
        used the plain name in prose and the D-code only in its footer."""
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "career chart" in prompt
        assert "birth chart" in prompt

    def test_sanskrit_is_confined_to_the_reference_block(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        block = prompt[prompt.index("OUTPUT"):]
        assert "gloss" in block.lower() or "plain English" in block

    def test_the_falsifier_survives_the_rewrite(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert "falsif" in prompt.lower()


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
        assert "Settle the promise before any date" in prompt

    def test_certainty_is_forbidden_for_dated_claims_not_only_for_health(self, facts):
        """The old rule covered health and death only, and the model wrote "You
        will receive your major career promotion" with a peak window."""
        prompt = build_direct_prompt(_state(
            chart=compute_chart(BIRTH), chart_facts=facts,
        ))
        lowered = prompt.lower()
        assert "will happen" in lowered or "never state that an event will" in lowered


# `TestPlanetaryCondition` lived here and is deliberately gone. It asserted a
# separate PLANETARY CONDITION block carrying dignity, strength, combustion and
# aspects with no sign and no house — which is exactly why a reading joined those
# judgements to the wrong planets and wrote "Venus debilitated in Virgo" about a
# chart whose natal Venus is exalted in Pisces. Those columns are now part of the
# single table, and `tests/council/test_fact_table.py` asserts them there.


class TestBuildDirectPrompt:
    def test_the_blocks_appear_in_order(self, facts):
        prompt = build_direct_prompt(_state(chart_facts=facts))
        order = [
            "expert Vedic (Jyotish) astrologer",
            "READING METHOD",
            "THE CHART",
            "ASTRO REFERENCE",
            "THE QUESTION",
        ]
        positions = [prompt.index(marker) for marker in order]
        assert positions == sorted(positions), prompt[:400]

    def test_the_output_header_is_unambiguous(self, facts):
        """The method block used to refer to "the OUTPUT section", so
        `index("OUTPUT")` found the reference rather than the header - which made
        an ordering assertion pass or fail for the wrong reason."""
        prompt = build_direct_prompt(_state(chart_facts=facts))
        assert prompt.count("OUTPUT") == 1

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

    def test_an_admitted_varga_is_rendered_from_the_chart(self, facts):
        """The filter must key on the withheld list, not on being a varga.

        Rendered from the chart by `_varga_block` rather than from the fact list:
        `chart_natal_node` appends varga facts to `chart_facts` AND `_varga_block`
        renders the same divisions, so keeping both printed every divisional
        placement twice."""
        from rishivan.varga.confidence import BirthConfidence
        from rishivan.varga.select import VargaSelection

        prompt = build_direct_prompt(_state(
            chart_facts=facts,
            chart=compute_chart(BIRTH),
            vargas=VargaSelection(
                selected=("D9",), withheld=(),
                confidence=BirthConfidence.MINUTE,
            ),
        ))
        assert "(D9)" in prompt
        assert "DIVISIONAL CHARTS" in prompt

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


class TestTheProfileDrivesTheFacts:
    """The prompt now carries what the question needs, and not the rest.

    Before this, all four question kinds received an identical sixty-fact prompt.
    A date question got a ten-year dasha forecast and no panchang, so it answered
    "late 2026 or early 2027" to a question about tomorrow.
    """

    def _prompt(self, question, domain, facts, **kw):
        state = _state(question, koonji_domain=domain, chart_facts=facts, **kw)
        return build_direct_prompt(state)

    def test_a_date_question_gets_a_panchang_for_that_date(self, facts):
        prompt = self._prompt(
            "can I travel foreign tomorrow?", "domain.travel", facts,
            chart=compute_chart(BIRTH),
        )
        assert "Rahu Kaal" in prompt
        # WHEN is 2026-08-25, so "tomorrow" is the 26th - not today's date.
        assert "2026-08-26" in prompt

    def test_a_date_question_gets_tara_and_chandra_bala(self, facts):
        prompt = self._prompt(
            "can I travel foreign tomorrow?", "domain.travel", facts,
            chart=compute_chart(BIRTH),
        )
        assert "Tara bala" in prompt
        assert "Chandra bala" in prompt

    def test_a_date_question_gets_no_ten_year_forecast(self, facts):
        """What produced the wrong answer."""
        prompt = self._prompt(
            "can I travel foreign tomorrow?", "domain.travel", facts,
            chart=compute_chart(BIRTH),
        )
        assert "Antardashas within the following" not in prompt

    def test_a_character_question_gets_no_transits(self, facts):
        prompt = self._prompt(
            "what is my personality like?", "domain.temperament", facts,
            chart=compute_chart(BIRTH),
        )
        assert "TRANSITS NOW" not in prompt
        assert "Sade sati" not in prompt

    def test_a_timing_question_gets_transits_and_forward_periods(self, facts):
        prompt = self._prompt(
            "when will I get married?", "domain.relationship", facts,
            chart=compute_chart(BIRTH),
        )
        assert "TRANSITS NOW" in prompt
        assert "Antardashas within the following" in prompt

    def test_a_timing_question_gets_no_panchang(self, facts):
        prompt = self._prompt(
            "when will I get married?", "domain.relationship", facts,
            chart=compute_chart(BIRTH),
        )
        # "Rahu Kaal" also appears in the OUTPUT granularity carve-out, so
        # assert on the block heading rather than the phrase.
        assert "DAILY WINDOWS FOR" not in prompt

    def test_the_three_kinds_produce_genuinely_different_prompts(self, facts):
        """Scoping that is wired but inert is the failure mode this replaces,
        arriving one layer further in."""
        kw = dict(facts=facts, chart=compute_chart(BIRTH))
        a = self._prompt("when will I get married?", "domain.relationship", **kw)
        b = self._prompt("can I travel foreign tomorrow?", "domain.travel", **kw)
        c = self._prompt("what is my personality like?", "domain.temperament", **kw)
        assert len({a, b, c}) == 3
        # And the character prompt must be the smallest of the three.
        assert len(c) < len(a)
        assert len(c) < len(b)

    def test_there_is_exactly_one_planetary_table(self, facts):
        prompt = self._prompt(
            "when will I get married?", "domain.relationship", facts,
            chart=compute_chart(BIRTH), chart_state=None,
        )
        assert len([ln for ln in prompt.splitlines() if "PLANET" in ln]) == 1

    def test_the_old_five_block_layout_is_gone(self, facts):
        prompt = self._prompt(
            "when will I get married?", "domain.relationship", facts,
            chart=compute_chart(BIRTH),
        )
        for banned in ("CHART FRAMEWORK", "PRIMARY EVIDENCE FOR THIS QUESTION",
                       "WIDER CHART", "PLANETARY CONDITION"):
            assert banned not in prompt

    def test_unavailable_evidence_is_declared_once(self, facts):
        """So a gap is stated rather than discovered per step, and the model does
        not pad the step it cannot support."""
        prompt = self._prompt(
            "when will I get married?", "domain.relationship", facts,
            chart=compute_chart(BIRTH),
        )
        assert "EVIDENCE NOT AVAILABLE" in prompt
        assert "Jaimini" in prompt

    def test_the_profile_reason_is_not_in_the_prompt(self, facts):
        """It is for the trace and for a reviewer, not for the model - telling it
        which bundles were selected invites it to reason about our plumbing."""
        prompt = self._prompt(
            "when will I get married?", "domain.relationship", facts,
            chart=compute_chart(BIRTH),
        )
        assert "fact bundles" not in prompt
