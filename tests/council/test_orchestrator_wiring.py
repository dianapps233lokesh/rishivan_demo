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


# ── The timing tokens must be dated by the reading, not by the clock ──────────


def test_the_orchestrator_dates_its_tokens_with_the_query_time():
    """`all_chart_tokens(chart)` silently defaults to now. Right for a reading cast
    today and wrong for every other caller -- a Prashna cast for a stated moment, or a
    backtest, would have been matched against today's dasha while every other token
    came from the stated one. Asserted on the source because the call sits inside a
    vector-store branch no unit test reaches."""
    from pathlib import Path

    source = Path("rishivan/council/orchestrator.py").read_text()
    assert "all_chart_tokens(chart)" not in source, (
        "the rule-matching tokens are undated, so timing rules are evaluated "
        "against the wall clock rather than the reading's moment"
    )
    assert "all_chart_tokens(chart, when=" in source


def test_the_orchestrator_reports_how_many_rules_carried_timing():
    """A stale index is the failure mode this codebase keeps hitting: `activation` only
    reaches the payload when `scripts/embed_rules.py` is re-run, and until then every
    rule parses to `active=None` and the timing labels silently never appear. Counting
    them makes that visible instead of quiet -- zero timing on a "when" question means
    the index predates the field, not that the chart has no periods."""
    from pathlib import Path

    source = Path("rishivan/council/orchestrator.py").read_text()
    assert "rules_with_timing" in source
