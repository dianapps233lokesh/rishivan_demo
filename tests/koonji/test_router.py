"""The question layer: text in, a filter out, and the gates in between.

Every test here is about one of two failure modes, because those are the only
two this layer can have:

  * it filters too much - a relevant rule is never considered, and the answer
    reads perfectly well without it, so nobody finds out;
  * it filters too little - the reading is padded with material from domains
    the question was not about, which is how a system sounds knowledgeable
    about everything.
"""

from datetime import datetime

import pytest

from rishivan.koonji.question import (
    CLARIFY_BELOW,
    REQUIRED_INPUTS,
    SEED_FLAG_REGISTRY,
    SERVABLE_MODES,
    InputKind,
    Mode,
    QuestionSpec,
    TurnType,
    resolve_missing,
)
from rishivan.koonji.router import (
    DOMAIN_KEYWORDS,
    GENERIC_PHRASES,
    INCIDENTAL_DOMAIN_WEIGHT,
    MAX_DOMAINS,
    parse,
    resolve_time_scope,
    retrieval_plan,
    score_domains,
)

NOW = datetime(2026, 8, 25, 12, 0)
HAVE_CHART = {InputKind.BIRTH_PROFILE}


def spec(text: str, **kw) -> QuestionSpec:
    kw.setdefault("available", HAVE_CHART)
    return parse(text, now=NOW, **kw)


class TestTurnType:
    @pytest.mark.parametrize("text,expected", [
        ("hi", TurnType.SOCIAL),
        ("hi there", TurnType.SOCIAL),
        ("thanks!", TurnType.SOCIAL),
        ("how does this work?", TurnType.META),
        ("who are you?", TurnType.META),
        ("why?", TurnType.FOLLOWUP),
        ("tell me more", TurnType.FOLLOWUP),
        ("which verse does that come from?", TurnType.DRILLDOWN),
        ("actually my birth time is 4:15", TurnType.CORRECTION),
        ("that didn't happen", TurnType.CHALLENGE),
        ("will I be wealthy?", TurnType.NEW_QUESTION),
    ])
    def test_turn_types(self, text, expected):
        assert spec(text).turn_type is expected

    def test_a_courtesy_in_front_of_a_question_is_still_a_question(self):
        """`_SOCIAL` is anchored at both ends for this. Matching the greeting
        alone would drop the question that follows it."""
        assert spec("thanks, but when will I marry?").turn_type is TurnType.NEW_QUESTION

    def test_a_challenge_outranks_the_followup_it_looks_like(self):
        assert spec("you were wrong, why?").turn_type is TurnType.CHALLENGE


class TestDomainRouting:
    @pytest.mark.parametrize("text,domain", [
        ("will I be wealthy?", "domain.wealth"),
        ("when will I get a promotion?", "domain.career"),
        ("when will I marry?", "domain.relationship"),
        ("will we have children?", "domain.progeny"),
        ("how are my studies going to go?", "domain.education"),
        ("is my health going to hold up?", "domain.health"),
        ("will I settle abroad?", "domain.travel"),
        ("will I buy property?", "domain.property"),
        ("what is my personality like?", "domain.temperament"),
        ("what is my spiritual path?", "domain.spiritual"),
    ])
    def test_the_obvious_questions_route_where_they_should(self, text, domain):
        assert domain in spec(text).routing.domains

    def test_routing_names_the_phrases_that_produced_it(self):
        """A routing complaint has to be answerable with a diff against a table,
        not with a shrug about model behaviour."""
        routing = spec("when will I get married?").routing
        assert routing.matched["domain.relationship"]
        assert "married" in routing.reason

    def test_a_multi_word_phrase_outranks_a_single_word(self):
        scores, _ = score_domains("i want to have a child")
        assert scores["domain.progeny"] > 1.0

    def test_a_generic_word_scores_below_a_specific_one(self):
        """"work" belongs to no domain in particular. It should not beat a term
        its domain owns outright."""
        scores, _ = score_domains("will my work at the university pay off")
        assert scores["domain.education"] > scores["domain.career"]

    def test_generic_phrases_are_all_real_keywords(self):
        """A typo in `GENERIC_PHRASES` demotes nothing and is invisible."""
        every = {p for phrases in DOMAIN_KEYWORDS.values() for p in phrases}
        assert GENERIC_PHRASES <= every

    def test_no_more_than_three_domains(self):
        s = spec("will my career, my money, my marriage and my health improve?")
        assert len(s.routing.domains) <= MAX_DOMAINS

    def test_an_unmatched_question_routes_nowhere_rather_than_guessing(self):
        s = spec("what does the sky look like today?")
        assert s.routing.domains == []
        assert s.ambiguity_note

    def test_word_boundaries_are_respected(self):
        """"ill" inside "will" routed half the corpus into domain.health."""
        assert "domain.health" not in spec("will I be happy?").routing.domains
        assert "domain.progeny" not in spec("for that reason").routing.domains


