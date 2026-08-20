"""Is this rule this Rishi's evidence? Eight Rishis §4-11 coverage, applied.

The case that motivated the whole layer, using the real conditions:

    BPHS 26.74  the 7th lord in the 2nd    "the native will have many wives"
    BPHS 22.6   the 9th lord in the 10th   "the native's father will be a king"

Both were scored 1.00 for a marriage question, because the extractor tagged them
`Relationships` and `father`, and the answering persona owns both relationships and
family. Their subject houses are 7 and 9, and only one of those is in PREMA's coverage.
"""

from rishivan.council.constitution import CONSTITUTIONS
from rishivan.council.routing import route_question
from rishivan.knowledge.concepts import concepts_of
from rishivan.rag.relevance import concept_relevance, domain_relevance

MANY_WIVES = {"atoms": [
    {"type": "lord_of_house_in_house", "lord_of": 7, "house": 2}
]}
FATHER_A_KING = {"atoms": [
    {"type": "lord_of_house_in_house", "lord_of": 9, "house": 10}
]}
SATURN_IN_THE_SEVENTH = {"atoms": [
    {"type": "planet_in_house", "planet": "saturn", "house": 7}
]}
VENUS_IN_THE_SEVENTH = {"atoms": [
    {"type": "planet_in_house", "planet": "venus", "house": 7}
]}
TENTH_LORD_IN_THE_SECOND = {"atoms": [
    {"type": "lord_of_house_in_house", "lord_of": 10, "house": 2}
]}
SUN_EXALTED = {"atoms": [
    {"type": "dignity_is", "planet": "sun", "dignity": "exalted"}
]}


def relevance(condition, domain):
    return concept_relevance(concepts_of(condition), CONSTITUTIONS[domain])


# ── The gate ─────────────────────────────────────────────────────────────────


def test_the_seventh_lord_is_premas_evidence():
    assert relevance(MANY_WIVES, "prema") > 0


def test_the_ninth_lord_is_not_premas_evidence():
    """The defect, stated as a test. PREMA covers 7/2/8/11; this rule's subject is 9."""
    assert relevance(FATHER_A_KING, "prema") == 0.0


def test_the_ninth_lord_IS_vanshs_evidence():
    """The gate must be domain-specific, not a blanket rejection: §8 gives VANSH the
    9th house, and the father is squarely its subject."""
    assert relevance(FATHER_A_KING, "vansh") > 0


def test_a_planet_in_the_seventh_is_premas_evidence():
    assert relevance(SATURN_IN_THE_SEVENTH, "prema") > 0


def test_the_tenth_lord_is_karmas_evidence_not_premas():
    assert relevance(TENTH_LORD_IN_THE_SECOND, "karma") > 0
    assert relevance(TENTH_LORD_IN_THE_SECOND, "prema") == 0.0


# ── Refinement within the gate ───────────────────────────────────────────────


def test_a_named_planet_of_the_domain_scores_higher():
    """§5 names Venus and Jupiter for PREMA. Two rules about the same house are not
    equally strong evidence when one names the domain's own significator."""
    assert relevance(VENUS_IN_THE_SEVENTH, "prema") > relevance(
        SATURN_IN_THE_SEVENTH, "prema"
    )


def test_a_houseless_rule_can_still_be_evidence_but_ranks_below_one_with_a_house():
    """`dignity_is{sun}` names no house, so coverage cannot judge it by subject. §9 lists
    the Sun for AAROGYA, so it is admissible -- but weaker than a rule about the 6th."""
    houseless = relevance(SUN_EXALTED, "aarogya")
    housed = relevance(
        {"atoms": [{"type": "planet_in_house", "planet": "sun", "house": 6}]}, "aarogya"
    )
    assert 0 < houseless < housed


def test_a_houseless_rule_naming_an_unrelated_planet_is_not_evidence():
    assert relevance(SUN_EXALTED, "yatra") == 0.0


def test_relevance_never_exceeds_one():
    for condition in (MANY_WIVES, VENUS_IN_THE_SEVENTH, SATURN_IN_THE_SEVENTH):
        for domain in CONSTITUTIONS:
            assert 0.0 <= relevance(condition, domain) <= 1.0


# ── Routed against a real question ───────────────────────────────────────────


def test_a_marriage_question_prefers_the_marriage_rule_over_the_father_rule():
    """The end-to-end statement of the bug."""
    routing = route_question("Will my marriage be happy?")
    wives, _ = domain_relevance(concepts_of(MANY_WIVES), routing)
    father, _ = domain_relevance(concepts_of(FATHER_A_KING), routing)
    assert wives > father


def test_a_secondary_domain_scores_below_the_primary():
    """§12 invokes secondaries for independent evidence, not as equals."""
    routing = route_question("Will my marriage be happy and will my family grow?")
    assert routing.primary == "prema"
    assert "vansh" in routing.secondary
    wives, wives_domain = domain_relevance(concepts_of(MANY_WIVES), routing)
    father, father_domain = domain_relevance(concepts_of(FATHER_A_KING), routing)
    assert wives_domain == "prema"
    assert father_domain == "vansh"
    assert wives > father > 0


def test_an_unsupported_question_yields_no_relevance():
    routing = route_question("What is the airspeed velocity of an unladen swallow?")
    score, domain = domain_relevance(concepts_of(MANY_WIVES), routing)
    assert score == 0.0
    assert domain is None


def test_the_domain_that_scored_is_reported():
    """A rule shown to a user must be able to say which Rishi claimed it -- §21's
    traceability, at the level of the routing decision."""
    routing = route_question("What career suits me?")
    _, domain = domain_relevance(concepts_of(TENTH_LORD_IN_THE_SECOND), routing)
    assert domain == "karma"


# --- Primary versus supporting houses ---------------------------------------
#
# §4-11 do not list their houses as equals. §5 gives PREMA "7th house/lord" and then
# "2nd/8th/11th"; §7 gives KARMA "10th house/lord" and then "Lagna/lord; 6th; 2nd; 11th";
# §17's own decision tree separates ARTHA's "BASELINE PROMISE" (Lagna, 2nd, 11th) from
# "SUPPORTING WEALTH HOUSES" (5th, 9th, 10th). Flattening them is why a marriage
# question ranked "promoter of wealth" -- a 2nd-house rule -- level with "many wives".

SECOND_LORD_RULE = {"atoms": [
    {"type": "lord_of_house_in_house", "lord_of": 2, "house": 1}
]}


def test_premas_own_house_outranks_its_supporting_houses():
    assert relevance(MANY_WIVES, "prema") > relevance(SECOND_LORD_RULE, "prema")


def test_a_supporting_house_is_still_evidence():
    """§5 lists the 2nd, so a 2nd-house rule is admissible for PREMA -- just weaker."""
    assert relevance(SECOND_LORD_RULE, "prema") > 0


def test_karmas_own_house_outranks_its_supporting_houses():
    tenth = {"atoms": [{"type": "lord_of_house_in_house", "lord_of": 10, "house": 2}]}
    assert relevance(tenth, "karma") > relevance(SECOND_LORD_RULE, "karma")


def test_every_supporting_house_is_inside_the_coverage_set():
    """`houses` stays the union, so the gate is unchanged by the split."""
    for domain, c in CONSTITUTIONS.items():
        assert c.primary_houses <= c.houses, domain
        assert c.supporting_houses <= c.houses, domain
        assert c.primary_houses | c.supporting_houses == c.houses, domain


def test_no_domain_leaves_its_primary_houses_empty():
    for domain, c in CONSTITUTIONS.items():
        assert c.primary_houses, f"{domain} names no house of its own"
