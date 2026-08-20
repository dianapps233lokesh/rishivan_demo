"""The runtime's view of the rule base: vector search nominates, exact evaluation decides.

The measurement this whole module is built around, taken on `text-embedding-004` against
the real corpus, with the chart "the 7th lord is in the 6th house":

    0.8434  "the 7th lord is placed in the 5th house"               FALSE, ranked 1st
    0.8396  "the 7th lord is placed in the 6th, 8th or 12th house"  TRUE,  ranked 2nd
    0.8277  "the 7th lord is NOT placed in the 6th, 8th or 12th"    FALSE, the negation

So similarity may nominate candidates and must never decide truth. These tests pin that.
"""

import json

from rishivan.rag.rules import (
    MIN_RELEVANCE,
    RuleHit,
    match_rules,
    rule_collection_name,
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


class FakeStore:
    """Returns points in a fixed order, standing in for similarity ranking."""

    def __init__(self, points, exists=True):
        self._points = points
        self._exists = exists

    def exists(self):
        return self._exists

    def search(self, embedding, n_results):
        return self._points[:n_results]


def test_the_nearest_neighbour_is_discarded_when_the_condition_is_false():
    """The whole point. `FALSE_RULE` is first in similarity order and must not win."""
    hits = match_rules(FakeStore([FALSE_RULE, TRUE_RULE]), [0.0], tokens=CHART,
                       rishi="medhan", limit=5)
    assert [hit.rule_key for hit in hits] == ["true"]


def test_a_rules_negation_does_not_survive():
    """`none` over the same atoms scores within 0.02 of the rule it contradicts."""
    hits = match_rules(FakeStore([NEGATED_RULE]), [0.0], tokens=CHART,
                       rishi="medhan", limit=5)
    assert hits == []


def test_a_rishi_without_affinity_for_the_rule_does_not_get_it():
    """`dhruvan` covers wealth, career and property. A marriage rule is not its
    evidence, and letting it cite one is how a Rishi stops being a specialist."""
    assert match_rules(FakeStore([TRUE_RULE]), [0.0], tokens=CHART,
                       rishi="dhruvan", limit=5) == []


def test_the_fallback_rishi_does_get_it():
    """`vyom` maps to every domain at medium weight, so a routing miss is not also a
    retrieval miss."""
    hits = match_rules(FakeStore([TRUE_RULE]), [0.0], tokens=CHART, rishi="vyom",
                       limit=5)
    assert [hit.rule_key for hit in hits] == ["true"]


def test_a_rule_with_no_affinity_reaches_nobody():
    unrouted = _point("unrouted", TRUE_RULE and json.loads(
        TRUE_RULE["metadata"]["condition"]), {})
    assert match_rules(FakeStore([unrouted]), [0.0], tokens=CHART, rishi="vyom",
                       limit=5) == []


def test_ties_in_relevance_keep_the_vector_ordering():
    """Both rules score 1.00 for `medhan`, so similarity is the only remaining signal.
    The sort must be stable or the vector's opinion is silently thrown away."""
    second = _point(
        "second", json.loads(TRUE_RULE["metadata"]["condition"]), {"prema": 1.0})
    hits = match_rules(FakeStore([TRUE_RULE, second]), [0.0], tokens=CHART,
                       rishi="medhan", limit=5)
    assert [hit.rule_key for hit in hits] == ["true", "second"]


def test_a_missing_collection_degrades_to_nothing_rather_than_raising():
    """Before the first embed run the collection does not exist, and the runtime must
    fall back to page retrieval rather than fail the whole answer."""
    assert match_rules(FakeStore([TRUE_RULE], exists=False), [0.0], tokens=CHART,
                       rishi="vyom", limit=5) == []


def test_an_unreachable_store_degrades_to_nothing():
    class Broken:
        def exists(self):
            raise ConnectionError("qdrant unreachable")

    assert match_rules(Broken(), [0.0], tokens=CHART, rishi="vyom", limit=5) == []


def test_a_corrupt_payload_is_skipped_not_fatal():
    """One bad point must not take down an answer."""
    corrupt = {"metadata": {"rule_key": "bad", "condition": "{not json",
                            "rishi_affinity": json.dumps({"prema": 1.0})}}
    hits = match_rules(FakeStore([corrupt, TRUE_RULE]), [0.0], tokens=CHART,
                       rishi="medhan", limit=5)
    assert [hit.rule_key for hit in hits] == ["true"]


def test_the_limit_is_respected():
    points = [
        _point(f"r{i}", json.loads(TRUE_RULE["metadata"]["condition"]), {"prema": 1.0})
        for i in range(20)
    ]
    assert len(match_rules(FakeStore(points), [0.0], tokens=CHART, rishi="medhan",
                           limit=3)) == 3


def test_citation_is_book_chapter_and_verse():
    hit = RuleHit(rule_key="k", condition={}, effects=[],
                  source={"chapter": "26", "verse_ref": "21"}, relevance=1.0)
    assert hit.citation == "BPHS 26.21"


def test_the_rule_collection_is_separate_from_the_page_collection():
    """Mixing them would let a page hit and a rule hit compete on one similarity score,
    and they are not comparable: a page is evidence to read, a rule is a claim to test."""
    assert rule_collection_name("rishivan_docs") == "rishivan_docs_rules"
    assert rule_collection_name("rishivan_docs") != "rishivan_docs"


def test_min_relevance_is_not_zero():
    """At zero, any Rishi can cite any rule, which dissolves the specialisation the
    client's design rests on."""
    assert MIN_RELEVANCE > 0


# --- Recall: match first, then rank ------------------------------------------
#
# The measurement that forced this inversion, on 204 approved rules of which 21 are true
# of the test chart:
#
#     "will my wife be healthy?"  vector nominated 10/21 true  -- 11 lost
#     "will I be wealthy?"                          6/21       -- 14 lost
#     "what about my career?"                       6/21       -- 14 lost
#
# It was nominating 72 of 204 -- over a third of the base -- and still losing half.


class ScrollStore(FakeStore):
    """A store that can be scrolled, which is what exact matching needs."""

    def all_points(self):
        return self._points


def test_true_rules_finds_every_true_rule_regardless_of_similarity():
    """`FALSE_RULE` is first in similarity order and `TRUE_RULE` last; recall must not
    depend on that ordering at all."""
    from rishivan.rag.rules import true_rules

    store = ScrollStore([FALSE_RULE, NEGATED_RULE, TRUE_RULE])
    assert [hit.rule_key for hit in true_rules(store, CHART)] == ["true"]


def test_true_rules_ignores_rishi_relevance():
    """Truth is not a Rishi's opinion. Filtering by relevance happens in ranking, so a
    rule outside the answering Rishi's domains is still found to be true."""
    from rishivan.rag.rules import true_rules

    wealth_rule = _point(
        "wealth", json.loads(TRUE_RULE["metadata"]["condition"]), {"artha": 1.0})
    assert len(true_rules(ScrollStore([wealth_rule]), CHART)) == 1


def test_a_rule_whose_exception_holds_is_not_true_of_the_chart():
    """`applies`, not `satisfies`. A rule the source cancels must not be presented as
    applying -- that asserts what the book denies."""
    from rishivan.rag.rules import true_rules

    excepted = _point(
        "excepted", json.loads(TRUE_RULE["metadata"]["condition"]), {"prema": 1.0})
    excepted["metadata"]["exceptions"] = json.dumps(
        [{"statement": "not when the 7th lord is in the 6th",
          "condition": {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 7,
                                   "house": 6}]}}]
    )
    assert true_rules(ScrollStore([excepted]), CHART) == []