class TestMode:
    @pytest.mark.parametrize("text,mode", [
        ("will I be rich?", Mode.NATAL_PREDICTIVE),
        ("what am I like?", Mode.NATAL_DESCRIPTIVE),
        ("what's my next good period?", Mode.TIMING_ONLY),
        ("are we compatible?", Mode.COMPATIBILITY),
        ("what's an auspicious date to start my business?", Mode.MUHURTA),
        ("what does BPHS say about the 7th lord?", Mode.KNOWLEDGE),
        ("what is my lucky number?", Mode.MODALITY),
        ("give me a full reading", Mode.LIFE_MAP),
        ("I'm not sure of my birth time, can you rectify it?", Mode.RECTIFICATION),
    ])
    def test_modes(self, text, mode):
        assert spec(text).mode is mode

    def test_a_descriptive_question_gets_no_time_scope(self):
        """A natal promise is not an event. Attaching a window to a "what am I
        like" question invites a timing claim nothing supports."""
        assert getattr(spec("what am I like?").payload, "time_scope", None) is None

    def test_a_timing_question_gets_one(self):
        assert spec("when will I marry?").payload.time_scope is not None


class TestTimeScope:
    def test_relative_phrases_resolve_to_dates_here_and_only_here(self):
        scope = resolve_time_scope("in the next 2 years", NOW)
        assert scope.start == "2026-08-25"
        assert scope.end == "2028-08-25"
        assert scope.user_phrase == "next 2 years"

    def test_next_year_is_a_calendar_year(self):
        scope = resolve_time_scope("will I marry next year?", NOW)
        assert (scope.start, scope.end) == ("2027-01-01", "2027-12-31")

    def test_an_absolute_year_is_taken_literally(self):
        scope = resolve_time_scope("will it happen by 2029?", NOW)
        assert (scope.start, scope.end) == ("2029-01-01", "2029-12-31")

    def test_a_word_count_resolves(self):
        assert resolve_time_scope("in the next few months", NOW).end == "2026-11-25"

    def test_month_arithmetic_clamps_rather_than_rolling_over(self):
        """31 Jan plus one month is the end of February, not the 3rd of March."""
        scope = resolve_time_scope("next 1 months", datetime(2026, 1, 31))
        assert scope.end == "2026-02-28"

    def test_no_phrase_means_no_scope_rather_than_a_default(self):
        """"no horizon given" and "a horizon of three years" have to stay
        distinguishable in the stored spec."""
        assert resolve_time_scope("will I be wealthy?", NOW) is None


class TestFlags:
    @pytest.mark.parametrize("text,flag", [
        ("should I resign?", "safety.decision_request"),
        ("when will I die?", "safety.mortality"),
        ("do I have cancer?", "safety.medical"),
        ("which stock should I buy?", "safety.financial_specific"),
        ("I'm desperate, when will this end?", "handling.emotional_charge"),
        ("prove it", "handling.skeptical_framing"),
        ("just tell me briefly", "handling.requests_brevity"),
        ("what if I moved?", "structure.hypothetical"),
    ])
    def test_flags(self, text, flag):
        assert spec(text).has_flag(flag)

    def test_every_flag_the_router_can_emit_is_in_the_registry(self):
        """An unregistered flag has no policy row behind it, so it silently does
        nothing - which is worse than not detecting it at all."""
        for text in ("should I resign?", "when will I die?", "I'm desperate",
                     "prove it", "what if I moved?", "urgent!"):
            for flag in spec(text).flags:
                assert flag.flag_id in SEED_FLAG_REGISTRY

    def test_a_flag_records_the_span_that_triggered_it(self):
        flag = next(f for f in spec("should I resign?").flags
                    if f.flag_id == "safety.decision_request")
        assert flag.evidence_span

    def test_a_refusing_flag_is_reported_as_such(self):
        assert spec("when will I die?").refused() == "safety.mortality"
        assert spec("will I be wealthy?").refused() is None

    def test_emotional_charge_does_not_touch_the_filter(self):
        """Tone is a narrative concern. An engine that bends its evidence to
        please people is a worse engine."""
        calm = spec("when will my career improve?")
        upset = spec("I'm exhausted, when will my career improve?")
        assert calm.routing.domains == upset.routing.domains
        assert calm.routing.min_domain_weight == upset.routing.min_domain_weight


class TestSubjects:
    def test_a_third_party_is_recorded_with_a_consent_requirement(self):
        refs = spec("will my wife change jobs?").subject_refs
        partner = next(r for r in refs if r.role == "partner")
        assert partner.consent_required

    def test_the_querent_is_always_a_subject(self):
        assert spec("will I be wealthy?").subject_refs[0].role == "self"

    def test_a_child_is_not_treated_as_a_consenting_adult_by_accident(self):
        child = next(r for r in spec("how will my son do?").subject_refs
                     if r.role == "child")
        assert child.label


