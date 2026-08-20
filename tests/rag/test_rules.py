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

from rishivan.council.routing import route_question
from rishivan.rag.rules import (
    MIN_RELEVANCE,
    RuleHit,
    _payload_to_hit,
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


# --- Relevance: §4-11 coverage is the gate ----------------------------------
#
# `CONDITION` is "the 7th lord in the 6th, 8th or 12th" -- subject house 7, so PREMA
# claims it and KARMA does not. Relevance is decided by the ROUTED DOMAIN of the
# question, not by which persona happens to be speaking: a persona like `medhan` spans
# three client domains whose coverage sets together reach eleven of twelve houses, which
# is why persona-scoped relevance could not discriminate.

CAREER_CONDITION = {"atoms": [
    {"type": "lord_of_house_in_house", "lord_of": 10, "house": 11}
]}

MARRIAGE_Q = route_question("Will my marriage be happy?")
CAREER_Q = route_question("What career suits me?")


def test_a_career_rule_does_not_surface_for_a_marriage_question():
    career = _point("career", CAREER_CONDITION, {"karma": 1.0}, verse="99")
    hits = rules_for_question(
        Store([career, TRUE_RULE]),
        [0.0], tokens={**CHART, "house.10.lord.house": 11},
        routing=MARRIAGE_Q, limit=10,
    )
    assert [hit.rule_key for hit in hits] == ["true"]


def test_the_same_career_rule_surfaces_for_a_career_question():
    career = _point("career", CAREER_CONDITION, {"karma": 1.0}, verse="99")
    hits = rules_for_question(
        Store([career, TRUE_RULE]),
        [0.0], tokens={**CHART, "house.10.lord.house": 11},
        routing=CAREER_Q, limit=10,
    )
    assert [hit.rule_key for hit in hits] == ["career"]


def test_coverage_outranks_affinity_absolutely():
    """A rule outside the routed coverage cannot be rescued by a perfect affinity tag.
    That is the difference between a gate and a weight, and it is the fix: BPHS 22.6 had
    a perfect `family` tag and a 9th-house subject."""
    mistagged = _point("mistagged", CAREER_CONDITION, {"prema": 1.0}, verse="98")
    hits = rules_for_question(
        Store([mistagged]), [0.0],
        tokens={**CHART, "house.10.lord.house": 11},
        routing=MARRIAGE_Q, limit=10,
    )
    assert hits == []


def test_a_rule_with_no_affinity_still_reaches_when_its_house_matches():
    """A deliberate change from the affinity-gated model, which required a tag and so
    lost every unenriched rule. Affinity is refinement now; the condition's own subject
    house is the claim."""
    unrouted = _point("unrouted", CONDITION, {})
    hits = rules_for_question(Store([unrouted]), [0.0], tokens=CHART,
                              routing=MARRIAGE_Q, limit=5)
    assert [hit.rule_key for hit in hits] == ["unrouted"]


def test_min_relevance_is_not_zero():
    """The floor discards the marginal tail; coverage itself does the real gating."""
    assert MIN_RELEVANCE > 0


def test_ranking_respects_the_limit_without_affecting_recall():
    # Distinct verses, because rules sharing a verse and condition merge — using one
    # verse 15 times would test the merge, not the limit.
    points = [
        _point(f"r{i}", CONDITION, {"prema": 1.0}, verse=str(i)) for i in range(15)
    ]
    store = Store(points)
    assert len(true_rules(store, CHART)) == 15
    assert len(rules_for_question(store, [0.0], tokens=CHART,
                                  routing=MARRIAGE_Q, limit=4)) == 4


def test_ties_keep_the_incoming_order():
    """Equally covered, equally topical rules must keep the store's ordering rather than
    having it silently thrown away by an unstable sort."""
    first = _point("first", CONDITION, {"prema": 1.0}, verse="1")
    second = _point("second", CONDITION, {"prema": 1.0}, verse="2")
    hits = rules_for_question(Store([first, second]), [0.0], tokens=CHART,
                              routing=MARRIAGE_Q, limit=5)
    assert [hit.rule_key for hit in hits] == ["first", "second"]


# --- Ranking inside the gate ------------------------------------------------


def test_a_focused_rule_outranks_a_scattered_one():
    """Both are inside PREMA's coverage; the one whose outcome is squarely about
    marriage should lead."""
    _, focused, _ = rank_score(MARRIAGE_Q, CONDITION, {"prema": 1.0}, [], [])
    _, scattered, _ = rank_score(
        MARRIAGE_Q, CONDITION,
        {"prema": 1.0, "artha": 1.0, "karma": 1.0, "yatra": 1.0, "dharma": 1.0},
        [], [],
    )
    assert focused > scattered


def test_both_still_clear_the_relevance_floor():
    """Affinity changes the ORDER; coverage decides admission."""
    for affinity in ({"prema": 1.0}, {"prema": 1.0, "artha": 1.0, "karma": 1.0}):
        relevance, _, _ = rank_score(MARRIAGE_Q, CONDITION, affinity, [], [])
        assert relevance >= MIN_RELEVANCE


def test_topical_similarity_can_reorder_equally_covered_rules():
    question = [1.0, 0.0]
    _, near, _ = rank_score(MARRIAGE_Q, CONDITION, {"prema": 1.0}, question, [1.0, 0.0])
    _, far, _ = rank_score(MARRIAGE_Q, CONDITION, {"prema": 1.0}, question, [0.0, 1.0])
    assert near > far


def test_the_claiming_domain_is_reported():
    _, _, domain = rank_score(MARRIAGE_Q, CONDITION, {"prema": 1.0}, [], [])
    assert domain == "prema"


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


# --- Coverage-gated relevance (Eight Rishis §4-11, §12) ----------------------
#
# Replaces the free-text `life_domains` score. BPHS 22.6 and 26.74 both scored 1.00 for a
# marriage question because one is tagged `father` and one `Relationships`, and the
# answering persona owns both family and relationships. Their subject houses are 9 and 7.

FATHER_A_KING = _point(
    "father",
    {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 9, "house": 10}]},
    {"vansh": 1.0}, statement="the native's father will be a king",
    chapter="22", verse="6",
)
MANY_WIVES = _point(
    "wives",
    {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 7, "house": 2}]},
    {"prema": 1.0}, statement="the native will have many wives",
    chapter="26", verse="74",
)
BOTH_TRUE = {"house.9.lord.house": 10, "house.7.lord.house": 2}


