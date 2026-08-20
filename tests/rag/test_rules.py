"""The runtime's view of the rule base: exact evaluation decides, similarity ranks.

The measurement this module is built around, on `text-embedding-004` against the real
corpus, for the chart "the 7th lord is in the 6th house":

    0.8434  "the 7th lord is placed in the 5th house"               FALSE, ranked 1st
    0.8396  "the 7th lord is placed in the 6th, 8th or 12th house"  TRUE,  ranked 2nd
    0.8277  "the 7th lord is NOT placed in the 6th, 8th or 12th"    FALSE, the negation

So similarity may order candidates and must never decide truth. And it must not gate
recall either: nominating by similarity first lost 11 to 14 of 21 true rules on the
measured chart. Match everything, then rank.
"""

import json

from rishivan.rag.rules import (
    MIN_RELEVANCE,
    RuleHit,
    merge_siblings,
    rank_score,
    rule_collection_name,
    rules_for_question,
    true_rules,
)


def _point(rule_key, condition, affinity, statement="an outcome", chapter="20",
           verse="2", translation="In case the 7th Lord..."):
    return {
        "document": translation,
        "metadata": {
            "rule_key": rule_key,
            "condition": json.dumps(condition),
            "effects": json.dumps(
                [{"polarity": "negative", "strength": "moderate",
                  "statement": statement}]
            ),
            "source": json.dumps(
                {"chapter": chapter, "verse_ref": verse, "translation": translation}
            ),
            "life_domains": json.dumps(["marriage"]),
            "rishi_affinity": json.dumps(affinity),
        },
    }


TRUE_RULE = _point(
    "true", {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 7,
                        "houses": [6, 8, 12]}]}, {"prema": 1.0})
FALSE_RULE = _point(
    "false", {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 7, "house": 5}]},
    {"prema": 1.0})
NEGATED_RULE = _point(
    "negated", {"none": [{"type": "lord_of_house_in_house", "lord_of": 7,
                          "houses": [6, 8, 12]}]}, {"prema": 1.0})

CHART = {"house.7.lord.house": 6}

CONDITION = json.loads(TRUE_RULE["metadata"]["condition"])


class Store:
    """A scrollable store. Point order stands in for similarity ranking."""

    def __init__(self, points):
        self._points = points

    def all_points(self, with_vectors=False):
        return self._points


# --- Truth ------------------------------------------------------------------


def test_every_true_rule_is_found_regardless_of_similarity_order():
    """`FALSE_RULE` is first in similarity order and `TRUE_RULE` last. Recall must not
    depend on that ordering, and a rule's own negation must not survive."""
    store = Store([FALSE_RULE, NEGATED_RULE, TRUE_RULE])
    assert [hit.rule_key for hit in true_rules(store, CHART)] == ["true"]


def test_truth_ignores_rishi_relevance():
    """Truth is not a Rishi's opinion — relevance is applied in ranking, so a rule
    outside the answering Rishi's domains is still found to be true."""
    wealth = _point("wealth", CONDITION, {"artha": 1.0})
    assert len(true_rules(Store([wealth]), CHART)) == 1


def test_a_rule_whose_exception_holds_is_not_true_of_the_chart():
    """`applies`, not `satisfies`. A rule the source cancels must not be presented as
    applying — that asserts what the book denies."""
    excepted = _point("excepted", CONDITION, {"prema": 1.0})
    excepted["metadata"]["exceptions"] = json.dumps(
        [{"statement": "not when the 7th lord is in the 6th",
          "condition": {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 7,
                                   "house": 6}]}}]
    )
    assert true_rules(Store([excepted]), CHART) == []


# --- Degrading rather than failing ------------------------------------------


def test_an_unreachable_store_degrades_to_nothing():
    """Before the first embed run the collection does not exist, and a broken Qdrant
    must fall back to page retrieval rather than fail the whole answer."""

    class Broken:
        def all_points(self, with_vectors=False):
            raise ConnectionError("qdrant unreachable")

    assert true_rules(Broken(), CHART) == []


def test_a_store_predating_with_vectors_still_works():
    """The TypeError retry must sit inside the outer guard, or a ConnectionError from
    the second call escapes and kills the answer."""

    class Legacy:
        def all_points(self):
            return [TRUE_RULE]

    assert [hit.rule_key for hit in true_rules(Legacy(), CHART)] == ["true"]


def test_a_corrupt_payload_is_skipped_not_fatal():
    corrupt = {"metadata": {"rule_key": "bad", "condition": "{not json",
                            "rishi_affinity": json.dumps({"prema": 1.0})}}
    hits = true_rules(Store([corrupt, TRUE_RULE]), CHART)
    assert [hit.rule_key for hit in hits] == ["true"]


# --- Relevance --------------------------------------------------------------


def test_ranking_drops_rules_outside_the_rishis_domains():
    wealth = _point("wealth", CONDITION, {"artha": 1.0}, verse="99")
    hits = rules_for_question(Store([wealth, TRUE_RULE]), [0.0], tokens=CHART,
                              rishi="medhan", limit=10)
    assert [hit.rule_key for hit in hits] == ["true"]


def test_the_fallback_rishi_still_gets_the_rule():
    """`vyom` maps to every domain at medium weight, so a routing miss is not also a
    retrieval miss."""
    hits = rules_for_question(Store([TRUE_RULE]), [0.0], tokens=CHART, rishi="vyom",
                              limit=5)
    assert [hit.rule_key for hit in hits] == ["true"]


def test_a_rule_with_no_affinity_reaches_nobody():
    unrouted = _point("unrouted", CONDITION, {})
    assert rules_for_question(Store([unrouted]), [0.0], tokens=CHART, rishi="vyom",
                              limit=5) == []


