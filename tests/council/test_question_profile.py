"""Which facts a question needs, decided by a table rather than a model.

The gap this closes: nothing in the pipeline mapped question type to required
computations. `constitution` maps domain to HOUSES, which answers "which houses
matter for marriage" and not "what must be computed to rule on tomorrow". So
every question got the same sixty facts, and "Can I travel foreign tomorrow?" was
answered with dasha boundaries to 2060 — the reading used what it had.

Deterministic on purpose, matching `hierarchy_node`: "A classifier call here
would be one more thing to be irreproducible about." Three of the four decisions
were already keyword tables in this repo (`relative_day_offset`,
`mentions_panchang`, `koonji.router.parse`); the fourth is a table too.
"""

import pytest

from rishivan.council.question_profile import QuestionKind, profile_for
from rishivan.council.requirements.catalog import FLOOR


class TestQuestionKind:
    def test_a_when_question_is_a_timing_question(self):
        assert profile_for(
            "when will I get married?", koonji_domain="domain.relationship"
        ).kind is QuestionKind.WHEN_WILL

    def test_hindi_kab_also_reads_as_timing(self):
        assert profile_for(
            "shaadi kab hogi?", koonji_domain="domain.relationship"
        ).kind is QuestionKind.WHEN_WILL

    def test_can_i_plus_a_day_is_a_date_question(self):
        assert profile_for(
            "can I travel foreign tomorrow?", koonji_domain="domain.travel"
        ).kind is QuestionKind.OK_ON_DATE

    def test_a_character_question_is_neither(self):
        assert profile_for(
            "what is my personality like?", koonji_domain="domain.temperament"
        ).kind is QuestionKind.WHAT_IS_IT_LIKE

    def test_a_promise_question_is_treated_as_a_future_event_question(self):
        """"Will I be wealthy?" wants the yes AND the when. It was landing in
        WHAT_IS_IT_LIKE, which sends no forward periods, so the reading could
        establish a promise and then had nothing to time it against. Caught by
        running real questions through the table rather than by a test."""
        profile = profile_for("will I be wealthy?", koonji_domain="domain.wealth")
        assert profile.kind is QuestionKind.WHEN_WILL
        assert profile.needs("block.dasha.forward")

    def test_a_trailing_space_stops_will_i_firing_inside_a_word(self):
        """"willing", "willow". The space in "will i " is load-bearing."""
        assert profile_for(
            "am I willing to change?", koonji_domain="domain.temperament"
        ).kind is QuestionKind.WHAT_IS_IT_LIKE

    def test_an_either_or_question_is_a_choice(self):
        assert profile_for(
            "should I take the Delhi job or the Pune job?",
            koonji_domain="domain.career",
        ).kind is QuestionKind.WHICH_OPTION

    def test_the_default_is_the_least_committal_kind(self):
        """An unplaceable question must not be treated as a timing question -
        that is how a vague query acquires a date it never asked for."""
        assert profile_for(
            "hmm", koonji_domain="domain.temperament"
        ).kind is QuestionKind.WHAT_IS_IT_LIKE

    def test_longest_phrase_wins(self):
        """"day after tomorrow" must not be read as "tomorrow"."""
        assert profile_for(
            "is it good to travel day after tomorrow?",
            koonji_domain="domain.travel",
        ).day_offset == 2


class TestTheDay:
    def test_today_is_the_default(self):
        assert profile_for(
            "when will I marry?", koonji_domain="domain.relationship"
        ).day_offset == 0

    def test_tomorrow_is_read_from_the_question(self):
        assert profile_for(
            "can I travel foreign tomorrow?", koonji_domain="domain.travel"
        ).day_offset == 1

    def test_it_reuses_the_existing_parser(self):
        """`panchang.relative_day_offset` already handles English, Hindi and
        Devanagari. A second copy is a second thing to drift."""
        from rishivan.chart.panchang import relative_day_offset
        for phrase in ("kal", "परसों", "tonight", "day after tomorrow"):
            question = f"is it good to travel {phrase}?"
            assert profile_for(
                question, koonji_domain="domain.travel"
            ).day_offset == relative_day_offset(question)