def test_a_marriage_question_does_not_surface_a_ninth_house_rule():
    """The defect, end to end. Both rules are TRUE of the chart; only one is about
    marriage, and no coverage set for relationships contains the 9th house."""
    from rishivan.council.routing import route_question

    hits = rules_for_question(
        Store([FATHER_A_KING, MANY_WIVES]), [0.0],
        tokens=BOTH_TRUE,
        routing=route_question("Will my marriage be happy?"),
        limit=10,
    )
    assert [hit.rule_key for hit in hits] == ["wives"]


def test_the_same_ninth_house_rule_does_surface_for_a_family_question():
    """The gate is per domain, not a blanket rejection -- §8 gives VANSH the 9th."""
    from rishivan.council.routing import route_question

    hits = rules_for_question(
        Store([FATHER_A_KING, MANY_WIVES]), [0.0],
        tokens=BOTH_TRUE,
        routing=route_question("What does my chart say about my father?"),
        limit=10,
    )
    assert "father" in [hit.rule_key for hit in hits]


def test_each_hit_records_which_domain_claimed_it():
    """§21 traceability at the routing level: a shown rule can say which Rishi owns it."""
    from rishivan.council.routing import route_question

    hits = rules_for_question(
        Store([MANY_WIVES]), [0.0], tokens=BOTH_TRUE,
        routing=route_question("Will my marriage be happy?"), limit=10,
    )
    assert hits[0].domain == "prema"


def test_an_unsupported_question_returns_no_rules():
    """§20: surfaced as unsupported rather than answered from whatever matched."""
    from rishivan.council.routing import route_question

    assert rules_for_question(
        Store([MANY_WIVES]), [0.0], tokens=BOTH_TRUE,
        routing=route_question("How do I rotate a PDF?"), limit=10,
    ) == []


# --- The payload contract ----------------------------------------------------


def test_every_payload_key_retrieval_reads_is_a_key_the_embedder_writes():
    """A reader/writer mismatch here is silent and total.

    `true_rules` read `exceptions` and `modifiers` from the payload while
    `scripts/embed_rules.py` wrote neither, so `applies()` degenerated to `satisfies()`
    and every commentary exception was ignored in production -- while the unit tests
    passed, because they build the payload by hand. Blueprint §6 lists MODIFIERS and
    EXCEPTIONS as Koonji fields; dropping them at the store boundary loses them.
    """
    import re
    from pathlib import Path

    reader = Path("rishivan/rag/rules.py").read_text()
    writer = Path("scripts/embed_rules.py").read_text()

    read_keys = set(re.findall(r'payload\.get\("(\w+)"\)', reader))
    read_keys |= set(re.findall(r'payload\["(\w+)"\]', reader))
    written = set(re.findall(r'^\s+"(\w+)":', writer, re.MULTILINE))

    missing = read_keys - written
    assert not missing, f"retrieval reads keys the embedder never writes: {sorted(missing)}"


# --- BP §4 level 5 and level 2 in ranking ------------------------------------


def _categorised(key, category, school="parashari", verse="1"):
    point = _point(key, CONDITION, {"prema": 1.0}, verse=verse)
    point["metadata"]["rule_category"] = category
    point["metadata"]["school"] = school
    return point


