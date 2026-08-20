"""Which personas may answer, and which may only compute.

The split is not new information -- it is already latent in RISHI_LIFE_DOMAINS, where
vyom and ritam rate every domain exactly MEDIUM and tejan rates every domain LOW-MEDIUM,
so none of the three owns anything. These tests pin that reading down so a future edit to
the weights cannot silently promote a service Rishi to a voice.
"""

from rishivan.council.domains import (
    DOMAIN_RISHIS,
    LIFE_DOMAIN_KEYS,
    RISHI_LIFE_DOMAINS,
    SERVICE_RISHIS,
)


def test_the_two_classes_partition_every_persona():
    assert DOMAIN_RISHIS | SERVICE_RISHIS == set(RISHI_LIFE_DOMAINS)
    assert not (DOMAIN_RISHIS & SERVICE_RISHIS)


def test_a_service_rishi_owns_no_life_domain():
    """The definition of the class: no HIGH weight anywhere."""
    for rishi in SERVICE_RISHIS:
        weights = RISHI_LIFE_DOMAINS[rishi]
        assert max(weights.values(), default=0.0) < 1.0, rishi


def test_every_domain_rishi_owns_at_least_one_life_domain():
    for rishi in DOMAIN_RISHIS:
        weights = RISHI_LIFE_DOMAINS[rishi]
        assert max(weights.values(), default=0.0) == 1.0, rishi


def test_every_life_domain_has_a_domain_rishi_that_owns_it():
    """ER 20: no orphan questions. Every domain must reach a persona that can SPEAK,
    not merely one that can contribute."""
    for domain in LIFE_DOMAIN_KEYS:
        owners = [
            r for r in DOMAIN_RISHIS
            if RISHI_LIFE_DOMAINS[r].get(domain, 0.0) == 1.0
        ]
        assert owners, domain