class TestTheFloor:
    def test_the_floor_is_present_whatever_the_question(self):
        """A reading cannot be right without the placements, the house lords,
        their condition and the running period. A table that can drop them is a
        table that eventually will, and a missing fact is invisible in fluent
        prose."""
        for question, domain in (
            ("when will I marry?", "domain.relationship"),
            ("can I travel tomorrow?", "domain.travel"),
            ("what is my nature?", "domain.temperament"),
            ("this job or that one?", "domain.career"),
        ):
            profile = profile_for(question, koonji_domain=domain)
            for requirement in FLOOR:
                assert profile.needs(requirement.key), f"{question}: {requirement.key}"

    def test_the_floor_is_always_band_one(self):
        """The floor is what a verdict rests on. Demoted to corroboration it
        would still be present and would no longer be leading, which is the same
        failure with a subtler cause."""
        profile = profile_for("when will I marry?",
                              koonji_domain="domain.relationship")
        floor = {r.key for r in FLOOR}
        for requirement in profile.requirements.requires:
            if requirement.key in floor:
                assert requirement.priority == 1, requirement.key
                assert requirement.mandatory, requirement.key


class TestTheDomainDecidesTheFacts:
    """The gap this module was written to close and then did not.

    `koonji_domain` was accepted for two commits and used only to build the
    `reason` string, so a marriage timing question and a career timing question
    received byte-identical facts. A marriage reading therefore leant on general
    dasha strength and never once named the 7th lord's condition.
    """

    def test_marriage_and_career_ask_for_different_things(self):
        marriage = profile_for("when will I marry?",
                               koonji_domain="domain.relationship")
        career = profile_for("when will I be promoted?",
                             koonji_domain="domain.career")
        assert {r.key for r in marriage.requirements.requires} != {
            r.key for r in career.requirements.requires
        }

    def test_a_marriage_question_requires_the_seventh_house_and_its_lord(self):
        profile = profile_for("when will I marry?",
                              koonji_domain="domain.relationship")
        assert profile.needs("block.house.7")
        assert profile.needs("house.7.lord.house")
        assert profile.needs("planet.venus.dignity")

    def test_a_marriage_question_requires_the_navamsa_lords_not_just_the_navamsa(self):
        """"D9 confirmation" is a protocol step, not a dump of placements. The
        lane sent raw D9 positions and left the model to work out which lord
        mattered, which is where it started asserting agreement that was not
        there."""
        profile = profile_for("when will I marry?",
                              koonji_domain="domain.relationship")
        assert profile.needs("d9.house.1.lord.house")
        assert profile.needs("d9.house.7.lord.house")
        assert profile.needs("block.varga_confirms.d9")

    def test_a_career_question_requires_the_tenth_and_the_d10(self):
        profile = profile_for("when will I be promoted?",
                              koonji_domain="domain.career")
        assert profile.needs("block.house.10")
        assert profile.needs("d10.house.10.lord.house")
        assert not profile.needs("block.kuja_dosha")

    def test_the_protocol_step_travels_with_the_requirement(self):
        """A fact that serves no step is a fact somebody should justify, and a
        missing fact whose step is known reads as "step 5 was skipped" rather
        than "something was"."""
        profile = profile_for("when will I marry?",
                              koonji_domain="domain.relationship")
        for requirement in profile.requirements.requires:
            assert requirement.step >= 1, requirement.key


class TestRequirementsPerKind:
    def test_a_timing_question_gets_forward_periods_and_transits(self):
        profile = profile_for("when will I get married?",
                              koonji_domain="domain.relationship")
        assert profile.needs("block.dasha.forward")
        assert profile.needs("block.transits_slow")
        assert profile.needs("block.sade_sati")

    def test_a_timing_question_reaches_the_third_dasha_level(self):
        """An antardasha is ~18 months wide. `dasha.current_periods` has walked
        down to pratyantar since it was written and no prompt ever printed it."""
        profile = profile_for("when will I get married?",
                              koonji_domain="domain.relationship")
        assert profile.needs("block.dasha.pratyantar")

    def test_a_timing_question_does_not_get_a_panchang(self):
        """"When will I marry" is not answered by tomorrow's Rahu Kaal, and
        sending it invites the model to reach for it."""
        profile = profile_for("when will I get married?",
                              koonji_domain="domain.relationship")
        assert not profile.needs("block.panchang")
        assert not profile.needs("block.tara_bala")

    def test_a_date_question_gets_the_muhurta_facts(self):
        """The whole reason this module exists."""
        profile = profile_for("can I travel foreign tomorrow?",
                              koonji_domain="domain.travel")
        assert profile.needs("block.panchang")
        assert profile.needs("block.tara_bala")
        assert profile.needs("block.chandra_bala")

    def test_a_date_question_does_not_get_a_ten_year_dasha_forecast(self):
        """It was given one, and answered "late 2026 or early 2027" to a question
        about tomorrow."""
        profile = profile_for("can I travel foreign tomorrow?",
                              koonji_domain="domain.travel")
        assert not profile.needs("block.dasha.forward")

    def test_a_character_question_gets_no_timing_at_all(self):
        """A temperament reading timed against a transit becomes a forecast
        nobody asked for."""
        profile = profile_for("what is my personality like?",
                              koonji_domain="domain.temperament")
        assert not profile.needs("block.transits_slow")
        assert not profile.needs("block.dasha.forward")
        assert not profile.needs("block.panchang")
        assert profile.needs("block.yogas")

    def test_no_question_asks_for_everything(self):
        """Scoping that admits everything is scoping that is wired but inert."""
        from rishivan.council.requirements.catalog import catalogue

        everything = {r.key for e in catalogue().values() for r in e.requires}
        for question, domain in (
            ("when will I marry?", "domain.relationship"),
            ("can I travel tomorrow?", "domain.travel"),
            ("what is my nature?", "domain.temperament"),
        ):
            asked = {
                r.key
                for r in profile_for(question, koonji_domain=domain)
                .requirements.requires
            }
            assert asked < everything, question


