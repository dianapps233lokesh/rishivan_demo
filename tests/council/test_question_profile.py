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

from rishivan.council.question_profile import (
    FLOOR, Bundle, QuestionKind, profile_for,
)


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
        assert Bundle.DASHA_FORWARD in profile.bundles

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
            bundles = profile_for(question, koonji_domain=domain).bundles
            assert FLOOR <= bundles, question

    def test_the_floor_names_what_it_names(self):
        assert FLOOR == frozenset({
            Bundle.NATAL_PLACEMENTS, Bundle.HOUSE_LORDS,
            Bundle.PLANET_CONDITION, Bundle.DASHA_CURRENT,
        })


class TestBundlesPerKind:
    def test_a_timing_question_gets_forward_periods_and_transits(self):
        bundles = profile_for(
            "when will I get married?", koonji_domain="domain.relationship"
        ).bundles
        assert Bundle.DASHA_FORWARD in bundles
        assert Bundle.TRANSITS_SLOW in bundles
        assert Bundle.SADE_SATI in bundles

    def test_a_timing_question_does_not_get_a_panchang(self):
        """"When will I marry" is not answered by tomorrow's Rahu Kaal, and
        sending it invites the model to reach for it."""
        bundles = profile_for(
            "when will I get married?", koonji_domain="domain.relationship"
        ).bundles
        assert Bundle.PANCHANG_FOR_DATE not in bundles
        assert Bundle.TARA_BALA not in bundles

    def test_a_date_question_gets_the_muhurta_facts(self):
        """The whole reason this module exists."""
        bundles = profile_for(
            "can I travel foreign tomorrow?", koonji_domain="domain.travel"
        ).bundles
        assert Bundle.PANCHANG_FOR_DATE in bundles
        assert Bundle.TARA_BALA in bundles
        assert Bundle.CHANDRA_BALA in bundles

    def test_a_date_question_does_not_get_a_ten_year_dasha_forecast(self):
        """It was given one, and answered "late 2026 or early 2027" to a question
        about tomorrow."""
        bundles = profile_for(
            "can I travel foreign tomorrow?", koonji_domain="domain.travel"
        ).bundles
        assert Bundle.DASHA_FORWARD not in bundles

    def test_a_character_question_gets_no_timing_at_all(self):
        """A temperament reading timed against a transit becomes a forecast
        nobody asked for."""
        bundles = profile_for(
            "what is my personality like?", koonji_domain="domain.temperament"
        ).bundles
        assert Bundle.TRANSITS_SLOW not in bundles
        assert Bundle.DASHA_FORWARD not in bundles
        assert Bundle.PANCHANG_FOR_DATE not in bundles
        assert Bundle.YOGAS in bundles

    def test_every_kind_produces_fewer_bundles_than_the_whole_menu(self):
        """Scoping that admits everything is scoping that is wired but inert."""
        whole = set(Bundle)
        for question, domain in (
            ("when will I marry?", "domain.relationship"),
            ("can I travel tomorrow?", "domain.travel"),
            ("what is my nature?", "domain.temperament"),
        ):
            assert profile_for(question, koonji_domain=domain).bundles < whole


class TestUnavailable:
    def test_it_names_what_the_question_wanted_and_cannot_have(self):
        """Declared once, so a gap is stated rather than discovered per step -
        and so the model does not substitute the facts it does have."""
        profile = profile_for(
            "when will I get married?", koonji_domain="domain.relationship"
        )
        assert profile.unavailable
        assert any("Jaimini" in u for u in profile.unavailable)

    def test_a_character_question_claims_no_missing_timing(self):
        profile = profile_for(
            "what is my nature?", koonji_domain="domain.temperament"
        )
        assert not any("transit" in u.lower() for u in profile.unavailable)


class TestReason:
    def test_the_profile_explains_itself(self):
        """It goes into the trace. A fact set nobody can account for is one
        nobody can correct."""
        profile = profile_for(
            "can I travel foreign tomorrow?", koonji_domain="domain.travel"
        )
        assert profile.reason
        assert "tomorrow" in profile.reason.lower() or "day" in profile.reason.lower()
