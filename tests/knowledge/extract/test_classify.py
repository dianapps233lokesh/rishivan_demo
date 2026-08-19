"""Triage routing — the decisions that cost money or lose content if wrong.

Every fixture below is real text from BPHS in `rishivan_dev_local`, not invented
prose, so a passing test means the classifier handles what the book actually says.
"""

import pytest

from app.knowledge.triage.classify import Destination, Verdict, classify
from app.knowledge.triage.signals import Signal, detect
from app.models.knowledge.item import ItemKind

CONDITIONAL = (
    "If the 8th Lord happens to be placed in the Ascendant the native will be "
    "bereft of bodily pleasures, be detractor of gods and Brahmins and will have "
    "wounds."
)
IMPLICIT = (
    "Planets situated in the visible half of the Zodiac give explicit results "
    "while the ones in the invisible half are known as giver of secret results."
)
FORMULA = (
    "One half of the summation of Uchcha Rashmi and Cheshta Rashmi is called "
    "Shubha Rashmi and if this is deducted from 8, the remainder is called "
    "Ashubha Rashmi."
)
RULE_WITH_REMEDY = (
    "if Venus is the lord of the 2nd or the 7th house, danger of death is there "
    "and to alleviate the evil effects, recitation of hymns in praise of Lord "
    "Shiva, charity of white cow and silver be resorted to and with the blessings "
    "of Lord Shiva, peace will undoubtedly, prevail."
)
INVOCATION = "Salutations to Lord Ganesha. O Maitreya, having heard this, Parasara spoke thus."


def test_explicit_conditional_routes_to_rule():
    assert classify(CONDITIONAL).destination is Destination.rule


def test_conditional_without_the_word_if_still_routes_to_rule():
    """BPHS 24.8 states a complete rule with no `if` anywhere. Requiring the keyword
    would silently discard a large share of the classical corpus."""
    assert Signal.conditional not in detect(IMPLICIT)
    assert classify(IMPLICIT).destination is Destination.rule


def test_formula_beats_its_own_conditional_marker():
    """BPHS 20.5 contains `if` and is arithmetic, not prediction. Were it routed to
    extraction it would yield a rule that can never match a chart."""
    assert Signal.conditional in detect(FORMULA)
    verdict = classify(FORMULA)
    assert verdict.destination is Destination.item
    assert verdict.kind is ItemKind.formula


def test_rule_with_a_remedy_stays_a_rule():
    """BPHS 54.63 states a condition, a consequence and a remedy together. Filing it
    as a remedy would throw away the prediction."""
    verdict = classify(RULE_WITH_REMEDY)
    assert verdict.destination is Destination.rule
    assert any("remedy" in reason for reason in verdict.reasons)


def test_noun_phrase_consequent_is_recognised():
    """"danger of death is there" is a consequent. An earlier verb-only pattern
    missed it and sent the verse to the paid ambiguous lane."""
    assert Signal.effect in detect(RULE_WITH_REMEDY)


def test_invocation_routes_to_item():
    verdict = classify(INVOCATION)
    assert verdict.destination is Destination.item
    assert verdict.kind is ItemKind.invocation


def test_invocation_framing_does_not_swallow_a_rule():
    """"Parasara said, if Saturn..." is a rule wearing a frame."""
    framed = "Parasara said: if Saturn is placed in the 7th house the native will suffer."
    assert Signal.invocation in detect(framed)
    assert classify(framed).destination is Destination.rule


def test_empty_translation_is_captured_not_dropped():
    verdict = classify("")
    assert verdict.destination is Destination.item
    assert verdict.kind is ItemKind.unclassified
    assert verdict.reasons


def test_chapter_gate_classifies_but_never_discards():
    """BPHS 1 is cosmology. It still lands in destination B with its text intact."""
    verdict = classify(CONDITIONAL, chapter_is_rule_bearing=False,
                       chapter_gating_reason="cosmology")
    assert verdict.destination is Destination.item
    assert verdict.kind is ItemKind.narrative


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("cosmology", ItemKind.narrative),
        ("devotional", ItemKind.invocation),
        ("calculation method", ItemKind.formula),
        ("reference data", ItemKind.reference_table),
        ("something new", ItemKind.out_of_domain),
    ],
)
def test_every_gating_reason_maps_to_a_kind(reason, expected):
    """An unrecognised gating reason must still produce a kind, never a crash or a
    silent skip."""
    verdict = classify("text", chapter_is_rule_bearing=False,
                       chapter_gating_reason=reason)
    assert verdict.kind is expected


def test_ambiguous_is_the_only_unpriced_outcome():
    """Uncertainty escalates. It must never resolve to `narrative`, because that is
    the one classification from which content does not come back."""
    verdict = classify("Jupiter and the 5th house.")
    assert verdict.destination is Destination.ambiguous
    assert verdict.kind is None


def test_classifier_is_deterministic():
    """Same version + same input = same state is a client release gate."""
    assert classify(CONDITIONAL) == classify(CONDITIONAL)


def test_item_verdict_must_name_a_kind():
    with pytest.raises(ValueError):
        Verdict(Destination.item, None, 0.5)


def test_timing_presence_is_flagged_for_the_compiler():
    """A dasha atom must end up in `timing.activation_factors`, never in the natal
    promise. Triage records the signal so S6 knows to move it."""
    timed = (
        "If the lord of the 7th is placed in the 8th house, the native will suffer "
        "loss during the dasha of Saturn."
    )
    verdict = classify(timed)
    assert verdict.destination is Destination.rule
    assert any("activation_factors" in reason for reason in verdict.reasons)


def test_avastha_chapters_are_gated_before_they_cost_anything():
    """Measured on the vol 1 whole-book run: chapter 47 "AVASTHAS OF PLANETS" spent 161
    AI calls to produce 161 declines -- 28% of the book's declines, and every one
    predictable from the chapter title alone."""
    from app.knowledge.triage.chapter_kind import missing_capability

    assert missing_capability("AVASTHAS OF PLANETS") == "avastha (planetary states)"
    assert missing_capability("Effects of the Bhava Lords") is None
