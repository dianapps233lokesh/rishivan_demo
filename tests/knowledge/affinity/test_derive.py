"""Deriving a rule's Rishi affinity from its life domains.

Eight Rishis §15: "the production matrix must be generated chapter/section/rule by rule."
This is that derivation, and these tests pin the judgement calls in it -- particularly the
two that look wrong at a glance and are not.
"""

import pytest

from rishivan.knowledge.affinity.derive import (
    LIFE_DOMAIN_KEYWORDS,
    affinity_for,
    unrouted_domains,
)
from rishivan.models.knowledge.affinity import RISHI_KEYS, WEIGHT_HIGH, WEIGHT_MEDIUM


def test_the_table_covers_exactly_the_clients_eight():
    assert set(LIFE_DOMAIN_KEYWORDS) == set(RISHI_KEYS)


@pytest.mark.parametrize(
    "domain,expected",
    [
        ("marriage", "prema"),
        ("relationships", "prema"),
        ("wealth", "artha"),
        ("finances", "artha"),
        ("career", "karma"),
        ("reputation", "karma"),
        ("children", "vansh"),
        ("siblings", "vansh"),
        ("health", "aarogya"),
        ("longevity", "aarogya"),
        ("travel", "yatra"),
        ("foreign residence & travel", "yatra"),
        ("spirituality", "dharma"),
        ("religion", "dharma"),
        ("personality", "atma"),
        ("intelligence", "atma"),
    ],
)
def test_each_domain_reaches_its_owning_rishi(domain, expected):
    assert affinity_for([domain]).get(expected) == WEIGHT_HIGH


def test_spiritual_karma_routes_to_dharma_not_to_the_career_rishi():
    """The single easiest mistake in this mapping. The client's KARMA is career (§3:
    "Profession, employment, business, leadership"); spiritual karma is DHARMA's. A rule
    about karma routed to the career Rishi is a silent mis-routing."""
    weights = affinity_for(["karma"])
    assert weights.get("dharma") == WEIGHT_HIGH
    assert "karma" not in weights


def test_fortune_routes_to_dharma_not_wealth():
    """The 9th house is fortune *and* dharma, and the client puts "higher learning,
    father, dharma" there, so the 9th-house sense is the intended one."""
    assert affinity_for(["fortune"]).get("dharma") == WEIGHT_HIGH


def test_property_is_yatra_with_artha_secondary():
    """§3 gives Yatra "property, residence"; the financial aspect is Artha's, but it does
    not own it."""
    weights = affinity_for(["property"])
    assert weights["yatra"] == WEIGHT_HIGH
    assert weights["artha"] == WEIGHT_MEDIUM


def test_a_compound_domain_reaches_both_rishis():
    """"wealth and career" is one of the real values in the corpus."""
    weights = affinity_for(["wealth and career"])
    assert weights["artha"] == WEIGHT_HIGH
    assert weights["karma"] == WEIGHT_HIGH


def test_the_long_tail_generalises_by_substring():
    """65 of the corpus's 105 domain values appear at most twice. A lookup table would
    miss them on the next book."""
    for value in (
        "wealth and assets",
        "mind and psychology",
        "domestic happiness",
        "valour and courage",
        "death and afterlife",
        "speech & communication",
    ):
        assert affinity_for([value]), value


def test_no_affinity_rather_than_a_guess():
    """A rule with no derivable affinity must be visible as unrouted, not quietly
    assigned to whichever Rishi came first in the table."""
    assert affinity_for([]) == {}
    assert affinity_for(None) == {}
    assert affinity_for(["zzz-not-a-domain"]) == {}


def test_weights_are_only_ever_client_keys():
    for value in ("marriage", "karma", "wealth and career", "happiness"):
        assert set(affinity_for([value])) <= set(RISHI_KEYS)


def test_every_domain_in_the_loaded_rule_base_is_routable():
    """The real coverage contract, measured against the live corpus rather than a fixture.

    An unrouted domain value is a rule no Rishi can cite -- present in the table, invisible
    in every answer.
    """
    from sqlalchemy import select

    from rishivan.models.knowledge.rule import Rule
    from tests.conftest import run_db, skip_without_database

    async def load(session):
        result = await session.execute(select(Rule).where(Rule.status == "parsed"))
        return [rule.life_domains or [] for rule in result.scalars()]

    domains = []
    try:
        domains = run_db(load)
    except Exception as exc:  # noqa: BLE001
        skip_without_database(exc)
    if not domains:
        pytest.skip("rule base is empty")

    assert unrouted_domains(domains) == set()
    assert all(affinity_for(d) for d in domains), "some rules derive no affinity at all"


@pytest.mark.parametrize(
    "domain,expected",
    [
        ("danger", "aarogya"),
        ("mental_state", "atma"),
        ("wounds", "aarogya"),
    ],
)
def test_values_found_only_after_enriching_the_whole_base(domain, expected):
    """These three surfaced when the derivation ran over all 398 rules rather than the
    376 parsed ones -- the `unparsed` rules carry their own domain values, and a keyword
    table built from the parsed subset alone missed them."""
    assert affinity_for([domain]).get(expected)