def test_a_timing_question_leads_with_the_timing_rule():
    """§8 rule 2: promise and timing are different reasoning problems."""
    hits = rules_for_question(
        Store([_categorised("promise", "formation", verse="1"),
               _categorised("activation", "timing", verse="2")]),
        [0.0], tokens=CHART,
        routing=route_question("When will I marry?"), limit=5,
    )
    assert [h.rule_key for h in hits][0] == "activation"


def test_a_potential_question_leads_with_the_promise():
    hits = rules_for_question(
        Store([_categorised("activation", "timing", verse="2"),
               _categorised("promise", "formation", verse="1")]),
        [0.0], tokens=CHART,
        routing=route_question("Will my marriage be happy?"), limit=5,
    )
    assert [h.rule_key for h in hits][0] == "promise"


def test_the_other_category_is_still_returned():
    """A preference, not a filter. §4-11's protocols run promise -> ... -> Dasha, so a
    timing question still needs the promise as evidence."""
    hits = rules_for_question(
        Store([_categorised("promise", "formation", verse="1"),
               _categorised("activation", "timing", verse="2")]),
        [0.0], tokens=CHART,
        routing=route_question("When will I marry?"), limit=5,
    )
    assert {h.rule_key for h in hits} == {"promise", "activation"}


def test_each_hit_carries_its_school():
    """§8 rule 5: never mix schools silently -- label both."""
    hits = rules_for_question(
        Store([_categorised("p", "formation", school="prashna")]),
        [0.0], tokens=CHART,
        routing=route_question("Will my marriage be happy?"), limit=5,
    )
    assert hits[0].school == "prashna"


def test_hits_can_be_grouped_by_school_without_merging():
    from rishivan.rag.rules import group_by_school

    hits = rules_for_question(
        Store([_categorised("a", "formation", school="parashari", verse="1"),
               _categorised("b", "formation", school="prashna", verse="2"),
               _categorised("c", "formation", school="parashari", verse="3")]),
        [0.0], tokens=CHART,
        routing=route_question("Will my marriage be happy?"), limit=9,
    )
    grouped = group_by_school(hits)
    assert set(grouped) == {"parashari", "prashna"}
    assert len(grouped["parashari"]) == 2
    assert len(grouped["prashna"]) == 1


# --- BP §8 rule 4: hierarchy of evidence -------------------------------------


def test_a_classical_rule_outranks_a_modern_one_all_else_equal():
    """§8 rule 4: "Primary classical source > established commentary > established
    practitioner > experimental material." Inert while every rule is BPHS; it matters
    the moment Hindu Predictive Astrology (S3) rules sit beside Prasna Marga (S0)."""
    classical = _categorised("classical", "formation", verse="1")
    classical["metadata"]["tier"] = "S0"
    modern = _categorised("modern", "formation", verse="2")
    modern["metadata"]["tier"] = "S3"

    hits = rules_for_question(
        Store([modern, classical]), [0.0], tokens=CHART,
        routing=route_question("Will my marriage be happy?"), limit=5,
    )
    assert [h.rule_key for h in hits] == ["classical", "modern"]


def test_a_hit_carries_its_tier():
    point = _categorised("r", "formation")
    point["metadata"]["tier"] = "S1"
    hits = rules_for_question(
        Store([point]), [0.0], tokens=CHART,
        routing=route_question("Will my marriage be happy?"), limit=5,
    )
    assert hits[0].tier == "S1"


def test_an_untiered_rule_is_treated_as_experimental_not_classical():
    hits = rules_for_question(
        Store([_categorised("untiered", "formation")]), [0.0], tokens=CHART,
        routing=route_question("Will my marriage be happy?"), limit=5,
    )
    assert hits[0].tier == "S5"


# --- BP §6's REMEDIES field across the store boundary -------------------------


def test_remedies_survive_the_store_boundary():
    """Blueprint §6 lists REMEDIES as a Koonji field and the extractor populates it, but
    it was written to Postgres and dropped at the Qdrant boundary -- unreachable at query
    time, exactly as `exceptions` and `modifiers` were."""
    remedy = [{"kind": "mantra", "detail": "hymns to Shiva"}]
    payload = {
        "rule_key": "r",
        "condition": json.dumps(CONDITION),
        "remedies": json.dumps(remedy),
    }
    hit = _payload_to_hit(payload, relevance=1.0)
    assert hit is not None
    assert hit.remedies == remedy


def test_a_rule_with_no_remedies_gets_an_empty_list_not_none():
    hit = _payload_to_hit(
        {"rule_key": "r", "condition": json.dumps(CONDITION)}, relevance=1.0
    )
    assert hit is not None
    assert hit.remedies == []


def test_the_embedder_writes_the_remedies_key():
    """The generic contract test cannot catch this: it compares keys the READER reads,
    so a field neither side handles passes silently."""
    from pathlib import Path

    writer = Path("scripts/embed_rules.py").read_text()
    assert '"remedies"' in writer