class TestUnavailable:
    def test_a_prashna_reading_says_what_it_cannot_have(self):
        """Every one of these failed silently before. Tara bala came back Janma
        every time - the moment chart's Moon measured against itself - and a
        reading built real advice on it."""
        profile = profile_for("when will I get married?",
                              koonji_domain="domain.relationship",
                              has_birth_chart=False)
        assert profile.unavailable
        assert any("Vimshottari" in u for u in profile.unavailable)

    def test_a_prashna_reading_stops_asking_for_the_dasha(self):
        profile = profile_for("when will I get married?",
                              koonji_domain="domain.relationship",
                              has_birth_chart=False)
        assert not profile.needs("block.dasha.current")
        assert not profile.needs("block.dasha.forward")
        assert not profile.needs("block.tara_bala")

    def test_a_natal_reading_claims_nothing_missing_up_front(self):
        """What is genuinely uncomputable is now discovered while assembling the
        prompt - `_requirement_blocks` reports it against the protocol step it
        served - rather than asserted here as a constant. A hardcoded list said
        "Jaimini karakas and Upapada" on every question, including the ones that
        never asked for them."""
        profile = profile_for("what is my nature?",
                              koonji_domain="domain.temperament")
        assert profile.unavailable == ()


class TestReason:
    def test_the_profile_explains_itself(self):
        """It goes into the trace. A fact set nobody can account for is one
        nobody can correct."""
        profile = profile_for(
            "can I travel foreign tomorrow?", koonji_domain="domain.travel"
        )
        assert profile.reason
        assert "tomorrow" in profile.reason.lower() or "day" in profile.reason.lower()

    def test_the_reason_names_where_the_requirements_came_from(self):
        """Mongo or the built-in catalogue. A demo silently running on the
        fallback while somebody edits Atlas and sees nothing change is a
        confusing afternoon."""
        profile = profile_for("when will I marry?",
                              koonji_domain="domain.relationship")
        assert profile.requirements.source.value in profile.reason


class TestGapsFoundByProbingRealQuestions:
    """Both found by running two dozen realistic questions through the table and
    reading the routing, which the unit tests had not covered."""

    def test_a_panchang_question_is_a_date_question(self):
        """"What is the Rahu Kaal today?" was landing in WHAT_IS_IT_LIKE and so
        received no panchang — the purest panchang question there is, answered
        without one, because "what is the" matches no date phrase.
        `mentions_panchang` already existed and was never consulted."""
        profile = profile_for("What is the Rahu Kaal today?", koonji_domain="")
        assert profile.kind is QuestionKind.OK_ON_DATE
        assert profile.needs("block.panchang")

    def test_hora_and_muhurta_questions_route_the_same_way(self):
        for question in ("which hora is running now?",
                         "what is a good muhurta this week?"):
            assert profile_for(
                question, koonji_domain=""
            ).kind is QuestionKind.OK_ON_DATE, question

    def test_going_forward_is_a_timing_phrase(self):
        """"How is my health going forward?" got neither transits nor forward
        periods — a question with "going forward" in it, read as a question about
        character."""
        profile = profile_for(
            "How is my health going forward?", koonji_domain="domain.health"
        )
        assert profile.kind is QuestionKind.WHEN_WILL
        assert profile.needs("block.dasha.forward")
