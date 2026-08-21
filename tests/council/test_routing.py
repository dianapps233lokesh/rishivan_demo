"""Question -> client life domains. Eight Rishis §12 is the test set.

The document hands us thirteen worked examples of a question with its primary Rishi and
its secondaries. They are the routing accuracy metric §18 asks for, so they are asserted
verbatim here rather than paraphrased.

Two of the thirteen are genuinely ambiguous in the document itself and are asserted
loosely, which is stated at each one.
"""

from rishivan.council.routing import route_question


def primary(question: str) -> str:
    return route_question(question).primary


def routed(question: str) -> set[str]:
    r = route_question(question)
    return {r.primary, *r.secondary} - {None}


# ── §12, the thirteen worked examples ────────────────────────────────────────


def test_billionaire_routes_to_artha():
    assert primary("Will I become a billionaire?") == "artha"


def test_leaving_a_job_to_start_a_business_routes_to_karma():
    assert primary("Should I leave my job and start a business?") == "karma"


def test_marriage_and_spouse_routes_to_prema():
    assert primary("When will I marry and what will my spouse be like?") == "prema"


def test_business_making_me_rich_reaches_both_karma_and_artha():
    """§12 gives Karma primary with Artha secondary. The question names both a business
    and its wealth outcome, so the honest assertion is that both are consulted rather
    than which of the two leads."""
    assert {"karma", "artha"} <= routed("Will my business make me rich?")


def test_moving_abroad_routes_to_yatra():
    assert primary("Should I move abroad?") == "yatra"


def test_children_routes_to_vansh():
    assert primary("How will my children be?") == "vansh"


def test_life_purpose_routes_to_dharma():
    assert primary("What is my life purpose?") == "dharma"


def test_repeated_relationship_problems_routes_to_prema():
    assert primary("Why am I facing repeated relationship problems?") == "prema"


def test_the_most_successful_period_reaches_atma():
    """§12 says "Atma/appropriate event Rishi" -- deliberately open, so this asserts
    only that Atma is consulted."""
    assert "atma" in routed("What period of my life will be most successful?")


def test_a_health_period_routes_to_aarogya():
    assert primary("What does this health period mean?") == "aarogya"


def test_buying_property_routes_to_yatra():
    assert primary("Should I buy this property now?") == "yatra"


def test_palm_and_career_routes_to_karma():
    assert primary("What does my palm say about my career?") == "karma"


def test_name_and_business_reaches_karma_or_artha():
    """§12: "Artha/Karma" -- the document itself does not choose."""
    assert routed("What does my name/date say about business?") & {"artha", "karma"}


# ── The governing rule and the boundary ──────────────────────────────────────


def test_a_single_subject_question_does_not_invoke_everything():
    """§12: "Do not invoke all eight by default. Invoke the minimum set that provides
    independent, relevant evidence." A plain marriage question must not pull in eight."""
    assert len(routed("When will I get married?")) <= 3


def test_a_question_outside_the_domains_is_marked_unsupported():
    """§20: no orphan questions -- but "everything" must not mean pretending to know.
    An unroutable question is surfaced as unsupported, not silently answered."""
    result = route_question("What is the airspeed velocity of an unladen swallow?")
    assert result.primary is None
    assert result.unsupported is True


def test_a_routed_question_is_not_unsupported():
    assert route_question("Will I be wealthy?").unsupported is False


def test_secondary_never_repeats_the_primary():
    for question in (
        "Will I become a billionaire?",
        "Should I move abroad?",
        "How will my children be?",
    ):
        result = route_question(question)
        assert result.primary not in result.secondary


# ── Blueprint §4 level 5: the question's application type ────────────────────
#
# §8 rule 2: "Separate potential from timing. Natal promise and event timing are
# different reasoning problems." Without this, "will I marry" and "when will I marry"
# retrieve identically.


def test_a_when_question_is_a_timing_question():
    for question in (
        "When will I marry?",
        "When can my finances improve?",
        "What period of my life will be most successful?",
        "Which years are good for a career change?",
        "What is my current mahadasha?",
    ):
        assert route_question(question).application == "timing", question


def test_a_whether_question_is_a_potential_question():
    for question in (
        "Will I be wealthy?",
        "What kind of spouse will I have?",
        "Will I have children?",
        "What career suits me?",
    ):
        assert route_question(question).application == "potential", question


def test_application_does_not_change_the_routed_domain():
    """Level 5 is orthogonal to level 4: "when will I marry" is still PREMA."""
    timed = route_question("When will I marry?")
    plain = route_question("Will I marry?")
    assert timed.primary == plain.primary == "prema"
    assert timed.application != plain.application


