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


from rishivan.council.domains import primary_rishi_for


def test_a_single_owner_domain_resolves_to_that_persona():
    assert primary_rishi_for("artha") == "dhruvan"
    assert primary_rishi_for("prema") == "medhan"
    assert primary_rishi_for("karma") == "dhruvan"
    assert primary_rishi_for("vansh") == "medhan"
    assert primary_rishi_for("aarogya") == "medhan"
    assert primary_rishi_for("yatra") == "dhruvan"


def test_a_two_owner_domain_lets_the_classifier_break_the_tie():
    """ATMA is owned HIGH by both agam and tattvan; DHARMA by agam and pragnav."""
    assert primary_rishi_for("atma", classifier_pick="tattvan") == "tattvan"
    assert primary_rishi_for("atma", classifier_pick="agam") == "agam"
    assert primary_rishi_for("dharma", classifier_pick="pragnav") == "pragnav"


def test_a_tie_ignores_a_classifier_pick_that_does_not_own_the_domain():
    """The LLM breaks ties; it does not override coverage. `medhan` owns no ATMA."""
    assert primary_rishi_for("atma", classifier_pick="medhan") in {"agam", "tattvan"}


def test_a_tie_is_deterministic_without_a_classifier_pick():
    assert primary_rishi_for("atma") == primary_rishi_for("atma")
    assert primary_rishi_for("atma") in {"agam", "tattvan"}


def test_an_unrouted_question_falls_back_to_a_domain_rishi():
    """Spec Section 2 step 5. Never vyom -- an all-MEDIUM fallback gates nothing."""
    assert primary_rishi_for(None) == "tattvan"
    assert primary_rishi_for(None, classifier_pick="dhruvan") == "dhruvan"


def test_a_service_rishi_is_never_returned():
    for domain in (*LIFE_DOMAIN_KEYS, None):
        for pick in ("vyom", "ritam", "tejan", None):
            assert primary_rishi_for(domain, classifier_pick=pick) in DOMAIN_RISHIS