class TestInputGates:
    def test_compatibility_needs_two_charts_whatever_the_router_thinks(self):
        """Derived from a table, not asked of the parser. A parser is unreliable
        about remembering this; a lookup is not."""
        s = spec("are we compatible?", available=HAVE_CHART)
        assert s.is_blocked()
        assert any(m.kind is InputKind.PARTNER_PROFILE for m in s.missing_inputs)

    def test_a_natal_question_with_a_chart_is_not_blocked(self):
        assert not spec("will I be wealthy?").is_blocked()

    def test_a_natal_question_without_one_is(self):
        assert parse("will I be wealthy?", now=NOW, available=set()).is_blocked()

    def test_every_mode_declares_its_inputs(self):
        """A mode missing from the table requires nothing, which is a silent way
        to serve a question that cannot be answered."""
        assert set(REQUIRED_INPUTS) == set(Mode)

    def test_the_query_moment_is_never_missing(self):
        s = spec("prashna: will it work out?")
        assert not any(m.kind is InputKind.QUERY_MOMENT for m in s.missing_inputs)

    def test_a_numerology_question_needs_a_name(self):
        s = spec("what does my name number say?")
        assert any(m.kind is InputKind.NAME_STRING for m in s.missing_inputs)


class TestConfidence:
    def test_a_bare_question_mark_asks_rather_than_answers(self):
        assert spec("?").parse_confidence < CLARIFY_BELOW

    def test_a_clear_question_does_not(self):
        assert spec("when will I get married?").parse_confidence >= CLARIFY_BELOW

    def test_a_greeting_is_confidently_a_greeting(self):
        assert spec("hello").parse_confidence == 1.0


class TestRetrievalPlan:
    def test_the_plan_carries_the_routed_domains(self):
        plan = retrieval_plan(spec("will I be wealthy?"))
        assert plan.domains == frozenset({"domain.wealth"})

    def test_an_unrouted_question_reads_the_whole_corpus(self):
        """None, not an empty set. An empty set retrieves nothing, and a router
        that matched no phrase must widen the read, never close it."""
        plan = retrieval_plan(spec("what does the sky look like today?"))
        assert plan.domains is None
        assert not plan.widen_if_empty

    def test_a_filtered_plan_is_allowed_to_widen(self):
        assert retrieval_plan(spec("will I be wealthy?")).widen_if_empty

    def test_a_life_map_drops_the_domain_filter_on_purpose(self):
        """It is the one mode whose question is "all of it"."""
        plan = retrieval_plan(spec("give me a full reading"))
        assert plan.domains is None

    def test_the_incidental_weight_threshold_is_applied(self):
        assert retrieval_plan(spec("will I be wealthy?")).min_domain_weight == (
            INCIDENTAL_DOMAIN_WEIGHT
        )

    def test_an_unfiltered_plan_has_no_threshold(self):
        """A threshold with no domain filter would do nothing but confuse a
        trace reader."""
        assert retrieval_plan(spec("hmm")).min_domain_weight == 0.0

    def test_widening_records_why(self):
        plan = retrieval_plan(spec("will I be wealthy?")).unfiltered()
        assert plan.domains is None
        assert not plan.widen_if_empty
        assert any("widened" in n for n in plan.notes)

    def test_the_plan_takes_its_clock_from_the_resolved_scope(self):
        plan = retrieval_plan(spec("will I marry in 2029?"))
        assert plan.when == datetime(2029, 1, 1)

    def test_statuses_default_to_production_only(self):
        assert retrieval_plan(spec("will I be wealthy?")).statuses == frozenset(
            {"production"}
        )


class TestServableModes:
    def test_every_servable_mode_can_be_reached_from_text(self):
        reachable = {
            spec(t).mode for t in (
                "will I be rich?", "what am I like?",
                "what's my next good period?", "give me a full reading",
            )
        }
        assert SERVABLE_MODES <= reachable

    def test_a_mode_with_no_corpus_behind_it_is_not_servable(self):
        for mode in (Mode.COMPATIBILITY, Mode.PRASHNA, Mode.MUHURTA,
                     Mode.KNOWLEDGE, Mode.MODALITY, Mode.RECTIFICATION):
            assert mode not in SERVABLE_MODES


class TestDeterminism:
    def test_the_same_question_parses_the_same_way_twice(self):
        """The whole reason this is not a model call."""
        a = spec("when will my career improve?")
        b = spec("when will my career improve?")
        assert a.model_dump() == b.model_dump()

    def test_resolve_missing_is_a_pure_function_of_mode_and_availability(self):
        s = spec("are we compatible?")
        assert resolve_missing(s, HAVE_CHART) == resolve_missing(s, HAVE_CHART)