def test_ranking_respects_the_limit_without_affecting_recall():
    from rishivan.rag.rules import rules_for_question, true_rules

    # Distinct verses, because rules sharing a verse and a condition now merge -- see
    # merge_siblings. Using one verse 15 times would test the merge, not the limit.
    points = [
        _point(f"r{i}", json.loads(TRUE_RULE["metadata"]["condition"]),
               {"prema": 1.0}, verse=str(i))
        for i in range(15)
    ]
    store = ScrollStore(points)
    assert len(true_rules(store, CHART)) == 15
    assert len(rules_for_question(store, [0.0], tokens=CHART, rishi="medhan",
                                  limit=4)) == 4


def test_ranking_drops_rules_outside_the_rishis_domains():
    from rishivan.rag.rules import rules_for_question

    wealth = _point(
        "wealth", json.loads(TRUE_RULE["metadata"]["condition"]), {"artha": 1.0},
        verse="99")
    hits = rules_for_question(ScrollStore([wealth, TRUE_RULE]), [0.0], tokens=CHART,
                              rishi="medhan", limit=10)
    assert [hit.rule_key for hit in hits] == ["true"]


def test_an_unscrollable_store_degrades_to_nothing():
    from rishivan.rag.rules import true_rules

    class Broken:
        def all_points(self):
            raise ConnectionError("qdrant unreachable")

    assert true_rules(Broken(), CHART) == []


