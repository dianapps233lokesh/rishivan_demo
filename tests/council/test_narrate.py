"""Prose, generated from the plan — and a template when the model fails.

Two things this file pins. First, **the gate**: a claim absent from the plan is
absent from the prompt, and a model cannot cite what it was never shown.

Second, **the fallback**. `render_template` produces a real answer with real
citations from the plan alone. That is possible only because the evidence is
structured, and it is the strongest single argument for the whole architecture:
when the model is down, the system still answers, and the answer is still
grounded.
"""

import types

import pytest

from rishivan.council.answer_plan import AllowedClaim, AnswerPlan
from rishivan.council.narrate import (
    INSUFFICIENT,
    render_template,
    stream_answer,
)

CLAIM = AllowedClaim(
    claim_id="wealth.accumulation",
    band="strongly_indicated",
    phrasing="strongly indicated",
    confidence=0.78,
    citations=("bphs ch34.v12",),
    rule_ids=("BPHS.WEALTH.CH34V12.0001",),
    tier="house",
    counter=("saravali ch5.v3",),
    corroborated=True,
)

WEAK = AllowedClaim(
    claim_id="wealth.loss",
    band="some_indications",
    phrasing="some indications suggest",
    confidence=0.42,
    citations=("phaladeepika ch2.v9",),
    rule_ids=("PD.WEALTH.CH2V9.0001",),
    tier="varga",
    corroborated=False,
)


def _plan(**kw):
    base = dict(
        question="will I become wealthy?",
        domain="domain.wealth",
        allowed=(CLAIM, WEAK),
        must_say=("D60 needs a birth time known to the minute; yours is to the hour.",),
        must_not_say=("Do not name a date, a year or a month.",),
        disagreement="",
        insufficient=False,
        unreviewed=True,
    )
    base.update(kw)
    return AnswerPlan(**base)


class RecordingClient:
    def __init__(self, chunks=("a grounded reading.",)):
        self.prompts = []
        outer = self

        class _Models:
            @staticmethod
            def generate_content_stream(model=None, contents=None):
                outer.prompts.append(contents)
                return iter([type("C", (), {"text": c})() for c in chunks])

        self.models = _Models()


class FailingClient:
    def __init__(self):
        class _Models:
            @staticmethod
            def generate_content_stream(**kw):
                raise RuntimeError("the model is down")

        self.models = _Models()


class MidStreamFailure:
    """Fails after the first chunk — the harder case, and the realistic one."""

    def __init__(self):
        class _Models:
            @staticmethod
            def generate_content_stream(**kw):
                yield type("C", (), {"text": "The chart "})()
                raise RuntimeError("connection reset")

        self.models = _Models()


def _text(plan, client):
    return "".join(stream_answer(plan, client=client, state={}))


# ==========================================================================
# The gate
# ==========================================================================


def test_the_prompt_contains_every_allowed_claim():
    client = RecordingClient()
    _text(_plan(), client)
    for claim in _plan().allowed:
        assert claim.claim_id in client.prompts[0]


def test_a_claim_absent_from_the_plan_is_absent_from_the_prompt():
    """The gate, stated as a test. It works because it is subtractive: there
    is no instruction to disobey."""
    client = RecordingClient()
    _text(_plan(allowed=(CLAIM,)), client)
    assert "wealth.loss" not in client.prompts[0]


def test_the_prompt_carries_the_phrasing_each_claim_licenses():
    client = RecordingClient()
    _text(_plan(), client)
    assert "strongly indicated" in client.prompts[0]
    assert "some indications suggest" in client.prompts[0]


def test_the_prompt_carries_the_citations():
    client = RecordingClient()
    _text(_plan(), client)
    assert "bphs ch34.v12" in client.prompts[0]


def test_the_prompt_carries_the_counter_evidence():
    client = RecordingClient()
    _text(_plan(), client)
    assert "saravali ch5.v3" in client.prompts[0]


def test_the_prompt_carries_what_must_be_said():
    client = RecordingClient()
    _text(_plan(), client)
    assert "D60" in client.prompts[0]


def test_the_prompt_carries_what_must_not_be_said():
    client = RecordingClient()
    _text(_plan(), client)
    assert "Do not name a date" in client.prompts[0]


def test_the_prompt_marks_an_uncorroborated_claim():
    client = RecordingClient()
    _text(_plan(), client)
    assert "not corroborated" in client.prompts[0].lower()


def test_a_disagreement_reaches_the_prompt():
    client = RecordingClient()
    _text(_plan(disagreement="dhruvan and vyom disagree"), client)
    assert "disagree" in client.prompts[0]


# ==========================================================================
# The fallback
# ==========================================================================


def test_a_model_failure_falls_back_to_the_template():
    """Possible only because the evidence is structured. The system answers
    with the model down, and the answer is still grounded."""
    text = _text(_plan(), FailingClient())
    assert text.strip()
    assert "bphs ch34.v12" in text


def test_a_mid_stream_failure_still_produces_a_whole_answer():
    """The realistic failure. A reader must not be left with half a sentence."""
    text = _text(_plan(), MidStreamFailure())
    assert "bphs ch34.v12" in text


def test_the_template_cites_every_claim_it_states():
    text = render_template(_plan())
    for claim in _plan().allowed:
        assert any(c in text for c in claim.citations)


def test_the_template_states_the_counter_evidence():
    assert "against" in render_template(_plan()).lower()


def test_the_template_uses_the_licensed_phrasing():
    text = render_template(_plan())
    assert "strongly indicated" in text
    assert "some indications suggest" in text


def test_the_template_says_what_must_be_said():
    assert "D60" in render_template(_plan())


def test_the_template_names_no_date_when_none_is_licensed():
    """It is generated from the plan, so it cannot invent what the plan
    forbids — but a template with a hardcoded year would."""
    import re

    assert not re.search(r"\b(?:19|20)\d\d\b", render_template(_plan()))


def test_the_template_is_deterministic():
    assert render_template(_plan()) == render_template(_plan())


# ==========================================================================
# Declining
# ==========================================================================


def test_an_insufficient_plan_declines_rather_than_composing():
    text = _text(_plan(allowed=(), insufficient=True), FailingClient())
    assert text.strip() == INSUFFICIENT.strip()


def test_an_insufficient_plan_never_calls_the_model():
    """Composing prose over nothing retrieved is the failure the whole
    grounding discipline exists to prevent. Paying for it is worse."""
    client = RecordingClient()
    _text(_plan(allowed=(), insufficient=True), client)
    assert client.prompts == []


# ==========================================================================
# Shape
# ==========================================================================


def test_it_returns_a_generator():
    """`streamlit_app` iterates it chunk by chunk to render progressively."""
    assert isinstance(stream_answer(_plan(), client=RecordingClient(), state={}),
                      types.GeneratorType)


def test_it_yields_more_than_once_when_the_model_streams():
    chunks = list(stream_answer(_plan(),
                                client=RecordingClient(("a", "b", "c")),
                                state={}))
    assert len(chunks) >= 3
