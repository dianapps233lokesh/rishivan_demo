"""The persona -> client life-domain mapping, and the drift guard it depends on.

The repo carries two different sets of eight Rishi names: the client's life domains
(`atma`..`dharma`, which the corpus is annotated with) and this repo's personas
(`agam`..`pragnav`, which answer users). They are different taxonomies under the same
count, so the mapping is weighted and many-to-many. If it breaks, rules stop reaching the
Rishi that should cite them -- and nothing raises.
"""

from rishivan.models.knowledge.affinity import RISHI_KEYS, WEIGHT_HIGH
from rishivan.council.domains import (
    DOMAIN_HIGH,
    LIFE_DOMAIN_KEYS,
    RISHI_LIFE_DOMAINS,
    life_domains_for_rishi,
    rishis_for_life_domain,
    rule_relevance,
)
from rishivan.council.personas import ALL_RISHI_NAMES


def test_life_domain_keys_match_the_knowledge_layer_exactly():
    """The copy exists because importing the knowledge layer would pull SQLAlchemy onto
    the Streamlit request path. `vocab.py` warns what an unguarded copy costs: "a second
    copy is a second thing to drift"."""
    assert LIFE_DOMAIN_KEYS == RISHI_KEYS


def test_weights_match_the_knowledge_layer():
    assert DOMAIN_HIGH == WEIGHT_HIGH


def test_every_persona_has_a_mapping():
    """A persona with no mapping retrieves no rules and degrades to page search without
    ever saying so."""
    assert set(RISHI_LIFE_DOMAINS) == set(ALL_RISHI_NAMES)


def test_every_client_domain_has_at_least_one_high_owner():
    """Eight Rishis §20: "No orphan questions." Yatra is the cell to watch -- no persona is
    really a movement/property specialist, so it is assigned deliberately rather than left
    empty."""
    for domain in LIFE_DOMAIN_KEYS:
        owners = [
            rishi
            for rishi, weights in RISHI_LIFE_DOMAINS.items()
            if weights.get(domain) == DOMAIN_HIGH
        ]
        assert owners, f"no persona owns {domain}"


def test_no_mapping_names_an_unknown_domain():
    for rishi, weights in RISHI_LIFE_DOMAINS.items():
        unknown = set(weights) - set(LIFE_DOMAIN_KEYS)
        assert not unknown, f"{rishi} maps unknown domains {unknown}"


def test_medhan_reaches_all_three_of_its_client_domains():
    """`medhan` is "relationships, family, health" -- one persona over three client
    Rishis. Dropping any of the three silently narrows what it can cite."""
    assert set(life_domains_for_rishi("medhan")) >= {"prema", "vansh", "aarogya"}


def test_dhruvan_reaches_wealth_career_and_property():
    assert set(life_domains_for_rishi("dhruvan")) >= {"artha", "karma", "yatra"}


def test_the_fallback_rishi_can_reach_everything():
    """`classifier.py` falls back to `vyom` when routing returns something unrecognised. A
    fallback that reaches only part of the corpus turns a routing miss into a silent
    retrieval miss."""
    assert set(life_domains_for_rishi("vyom")) == set(LIFE_DOMAIN_KEYS)


def test_reverse_lookup_agrees_with_forward_lookup():
    for rishi in RISHI_LIFE_DOMAINS:
        for domain in life_domains_for_rishi(rishi):
            assert rishi in rishis_for_life_domain(domain)


def test_relevance_is_zero_without_an_affinity_vector():
    """Scoring an unannotated rule as universally relevant would let any Rishi cite any
    rule."""
    assert rule_relevance("dhruvan", None) == 0.0
    assert rule_relevance("dhruvan", {}) == 0.0


def test_relevance_is_zero_for_an_unknown_persona():
    assert rule_relevance("not-a-rishi", {"artha": 1.0}) == 0.0


def test_relevance_prefers_the_strongest_single_agreement():
    """§12's master rule is to invoke the minimum set giving independent evidence, so a
    rule strongly about one relevant domain must outrank one weakly about several."""
    focused = rule_relevance("dhruvan", {"artha": 1.0})
    scattered = rule_relevance("dhruvan", {"artha": 0.3, "karma": 0.3, "yatra": 0.3})
    assert focused > scattered


def test_a_marriage_rule_does_not_reach_the_career_rishi():
    """The specialisation the client's design rests on. `dhruvan` covers wealth, career
    and property; a marriage rule is not its evidence."""
    from rishivan.rag.rules import MIN_RELEVANCE

    marriage = {"prema": 1.0}
    assert rule_relevance("medhan", marriage) >= MIN_RELEVANCE
    assert rule_relevance("dhruvan", marriage) < MIN_RELEVANCE