def test_min_relevance_is_not_zero():
    """At zero any Rishi can cite any rule, dissolving the specialisation."""
    assert MIN_RELEVANCE > 0


def test_ranking_respects_the_limit_without_affecting_recall():
    # Distinct verses, because rules sharing a verse and condition merge — using one
    # verse 15 times would test the merge, not the limit.
    points = [
        _point(f"r{i}", CONDITION, {"prema": 1.0}, verse=str(i)) for i in range(15)
    ]
    store = Store(points)
    assert len(true_rules(store, CHART)) == 15
    assert len(rules_for_question(store, [0.0], tokens=CHART, rishi="medhan",
                                  limit=4)) == 4


def test_ties_keep_the_incoming_order():
    """Equally owned, equally topical rules must keep the store's ordering rather than
    having it silently thrown away by an unstable sort."""
    first = _point("first", CONDITION, {"prema": 1.0}, verse="1")
    second = _point("second", CONDITION, {"prema": 1.0}, verse="2")
    hits = rules_for_question(Store([first, second]), [0.0], tokens=CHART,
                              rishi="medhan", limit=5)
    assert [hit.rule_key for hit in hits] == ["first", "second"]


# --- Ranking that discriminates ---------------------------------------------
#
# Before focus, every rule touching one of a persona's domains scored 1.0, so a
# marriage question ranked "honoured by the King" level with "happiness through wife".


def test_a_focused_rule_outranks_a_scattered_one():
    _, focused = rank_score("medhan", {"prema": 1.0}, [], [])
    _, scattered = rank_score(
        "medhan",
        {"prema": 1.0, "artha": 1.0, "karma": 1.0, "yatra": 1.0, "dharma": 1.0},
        [], [],
    )
    assert focused > scattered


def test_both_still_clear_the_relevance_floor():
    """Focus changes the ORDER, not whether a rule is this Rishi's evidence at all."""
    for affinity in ({"prema": 1.0}, {"prema": 1.0, "artha": 1.0, "karma": 1.0}):
        relevance, _ = rank_score("medhan", affinity, [], [])
        assert relevance >= MIN_RELEVANCE


def test_topical_similarity_can_reorder_equally_owned_rules():
    question = [1.0, 0.0]
    _, near = rank_score("medhan", {"prema": 1.0}, question, [1.0, 0.0])
    _, far = rank_score("medhan", {"prema": 1.0}, question, [0.0, 1.0])
    assert near > far


def test_focus_is_the_share_of_the_rules_affinity_mass():
    from rishivan.rag.rules import focus

    assert focus({"prema": 1.0}, "prema") == 1.0
    assert focus({"prema": 1.0, "artha": 1.0}, "prema") == 0.5
    assert focus({}, "prema") == 0.0


# --- Sibling merging --------------------------------------------------------
#
# BPHS 26.60 was extracted as three rules (adopted / purchased son / bereft of his own)
# while 26.13 kept all six outcomes on one. On a real chart, 17 matches were 10 verses.


def test_siblings_sharing_a_verse_and_condition_merge():
    siblings = [
        _point("a", CONDITION, {"prema": 1.0}, statement="adopted son",
               chapter="26", verse="60"),
        _point("b", CONDITION, {"prema": 1.0}, statement="purchased son",
               chapter="26", verse="60"),
        _point("c", CONDITION, {"prema": 1.0}, statement="bereft of his own sons",
               chapter="26", verse="60"),
    ]
    hits = true_rules(Store(siblings), CHART)
    assert len(hits) == 1
    assert {effect["statement"] for effect in hits[0].effects} == {
        "adopted son", "purchased son", "bereft of his own sons",
    }
    assert hits[0].merged_from == ["b", "c"]


def test_the_same_verse_with_different_conditions_stays_separate():
    """BPHS 15.1-2 holds several distinct conditions in one verse; merging on the verse
    alone would collapse claims the book keeps apart."""
    other = {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 7, "house": 6}]}
    points = [
        _point("a", CONDITION, {"prema": 1.0}, chapter="15", verse="1-2"),
        _point("b", other, {"prema": 1.0}, chapter="15", verse="1-2"),
    ]
    assert len(true_rules(Store(points), CHART)) == 2


def test_merging_takes_the_union_of_affinity():
    """Keeping only one sibling's affinity would narrow the merged rule's reach."""
    cond = {"atoms": []}
    left = RuleHit(rule_key="a", condition=cond, effects=[], source={"chapter": "1",
                   "verse_ref": "1"}, relevance=0.0, rishi_affinity={"prema": 1.0})
    right = RuleHit(rule_key="b", condition=cond, effects=[], source={"chapter": "1",
                    "verse_ref": "1"}, relevance=0.0, rishi_affinity={"vansh": 0.6})
    merged = merge_siblings([left, right])
    assert len(merged) == 1
    assert merged[0].rishi_affinity == {"prema": 1.0, "vansh": 0.6}


# --- Wiring -----------------------------------------------------------------


def test_citation_is_book_chapter_and_verse():
    hit = RuleHit(rule_key="k", condition={}, effects=[],
                  source={"chapter": "26", "verse_ref": "21"}, relevance=1.0)
    assert hit.citation == "BPHS 26.21"


def test_the_rule_collection_is_separate_from_the_page_collection():
    """Mixing them would let a page hit and a rule hit compete on one similarity score,
    and they are not comparable: a page is evidence to read, a rule a claim to test."""
    assert rule_collection_name("rishivan_docs") == "rishivan_docs_rules"
    assert rule_collection_name("rishivan_docs") != "rishivan_docs"
