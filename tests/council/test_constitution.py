"""The Rishi Constitutions — Eight Rishis §16, populated from §4-11.

Each §4-11 section gives its Rishi four things: the questions it owns, its astrological
coverage, its protocol, and its sources. These tests pin the coverage sets against the
document, because coverage is what decides whether a rule is this Rishi's evidence.
"""

from rishivan.council.constitution import CONSTITUTIONS
from rishivan.council.domains import LIFE_DOMAIN_KEYS


def test_every_client_domain_has_a_constitution():
    """ER §20: no orphan questions. A domain with no constitution can route nowhere."""
    assert set(CONSTITUTIONS) == set(LIFE_DOMAIN_KEYS)


def test_prema_covers_the_houses_the_document_names():
    """ER §5: "7th house/lord, Venus, Jupiter where relevant, 2nd/8th/11th, D9"."""
    prema = CONSTITUTIONS["prema"]
    assert prema.houses == frozenset({7, 2, 8, 11})
    assert {"venus", "jupiter"} <= prema.planets
    assert "D9" in prema.vargas


def test_artha_covers_the_houses_the_document_names():
    """ER §6: "2nd, 5th, 9th, 10th, 11th; their lords; Lagna/Lagna lord; D2; D10"."""
    artha = CONSTITUTIONS["artha"]
    assert artha.houses == frozenset({1, 2, 5, 9, 10, 11})
    assert {"D2", "D10"} <= artha.vargas


def test_aarogya_covers_the_houses_the_document_names():
    """ER §9: "Lagna/1st; 6th; 8th; 12th; Sun; Moon"."""
    aarogya = CONSTITUTIONS["aarogya"]
    assert aarogya.houses == frozenset({1, 6, 8, 12})
    assert {"sun", "moon"} <= aarogya.planets


def test_yatra_covers_the_houses_the_document_names():
    """ER §10: "3rd, 4th, 8th, 9th, 12th; Rahu/Ketu; D4"."""
    yatra = CONSTITUTIONS["yatra"]
    assert yatra.houses == frozenset({3, 4, 8, 9, 12})
    assert {"rahu", "ketu"} <= yatra.planets
    assert "D4" in yatra.vargas


def test_no_constitution_covers_every_house():
    """A coverage set that spans all twelve houses cannot discriminate, which is the
    whole reason this layer exists."""
    for domain, constitution in CONSTITUTIONS.items():
        assert len(constitution.houses) < 12, f"{domain} covers every house"


def test_every_constitution_states_its_protocol_and_sources():
    """ER §14 requires an analysis order and a source mapping per Rishi."""
    for domain, constitution in CONSTITUTIONS.items():
        assert constitution.protocol, f"{domain} has no protocol"
        assert constitution.source_families, f"{domain} names no sources"


def test_aarogya_carries_the_forbidden_claims():
    """ER §9 states them as absolute: never diagnose, never predict death as certainty."""
    assert CONSTITUTIONS["aarogya"].forbidden_claims


def test_dharma_records_that_its_corpus_is_missing():
    """ER §11 gives Dharma the Gita, Upanishads and Yoga Sutras. None are ingested, so
    the constitution must say so rather than imply Dharma can answer from scripture."""
    assert CONSTITUTIONS["dharma"].unavailable_sources
