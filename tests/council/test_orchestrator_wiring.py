"""The end-to-end routing contract, without an LLM or a vector store.

These assert the specific inversions this change exists to fix, which
`scripts/eval_rules.py` cannot see -- it grades `primary` only.
"""

from rishivan.council.domains import DOMAIN_RISHIS, primary_rishi_for
from rishivan.council.routing import merge_supporting, route_question
from tests.eval.questions import QUESTIONS


def voice_for(question: str, supporting=()) -> str:
    routing = merge_supporting(route_question(question), list(supporting))
    return primary_rishi_for(routing.primary)


def test_a_marriage_timing_question_is_answered_by_the_marriage_rishi():
    """It routed to ritam, whose all-MEDIUM weights gate nothing."""
    assert voice_for("When will I marry?") == "medhan"


def test_the_billionaire_question_is_answered_by_dhruvan():
    assert voice_for("Will I become a billionaire?") == "dhruvan"


def test_the_billionaire_question_gains_atma_as_a_secondary():
    """§12 prescribes ARTHA primary with KARMA / ATMA / YATRA secondary."""
    routing = merge_supporting(
        route_question("Will I become a billionaire?"), ["tattvan"]
    )
    assert "atma" in routing.secondary


def test_no_eval_question_is_answered_by_a_service_rishi():
    for entry in QUESTIONS:
        assert voice_for(entry.question) in DOMAIN_RISHIS, entry.question


def test_lens_is_gone():
    import importlib

    import pytest

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("rishivan.council.lens")
