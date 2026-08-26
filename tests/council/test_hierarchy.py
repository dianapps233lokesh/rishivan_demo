"""Blueprint §12: one evidence hierarchy per life domain.

The invariants here are doctrinal, not mechanical, so they are asserted rather
than left to the shape of the table. A row that quietly weights a D9
confirmation above the D1 placement it confirms is not a typo anyone would
notice reading the file.
"""

from rishivan.council.hierarchy import (
    DEFAULT_DOMAIN,
    HIERARCHIES,
    TIERS,
    hierarchy_for,
)
from rishivan.koonji.router import DOMAIN_KEYWORDS


def test_every_routable_domain_has_a_hierarchy():
    """A domain the router can produce and the table cannot answer for falls
    back to temperament, which reads as an answer about the wrong subject."""
    assert set(DOMAIN_KEYWORDS) <= set(HIERARCHIES)


def test_marriage_carries_the_blueprint_row():
    h = hierarchy_for("domain.relationship")
    assert h.houses[0] == 7
    assert 7 in h.lords
    assert "graha.venus" in h.karakas and "graha.jupiter" in h.karakas
    assert "D9" in h.vargas
    assert "upapada" in h.jaimini and "darakaraka" in h.jaimini


def test_career_names_d10_and_the_tenth():
    h = hierarchy_for("domain.career")
    assert h.houses[0] == 10
    assert "D10" in h.vargas
    assert "amatyakaraka" in h.jaimini


def test_tier_weights_are_declared_for_every_tier():
    for domain, h in HIERARCHIES.items():
        assert set(h.tier_weights) == set(TIERS), domain


def test_a_house_placement_always_outranks_a_varga_confirmation():
    """The blueprint's whole complaint about one generic scoring formula."""
    for domain, h in HIERARCHIES.items():
        assert h.tier_weights["house"] > h.tier_weights["varga"], domain


def test_the_vargas_named_are_vargas_the_policy_registry_knows():
    from rishivan.varga.policy import POLICIES

    for domain, h in HIERARCHIES.items():
        assert set(h.vargas) <= set(POLICIES), domain


def test_the_karakas_named_are_grahas_the_registry_knows():
    """A karaka spelled differently from the registry is a karaka no rule and
    no fact set can ever be matched against."""
    from rishivan.koonji.registry import RegistryKind, seed_registry

    entities = seed_registry().symbols(RegistryKind.ENTITY)
    for domain, h in HIERARCHIES.items():
        for karaka in h.karakas:
            assert karaka in entities, f"{domain}: {karaka}"


def test_houses_are_real_bhavas():
    for domain, h in HIERARCHIES.items():
        assert all(1 <= b <= 12 for b in h.houses), domain
        assert all(1 <= b <= 12 for b in h.lords), domain


def test_an_unknown_domain_falls_back_rather_than_raising():
    assert hierarchy_for("domain.nonexistent") is HIERARCHIES[DEFAULT_DOMAIN]


def test_longevity_demands_more_corroboration_than_temperament():
    """A mortality claim resting on one verse is the single most damaging
    thing this system could emit."""
    assert (
        hierarchy_for("domain.longevity").min_independent_sources
        > hierarchy_for("domain.temperament").min_independent_sources
    )


def test_a_domain_needing_a_dasha_is_one_about_events():
    """Temperament is a description and needs no period; marriage is an event
    and does. Getting this backwards produces a dated personality."""
    assert hierarchy_for("domain.relationship").requires_dasha
    assert not hierarchy_for("domain.temperament").requires_dasha


def test_every_hierarchy_names_at_least_one_house():
    for domain, h in HIERARCHIES.items():
        assert h.houses, domain


def test_the_domain_field_matches_its_key():
    for key, h in HIERARCHIES.items():
        assert h.domain == key


# ==========================================================================
# The bridge to the client's life-domain taxonomy
# ==========================================================================


def test_no_koonji_domain_is_orphaned_from_the_client_taxonomy():
    """An orphaned domain means a question routes to a rule set no persona is
    allowed to read, and the symptom is an empty answer nobody can trace."""
    from rishivan.council.domains import LIFE_DOMAIN_KEYS
    from rishivan.council.hierarchy import LIFE_DOMAIN_OF

    assert set(LIFE_DOMAIN_OF) == set(HIERARCHIES)
    for domain, keys in LIFE_DOMAIN_OF.items():
        assert keys, domain
        assert set(keys) <= set(LIFE_DOMAIN_KEYS), domain


def test_the_marriage_rishi_can_reach_marriage_rules():
    from rishivan.council.hierarchy import koonji_domains_for_rishi

    assert "domain.relationship" in koonji_domains_for_rishi("medhan")


def test_the_wealth_rishi_can_reach_wealth_and_career():
    from rishivan.council.hierarchy import koonji_domains_for_rishi

    reach = koonji_domains_for_rishi("dhruvan")
    assert {"domain.wealth", "domain.career"} <= reach


def test_a_service_rishi_reaches_everything():
    """vyom is the fallback voice and rates every life domain MEDIUM. A
    fallback that reaches nothing is not a fallback."""
    from rishivan.council.hierarchy import koonji_domains_for_rishi

    assert koonji_domains_for_rishi("vyom") == frozenset(HIERARCHIES)


def test_an_unknown_persona_reaches_nothing():
    """Silently reaching everything would let a typo in a roster entry read as
    a Rishi with universal competence."""
    from rishivan.council.hierarchy import koonji_domains_for_rishi

    assert koonji_domains_for_rishi("nobody") == frozenset()


def test_every_persona_reaches_at_least_one_domain():
    from rishivan.council.personas import ALL_RISHI_NAMES
    from rishivan.council.hierarchy import koonji_domains_for_rishi

    for rishi in ALL_RISHI_NAMES:
        assert koonji_domains_for_rishi(rishi), rishi


def test_the_lookup_is_case_insensitive():
    from rishivan.council.hierarchy import koonji_domains_for_rishi

    assert koonji_domains_for_rishi("MEDHAN") == koonji_domains_for_rishi("medhan")
