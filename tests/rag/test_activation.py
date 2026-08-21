"""Activation: whether a rule's timing is running, not just whether it is promised.

Blueprint §8 rule 2 -- "separate potential from timing. Natal promise and event timing
are different reasoning problems." The corpus has carried `timing.activation_factors`
from the first extraction (393 rules, 343 of category `timing`), and every layer between
the corpus and the answer dropped it:

  * `scripts/embed_rules.py` never wrote it to the payload -- the same reader/writer gap
    already found with `modifiers`, `exceptions` and `remedies`.
  * `OBJECT_FIELD` mapped `dasha_of` to `level`, so the atom compared a planet name
    against the string "maha".
  * the chart emitted no `dasha.*` tokens for it to read.

So a "when" question could only ever be answered from the promise, with no way to say
whether the period that activates it is running. These pin the whole path.
"""

import json

import pytest

from rishivan.rag.rules import RuleHit, _payload_to_hit, rank_true_rules, true_rules

ACTIVATION = {
    "combinator": "all",
    "atoms": [{"type": "dasha_of", "planet": "saturn", "level": "maha"}],
}

CONDITION = {
    "combinator": "all",
    "atoms": [{"type": "lord_of_house_in_house", "lord_of": 7, "house": 7}],
}

CHART = {"house.7.lord.house": 7}
SATURN_RUNNING = {**CHART, "dasha.maha.lord": "saturn"}
JUPITER_RUNNING = {**CHART, "dasha.maha.lord": "jupiter"}


def payload(**overrides) -> dict:
    base = {
        "rule_key": "test.1",
        "condition": json.dumps(CONDITION),
        "effects": json.dumps([{"polarity": "favourable", "statement": "marriage"}]),
        "source": json.dumps({"chapter": 7, "verse_ref": "1", "translation": "t"}),
        "life_domains": json.dumps(["prema"]),
        "rule_category": "timing",
        "activation": json.dumps(ACTIVATION),
    }
    return {**base, **overrides}


class Store:
    def __init__(self, payloads):
        self._payloads = payloads

    def all_points(self, with_vectors: bool = False):
        return [{"metadata": p, "vector": [1.0]} for p in self._payloads]


# ── the payload boundary ─────────────────────────────────────────────────────


def test_the_reader_parses_activation_from_the_payload():
    hit = _payload_to_hit(payload(), relevance=0.0)
    assert hit is not None
    assert hit.activation == ACTIVATION


def test_a_rule_with_no_activation_recorded_parses_to_no_activation():
    hit = _payload_to_hit(payload(activation=json.dumps({})), relevance=0.0)
    assert hit is not None
    assert hit.activation == {}


def test_a_payload_predating_activation_still_parses():
    """Points embedded before this field existed must not vanish from the rule base."""
    stale = payload()
    del stale["activation"]
    assert _payload_to_hit(stale, relevance=0.0) is not None


def test_the_embedder_writes_the_key_the_reader_reads():
    """The contract test in test_rules.py catches a key the reader reads and the writer
    drops. It cannot catch a field NEITHER side handles, which is how this one survived
    three separate audits -- so name it explicitly."""
    from pathlib import Path

    writer = Path("scripts/embed_rules.py").read_text()
    assert '"activation"' in writer


# ── the running / dormant distinction ────────────────────────────────────────


def test_a_matched_rule_whose_period_is_running_is_marked_active():
    hits = true_rules(Store([payload()]), SATURN_RUNNING)
    assert len(hits) == 1
    assert hits[0].active is True


def test_a_matched_rule_whose_period_is_not_running_is_marked_dormant():
    """It still matched -- the promise is in the chart. What changed is that the answer
    can now say the promise is not currently activated instead of implying it is."""
    hits = true_rules(Store([payload()]), JUPITER_RUNNING)
    assert len(hits) == 1
    assert hits[0].active is False


def test_a_rule_with_no_activation_recorded_is_neither_active_nor_dormant():
    """None, not False. "No timing recorded" and "timing recorded and not running" are
    different claims, and collapsing them would let the answer report a pure natal
    promise as dormant."""
    hits = true_rules(Store([payload(activation=json.dumps({}))]), SATURN_RUNNING)
    assert hits[0].active is None


def test_activation_is_not_evaluated_against_a_chart_with_no_dasha_tokens():
    """A caller that forgot to date the tokens must get "cannot say", never "dormant"."""
    hits = true_rules(Store([payload()]), CHART)
    assert hits[0].active is False


# ── ranking ──────────────────────────────────────────────────────────────────


def _rank(hits, question):
    from rishivan.council.routing import route_question

    return rank_true_rules(
        hits, [1.0], routing=route_question(question), limit=10, question=question
    )


def test_a_running_rule_outranks_a_dormant_one_on_a_when_question():
    running = true_rules(Store([payload()]), SATURN_RUNNING)[0]
    dormant = true_rules(Store([payload(rule_key="test.2")]), JUPITER_RUNNING)[0]
    dormant.source = {**dormant.source, "verse_ref": "2"}
    ranked = _rank([dormant, running], "When will I marry?")
    assert [h.active for h in ranked][0] is True


def test_a_dormant_rule_is_never_dropped():
    """§8 rule 2 makes promise and timing different problems, not a hierarchy. The
    promise is still the evidence that there is anything to time."""
    dormant = true_rules(Store([payload()]), JUPITER_RUNNING)
    assert _rank(dormant, "When will I marry?") != []


def test_activation_does_not_reorder_a_whether_question():
    """"Will I marry?" asks about the promise. A running period is not more relevant to
    it than a dormant one, and letting it reorder here would answer a different
    question."""
    from rishivan.rag.rules import ACTIVATION_BONUS, rank_score
    from rishivan.council.routing import route_question

    common = dict(
        condition=CONDITION, affinity={"prema": 1.0}, query_embedding=[1.0],
        rule_vector=[1.0], rule_category="timing", tier="S0",
    )
    whether = route_question("Will I marry?")
    assert rank_score(whether, active=True, **common)[1] == rank_score(
        whether, active=False, **common
    )[1]
    timing = route_question("When will I marry?")
    assert rank_score(timing, active=True, **common)[1] - rank_score(
        timing, active=False, **common
    )[1] == pytest.approx(ACTIVATION_BONUS)