# --- Sibling merging --------------------------------------------------------
#
# BPHS 26.60 was extracted as three rules (adopted son / purchased son / bereft of his own
# sons) while 26.13 kept all six of its outcomes on one. On a real chart, 17 matching rules
# proved to be 10 distinct verses.


def test_siblings_sharing_a_verse_and_condition_merge():
    from rishivan.rag.rules import true_rules

    cond = json.loads(TRUE_RULE["metadata"]["condition"])
    siblings = [
        _point("a", cond, {"prema": 1.0}, statement="adopted son", chapter="26",
               verse="60"),
        _point("b", cond, {"prema": 1.0}, statement="purchased son", chapter="26",
               verse="60"),
        _point("c", cond, {"prema": 1.0}, statement="bereft of his own sons",
               chapter="26", verse="60"),
    ]
    hits = true_rules(ScrollStore(siblings), CHART)
    assert len(hits) == 1
    assert {effect["statement"] for effect in hits[0].effects} == {
        "adopted son", "purchased son", "bereft of his own sons",
    }
    assert hits[0].merged_from == ["b", "c"]


def test_the_same_verse_with_different_conditions_stays_separate():
    """BPHS 15.1-2 holds several distinct conditions in one verse. Merging on the verse
    alone would collapse claims the book keeps apart."""
    from rishivan.rag.rules import true_rules

    other = {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 7, "house": 6}]}
    points = [
        _point("a", json.loads(TRUE_RULE["metadata"]["condition"]), {"prema": 1.0},
               chapter="15", verse="1-2"),
        _point("b", other, {"prema": 1.0}, chapter="15", verse="1-2"),
    ]
    assert len(true_rules(ScrollStore(points), CHART)) == 2


def test_merging_takes_the_union_of_affinity():
    """Keeping only one sibling's affinity would narrow the merged rule's reach."""
    from rishivan.rag.rules import merge_siblings

    cond = {"atoms": []}
    left = RuleHit(rule_key="a", condition=cond, effects=[], source={"chapter": "1",
                   "verse_ref": "1"}, relevance=0.0, rishi_affinity={"prema": 1.0})
    right = RuleHit(rule_key="b", condition=cond, effects=[], source={"chapter": "1",
                    "verse_ref": "1"}, relevance=0.0, rishi_affinity={"vansh": 0.6})
    merged = merge_siblings([left, right])
    assert len(merged) == 1
    assert merged[0].rishi_affinity == {"prema": 1.0, "vansh": 0.6}


# --- Ranking that actually discriminates ------------------------------------
#
# Before this, every rule touching one of a persona's domains scored 1.0, so a marriage
# question ranked "honoured by the King" and "lives in foreign lands" equal to "happiness
# through wife". Ownership cannot order anything on its own.


def test_a_focused_rule_outranks_a_scattered_one():
    from rishivan.rag.rules import rank_score

    _, focused = rank_score("medhan", {"prema": 1.0}, [], [])
    _, scattered = rank_score(
        "medhan",
        {"prema": 1.0, "artha": 1.0, "karma": 1.0, "yatra": 1.0, "dharma": 1.0},
        [], [],
    )
    assert focused > scattered


def test_both_still_clear_the_relevance_floor():
    """Focus changes the ORDER, not whether a rule is this Rishi's evidence at all."""
    from rishivan.rag.rules import MIN_RELEVANCE, rank_score

    for affinity in ({"prema": 1.0}, {"prema": 1.0, "artha": 1.0, "karma": 1.0}):
        relevance, _ = rank_score("medhan", affinity, [], [])
        assert relevance >= MIN_RELEVANCE


def test_topical_similarity_can_reorder_equally_owned_rules():
    from rishivan.rag.rules import rank_score

    question = [1.0, 0.0]
    _, near = rank_score("medhan", {"prema": 1.0}, question, [1.0, 0.0])
    _, far = rank_score("medhan", {"prema": 1.0}, question, [0.0, 1.0])
    assert near > far


def test_focus_is_the_share_of_the_rules_affinity_mass():
    from rishivan.rag.rules import focus

    assert focus({"prema": 1.0}, "prema") == 1.0
    assert focus({"prema": 1.0, "artha": 1.0}, "prema") == 0.5
    assert focus({}, "prema") == 0.0
