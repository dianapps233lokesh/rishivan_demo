"""Facts the seeker states about their own life.

The seeker wrote "I got married on 22nd Nov 2025. When will I have a child" and
the reading came back saying their primary window for marriage opens between
April 2030 and August 2036. That is not caution and it is not a hedge - it is
the answer contradicting something it was told in the same sentence it was
asked.

Nothing read it. There was no state field for a stated fact, nothing parsed a
date out of a question, and the only `LIFE_EVENTS` reference in the tree is a
rectification enum. The question reached routing as topic words and the fact
went nowhere.

So: the classifier already makes one structured pass over the question, and the
facts ride along on it rather than paying for a second call. From there they
have to survive three hops - into state, into the Rishi's prompt, and into the
narrative gate - and each hop is a place they were silently dropped before.
"""

import json
import types

import pytest

from rishivan.council.classifier import classify_query

MARRIED = "I got married on 22nd Nov 2025. When will I have a child"


def _client(payload: dict):
    """A client that returns one canned classification."""
    def generate_content(*, model, contents):
        return types.SimpleNamespace(text=json.dumps(payload))

    return types.SimpleNamespace(
        models=types.SimpleNamespace(generate_content=generate_content)
    )


_BASE = {
    "is_smalltalk_or_gibberish": False,
    "primary_rishi": "medhan",
    "query_domain": "natal",
    "needs_birth_data": True,
    "confidence": 0.9,
    "reasoning": "children",
    "supporting_rishis": [],
    "search_query": "children fifth house",
    "intent": "fact",
    "chart_type": "varga",
    "varga_code": "D1",
    "relevant_vargas": ["D7"],
    "dasha_level": "all",
}


class TestTheClassifierCarriesThem:
    def test_a_stated_fact_survives_classification(self):
        out = classify_query(_client({**_BASE, "stated_facts": [
            {"text": "married", "when": "2025-11-22"}]}), MARRIED)
        assert out["stated_facts"]
        assert out["stated_facts"][0]["when"] == "2025-11-22"

    def test_a_fact_without_a_date_is_still_kept(self):
        """"I am working in an IT company as a Product Owner" dates nothing and
        still constrains what the answer may claim about their work."""
        out = classify_query(_client({**_BASE, "stated_facts": [
            {"text": "works as a Product Owner at an IT company", "when": ""}]}),
            "how will my appraisal go")
        assert out["stated_facts"][0]["text"]
        assert out["stated_facts"][0]["when"] == ""

    def test_no_facts_is_an_empty_list_not_a_missing_key(self):
        """Every consumer does a plain lookup. A missing key is an AttributeError
        three nodes downstream, inside a broad `except`, where it reads as the
        feature not existing."""
        assert classify_query(_client(_BASE), "will I be wealthy")["stated_facts"] == []

    def test_a_malformed_entry_is_dropped_not_fatal(self):
        """Model output. The question still has to be answered."""
        out = classify_query(_client({**_BASE, "stated_facts": [
            "just a string", {"when": "2025-11-22"}, None, 7,
            {"text": "married", "when": "2025-11-22"}]}), MARRIED)
        assert out["stated_facts"] == [{"text": "married", "when": "2025-11-22"}]

    def test_classification_failure_still_yields_the_key(self):
        def boom(*, model, contents):
            raise RuntimeError("no")

        client = types.SimpleNamespace(
            models=types.SimpleNamespace(generate_content=boom))
        assert classify_query(client, MARRIED)["stated_facts"] == []


class TestTheRishiIsToldThem:
    def test_the_prompt_names_the_fact(self):
        from rishivan.council.rishis.prompt import _stated_facts_block

        block = _stated_facts_block([
            {"text": "married", "when": "2025-11-22"}])
        assert "2025-11-22" in block
        assert "married" in block

    def test_no_facts_produces_no_block(self):
        from rishivan.council.rishis.prompt import _stated_facts_block

        assert _stated_facts_block([]) == ""
        assert _stated_facts_block(None) == ""

    def test_the_block_forbids_contradicting_them(self):
        from rishivan.council.rishis.prompt import _stated_facts_block

        block = _stated_facts_block([{"text": "married", "when": "2025-11-22"}]).lower()
        assert "contradict" in block


class TestTheNarrativeGateCarriesThem:
    def test_the_plan_keeps_them(self):
        from rishivan.council.answer_plan import build_answer_plan

        plan = build_answer_plan(
            question=MARRIED, domain="domain.progeny",
            stated_facts=[{"text": "married", "when": "2025-11-22"}],
        )
        assert plan.stated_facts

    def test_the_prompt_block_names_them(self):
        from rishivan.council.answer_plan import build_answer_plan
        from rishivan.council.narrate import gate_block

        plan = build_answer_plan(
            question=MARRIED, domain="domain.progeny",
            stated_facts=[{"text": "married", "when": "2025-11-22"}],
        )
        assert "2025-11-22" in gate_block(plan)

    def test_they_are_not_spent_from_the_disclosure_budget(self):
        """A fact the seeker gave is context the answer must respect, not a
        caveat about the machinery. Putting it in `must_say` would let a
        withheld division push it out of the answer."""
        from rishivan.council.answer_plan import build_answer_plan

        plan = build_answer_plan(
            question=MARRIED, domain="domain.progeny",
            stated_facts=[{"text": "married", "when": "2025-11-22"}],
        )
        assert not any("2025-11-22" in m for m in plan.must_say)
