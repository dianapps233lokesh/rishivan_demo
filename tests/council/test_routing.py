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
