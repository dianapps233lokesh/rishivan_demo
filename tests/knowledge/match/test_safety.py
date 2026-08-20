"""What may be shown, and to which question.

Eight Rishis §9: "Never diagnose a disease, predict death as certainty, prescribe
treatment." BPHS says these things plainly and the verses belong in the rule base -- the
constraint is on presentation. Every case here comes from a real match on a real chart.
"""

from types import SimpleNamespace

from rishivan.knowledge.match.safety import (
    sensitivities,
    question_admits,
    withhold_reasons,
)


def rule(statement="", translation=""):
    return SimpleNamespace(
        effects=[{"polarity": "negative", "statement": statement}],
        source={"translation": translation},
    )


def test_a_death_claim_is_detected():
    assert "death" in sensitivities(
        rule("Death will certainly occur due to worms or insects or leprosy")
    )


def test_a_named_disease_is_detected():
    assert "diagnosis" in sensitivities(rule("Death is caused by swelling or tumours"))


def test_intimate_content_is_detected():
    """BPHS 20.9 rates the shape of the querent's future wife's breasts, and it answered a
    question about her health."""
    assert "intimate" in sensitivities(rule("wife has hard and prominent breasts"))


def test_the_source_verse_counts_not_only_the_effect():
    """An effect can read innocuously while the verse it came from does not -- BPHS
    46.25-31's "Knowledge about one's father" sits inside a verse about the manner of
    death."""
    assert "death" in sensitivities(
        rule("a neutral outcome", "the death will occur due to poison")
    )


def test_an_ordinary_rule_carries_no_sensitivity():
    assert sensitivities(rule("the native will be wealthy")) == set()


def test_a_marriage_question_does_not_admit_death_claims():
    """The measured failure this exists to stop: "will my marriage be happy and will my
    wife be healthy?" returned four rules predicting the manner of the querent's death."""
    question = "will my marriage be happy and will my wife be healthy?"
    assert not question_admits("death", question)
    assert withhold_reasons(
        rule("Death will certainly occur due to worms"), question
    ) == ["death", "diagnosis"]


def test_a_general_health_question_still_does_not_admit_death_claims():
    """"Healthy" is not a request to be told how you will die -- least of all when the
    question is about someone else's health. The narrower gate is the honest one."""
    assert not question_admits("death", "will my wife be healthy?")


def test_an_explicit_longevity_question_does_admit_them():
    """Gated, not suppressed. Someone who asks this is owed the tradition's answer."""
    for question in ("how long will I live?", "when will I die?", "what is my longevity?"):
        assert question_admits("death", question), question


def test_a_health_question_admits_a_diagnosis_claim():
    assert question_admits("diagnosis", "what does my chart say about my health?")


def test_a_wealth_question_admits_neither():
    for sensitivity in ("death", "diagnosis", "intimate"):
        assert not question_admits(sensitivity, "will I be wealthy?")


def test_an_unclassified_category_is_always_admissible():
    """The gate must not become a default-deny on categories nobody defined."""
    assert question_admits("not-a-category", "anything at all")


def test_an_empty_question_admits_nothing_sensitive():
    """A missing question is not consent."""
    for sensitivity in ("death", "diagnosis", "intimate"):
        assert not question_admits(sensitivity, "")
