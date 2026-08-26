"""Turn 14 must not disagree with turn 13 about a fact.

That is the failure a reader notices fastest and forgives least, and
`Conversation` could not prevent it: it carried prose only, so nothing on turn
14 knew what turn 13 had actually been licensed to assert.

What travels is the **claim ids and their bands**, not more prose. The prose is
already in the transcript; the claim ids are what a model can be held to.
"""

from rishivan.council.answer_plan import AllowedClaim, AnswerPlan
from rishivan.council.conversation import (
    MAX_TURNS,
    Conversation,
    consistency_instruction,
)

STRONG = AllowedClaim(
    claim_id="wealth.accumulation", band="strongly_indicated",
    phrasing="strongly indicated", confidence=0.78,
    citations=("bphs ch34.v12",), rule_ids=("R1",), tier="house",
    corroborated=True,
)

WEAKER = AllowedClaim(
    claim_id="wealth.accumulation", band="some_indications",
    phrasing="some indications suggest", confidence=0.45,
    citations=("bphs ch34.v12",), rule_ids=("R1",), tier="house",
    corroborated=True,
)

OTHER = AllowedClaim(
    claim_id="career.rise", band="strongly_indicated",
    phrasing="strongly indicated", confidence=0.8,
    citations=("bphs ch10.v1",), rule_ids=("R3",), tier="house",
    corroborated=True,
)


def _plan(allowed):
    return AnswerPlan(question="q", domain="domain.wealth",
                      allowed=tuple(allowed))


def _convo(claims=(("wealth.accumulation", "strongly_indicated"),)):
    convo = Conversation()
    convo.add("will I be wealthy?", "yes, strongly indicated", "dhruvan",
              claims=tuple(claims))
    return convo


# ==========================================================================
# Carrying the claims
# ==========================================================================


def test_a_turn_remembers_what_it_was_allowed_to_claim():
    assert _convo().last.claims == (("wealth.accumulation", "strongly_indicated"),)


def test_claims_are_optional_so_every_existing_caller_still_works():
    convo = Conversation()
    convo.add("q", "a", "vyom")
    assert convo.last.claims == ()


def test_claims_can_be_taken_straight_from_a_plan():
    from rishivan.council.conversation import claims_of

    assert claims_of(_plan([STRONG])) == (
        ("wealth.accumulation", "strongly_indicated"),
    )


def test_claims_of_none_is_empty():
    from rishivan.council.conversation import claims_of

    assert claims_of(None) == ()


# ==========================================================================
# The directive
# ==========================================================================


def test_an_empty_conversation_produces_no_directive():
    assert consistency_instruction(None, _plan([STRONG])) == ""
    assert consistency_instruction(Conversation(), _plan([STRONG])) == ""


def test_a_turn_with_no_recorded_claims_produces_no_directive():
    """Nothing to be consistent with. A directive here would be instructions
    about an empty list, which a model fills in."""
    convo = Conversation()
    convo.add("q", "a", "vyom")
    assert consistency_instruction(convo, _plan([STRONG])) == ""


def test_a_repeated_claim_at_the_same_band_is_named():
    text = consistency_instruction(_convo(), _plan([STRONG]))
    assert "wealth.accumulation" in text
    assert "already" in text.lower()


def test_a_claim_that_got_louder_is_flagged():
    """The same evidence read twice must not gain confidence on the second
    telling. Nothing changed but the retelling."""
    convo = _convo((("wealth.accumulation", "some_indications"),))
    text = consistency_instruction(convo, _plan([STRONG]))
    assert "stronger" in text.lower() or "louder" in text.lower()


def test_a_claim_that_got_quieter_is_flagged():
    convo = _convo((("wealth.accumulation", "strongly_indicated"),))
    text = consistency_instruction(convo, _plan([WEAKER]))
    assert "weaker" in text.lower() or "quieter" in text.lower()


def test_a_claim_that_has_dropped_out_is_flagged():
    """It was asserted last turn and this turn's evidence does not support it.
    Say so; do not silently stop mentioning it."""
    convo = _convo((("wealth.accumulation", "strongly_indicated"),))
    text = consistency_instruction(convo, _plan([OTHER]))
    assert "wealth.accumulation" in text
    assert "no longer" in text.lower()


def test_a_new_claim_is_not_flagged():
    """Turn 14 saying something turn 13 did not is normal — a different
    question was asked."""
    convo = _convo((("wealth.accumulation", "strongly_indicated"),))
    text = consistency_instruction(convo, _plan([STRONG, OTHER]))
    assert "career.rise" not in text


def test_an_unchanged_conversation_produces_a_short_directive():
    """An instruction block that grows with every turn is an instruction block
    a model reads past."""
    text = consistency_instruction(_convo(), _plan([STRONG]))
    assert len(text.splitlines()) < 12


def test_older_turns_are_not_carried_forever():
    """`MAX_TURNS` still bounds it. An unbounded directive is an unbounded
    prompt."""
    convo = Conversation()
    for i in range(MAX_TURNS + 3):
        convo.add(f"q{i}", f"a{i}", "dhruvan",
                  claims=((f"claim.{i}", "strongly_indicated"),))
    text = consistency_instruction(convo, _plan([STRONG]))
    assert "claim.0" not in text


def test_it_is_deterministic():
    assert (consistency_instruction(_convo(), _plan([STRONG]))
            == consistency_instruction(_convo(), _plan([STRONG])))