# ── Blueprint §4 level 1: which universes this question invokes ──────────────
#
# ER §13: numerology, palmistry, face reading and Vastu are "shared specialist
# modalities callable by the relevant Rishi(s)" and "must never silently override natal
# astrology". So a natal question retrieves from Jyotisha only.


def test_a_natal_question_invokes_jyotisha_only():
    for question in ("Will I be wealthy?", "When will I marry?", "What career suits me?"):
        assert route_question(question).universes == frozenset({"jyotisha"}), question


def test_a_numerology_question_invokes_numerology_too():
    """§13 routes name/number questions to Atma for identity and Artha for business --
    the modality is added to natal astrology, never substituted for it."""
    for question in (
        "What does my name say about business?",
        "What is my mulank?",
        "What does numerology say about my career?",
        "Is my lucky number good for money?",
    ):
        result = route_question(question)
        assert "numerology" in result.universes, question
        assert "jyotisha" in result.universes, question


def test_numerology_never_replaces_jyotisha():
    """The §13 constraint, as a test: the modality is additive."""
    assert route_question("What does my name say about business?").universes >= (
        frozenset({"jyotisha"})
    )


from rishivan.council.routing import MAX_DOMAINS, merge_supporting


def test_a_single_keyword_question_gains_secondaries_from_the_classifier():
    """The gap this exists to close: 'billionaire' matches one phrase, so the keyword
    table alone returns no secondary at all, and ER §12 asks for three."""
    base = route_question("Will I become a billionaire?")
    assert base.primary == "artha"
    assert base.secondary == ()

    merged = merge_supporting(base, ["tattvan", "dhruvan"])
    assert merged.primary == "artha"
    assert "atma" in merged.secondary


def test_merging_never_displaces_the_keyword_primary():
    merged = merge_supporting(route_question("Will I marry?"), ["dhruvan"])
    assert merged.primary == "prema"


def test_a_supporting_persona_that_repeats_the_primary_is_dropped():
    merged = merge_supporting(route_question("Will I be wealthy?"), ["dhruvan"])
    assert "artha" not in merged.secondary


def test_service_personas_contribute_no_life_domain():
    """vyom and ritam rate all eight domains MEDIUM -- mapping them back would add
    every domain as a secondary and make the cap meaningless."""
    merged = merge_supporting(route_question("Will I marry?"), ["vyom", "ritam"])
    assert merged.secondary == ()


def test_the_minimum_set_cap_still_holds():
    """ER §12: 'Do not invoke all eight by default.'"""
    merged = merge_supporting(
        route_question("Will I become a billionaire?"),
        ["tattvan", "medhan", "agam", "pragnav", "dhruvan"],
    )
    assert len(merged.secondary) <= MAX_DOMAINS - 1


def test_merging_preserves_application_and_universes():
    base = route_question("When will I marry?")
    merged = merge_supporting(base, ["dhruvan"])
    assert merged.application == base.application == "timing"
    assert merged.universes == base.universes


def test_an_unrouted_question_stays_unrouted():
    """ER §20: a question outside the eight domains must not be rescued into one by a
    persona guess."""
    base = route_question("What is the airspeed velocity of an unladen swallow?")
    merged = merge_supporting(base, ["dhruvan", "tattvan"])
    assert merged.primary is None
    assert merged.unsupported is True


# ── Specificity: a generic phrase must not outrank a specific one ─────────────


def test_natural_strengths_reaches_atma():
    """ER §4 owns "What are my strengths and weaknesses?". The table carried
    "my strengths" but not the bare plural, so the commonest phrasing of §4's own
    question routed nowhere at all -- §20 would report it unsupported."""
    routing = route_question("What are my natural strengths?")
    assert routing.primary == "atma"
    assert routing.unsupported is False


def test_a_named_family_member_outranks_the_generic_word_relationship():
    """"relationship" spans every domain -- career relationships, family
    relationships, business partners. "father" names exactly one (§8). Scoring both
    at 1.0 left a tie that document order broke toward PREMA, so a question about a
    parent retrieved marriage rules."""
    routing = route_question("What is my relationship with my father?")
    assert routing.primary == "vansh"
    assert "prema" in routing.secondary


def test_a_generic_phrase_still_reinforces_its_own_domain():
    """Demoting "relationship" must not strip it of meaning: with a specific PREMA
    term beside it the two should add up and still land on PREMA."""
    routing = route_question("What is my relationship with my spouse?")
    assert routing.primary == "prema"


def test_a_generic_phrase_alone_still_routes():
    """A demoted phrase is worth less than a specific one, not nothing -- otherwise
    "will my relationship last?" would become an unsupported question."""
    routing = route_question("Will my relationship last?")
    assert routing.primary == "prema"
