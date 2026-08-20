"""Book domain taxonomy and Rishi → book-domain mapping.

The 8 Rishis are personalities on top of one shared knowledge base.
Domain filters control which books each Rishi draws from at query time.
"""
from __future__ import annotations

from enum import Enum


class BookDomain(str, Enum):
    FOUNDATION   = "foundation"    # BPHS, Phaladeepika, Saravali, Jataka Parijata, Hindu Predictive Astrology
    PREDICTION   = "prediction"    # Brihat Jataka, Laghu Parashari, Sarvartha Chintamani, Hindu Predictive Astrology
    TIMING       = "timing"        # Laghu Parashari, BPHS timing chapters
    MUHURTA      = "muhurta"       # Muhurta Chintamani, Dharma Sindhu, Vivaha Patalam
    PRASHNA      = "prashna"       # Prashna Marga, Prashna Tantra
    REMEDIAL     = "remedial"      # BPHS remedies chapters
    NADI         = "nadi"          # Deva Keralam / Chandra Kala Nadi
    WEALTH       = "wealth"        # Bhavartha Ratnakara, Sarvartha Chintamani
    COMPATIBILITY = "compatibility" # Muhurta vivaha sections, Vivaha Patalam
    NUMEROLOGY   = "numerology"    # Cheiro's Book of Numbers, Complete Book of Numerology, Numerology: Key to Your Inner Self


# ── Book slug → domain tags (multi-tag per book) ────────────────────────────

SLUG_DOMAINS: dict[str, list[str]] = {
    "bphs-gcsharma-vol1":                   [BookDomain.FOUNDATION, BookDomain.TIMING, BookDomain.REMEDIAL],
    "bphs-gcsharma-vol2":                   [BookDomain.FOUNDATION, BookDomain.TIMING, BookDomain.REMEDIAL],
    "phaladeepika-sastri-1950":             [BookDomain.FOUNDATION],
    "saravali-santhanam-en":                [BookDomain.FOUNDATION],
    "jatakaparijata-sastri-vol1":           [BookDomain.FOUNDATION],
    "jatakaparijata-sastri-vol2":           [BookDomain.FOUNDATION],
    "brihatjataka-row-1919":                [BookDomain.PREDICTION],
    "laghu-parashari":                      [BookDomain.PREDICTION, BookDomain.TIMING],
    "sarvartha-chintamani":                 [BookDomain.PREDICTION, BookDomain.WEALTH],
    "bhavartha-ratnakara-by-b-v-raman-text": [BookDomain.WEALTH],
    "muhurtachintamani":                    [BookDomain.MUHURTA, BookDomain.COMPATIBILITY],
    "prasnamarga-raman-part1":              [BookDomain.PRASHNA],
    "prasnamarga-raman-part2":              [BookDomain.PRASHNA],
    "prashna-tantra":                       [BookDomain.PRASHNA],
    "devakeralam-chandrakalanadi-vol1":     [BookDomain.NADI],
    "hindupredictiveastrology-raman":       [BookDomain.FOUNDATION, BookDomain.PREDICTION],
    "dharma-sindhu":                        [BookDomain.MUHURTA],
    "vivaha-patalam":                       [BookDomain.MUHURTA, BookDomain.COMPATIBILITY],
    "cheiros-book-of-numbers":              [BookDomain.NUMEROLOGY],
    "the-complete-book-of-numerology":      [BookDomain.NUMEROLOGY],
    "numerology-key-to-your-inner-self":    [BookDomain.NUMEROLOGY],
}


def domains_for_slug(slug: str) -> list[str]:
    """Return domain tags for a book slug; falls back to FOUNDATION."""
    norm = slug.lower().strip()
    if norm in SLUG_DOMAINS:
        return [d.value for d in SLUG_DOMAINS[norm]]
    for known, domains in SLUG_DOMAINS.items():
        if norm.startswith(known):
            return [d.value for d in domains]
    return [BookDomain.FOUNDATION.value]


# ── Rishi → book domains they draw from ─────────────────────────────────────

RISHI_BOOK_DOMAINS: dict[str, list[str]] = {
    "agam":    [BookDomain.FOUNDATION, BookDomain.NADI],
    "vyom":    [BookDomain.FOUNDATION, BookDomain.PREDICTION, BookDomain.NADI],
    "dhruvan": [BookDomain.WEALTH, BookDomain.PREDICTION, BookDomain.FOUNDATION, BookDomain.NUMEROLOGY],
    "ritam":   [BookDomain.TIMING, BookDomain.MUHURTA, BookDomain.FOUNDATION],
    "tejan":   [BookDomain.REMEDIAL, BookDomain.FOUNDATION],
    "medhan":  [BookDomain.FOUNDATION, BookDomain.PREDICTION, BookDomain.PRASHNA, BookDomain.COMPATIBILITY, BookDomain.NUMEROLOGY],
    "tattvan": [BookDomain.PREDICTION, BookDomain.NADI, BookDomain.FOUNDATION],
    "pragnav": [BookDomain.FOUNDATION, BookDomain.NADI],
}


# ── Query-domain taxonomy (for chart routing) ────────────────────────────────

class QueryDomain(str, Enum):
    NATAL   = "natal"
    MUHURTA = "muhurta"
    PRASHNA = "prashna"
    GENERAL = "general"


# ── Persona Rishi → client life-domain Rishi (weighted) ──────────────────────
#
# The client's blueprint names eight Rishis by life domain (Eight Rishis doc §21):
# ATMA, PREMA, ARTHA, KARMA, VANSH, AAROGYA, YATRA, DHARMA. The eight personas in
# this repo are a different taxonomy under the same count, so the two do not pair
# one-to-one and a rename would lose information:
#
#   * `medhan` alone spans three client domains (prema + vansh + aarogya).
#   * `dhruvan` spans two (artha + karma).
#   * `agam` and `tattvan` both look at atma.
#   * `vyom`, `ritam` and `tejan` are not life domains at all — they are technique
#     lenses (cosmic patterns, timing, remedies). The client treats these as shared
#     services rather than Rishis: Muhurta is a "cross-domain timing service"
#     (§13) and remedies are "a separate remedy corpus" (Blueprint §17).
#
# So the mapping is weighted and many-to-many, which is how the client expresses
# its own Book × Rishi matrix (§15: High/Medium/Low, "not claims that a source
# contains equal coverage of every Rishi"). A persona's weight for a domain answers
# one question: when this Rishi speaks, how relevant are rules tagged with that
# domain?
#
# Extracted rules carry `rishi_affinity` in the CLIENT's keys, because that is what
# the corpus is annotated against. This table is what lets a persona retrieve them.

LIFE_DOMAIN_KEYS: tuple[str, ...] = (
    "atma",
    "prema",
    "artha",
    "karma",
    "vansh",
    "aarogya",
    "yatra",
    "dharma",
)
"""The client's eight life-domain Rishis, in the client's order.

Duplicated from `app.models.knowledge.affinity.RISHI_KEYS` rather than imported: the
knowledge layer pulls in SQLAlchemy, and this module is on the Streamlit request path.
A contract test asserts the two stay identical — `vocab.py` warns in its own docstring
that "a second copy is a second thing to drift", so the copy is only safe with the test.
"""

DOMAIN_HIGH = 1.0
DOMAIN_MEDIUM = 0.6
DOMAIN_LOW = 0.3
"""Mirrors the client's High/Medium/Low weighting, and the numeric values already
used by `BookRishiAffinity`."""

_ALL_MEDIUM = dict.fromkeys(LIFE_DOMAIN_KEYS, DOMAIN_MEDIUM)

RISHI_LIFE_DOMAINS: dict[str, dict[str, float]] = {
    # "Soul purpose, karma & life lessons". Note the trap: `agam`'s "karma" is
    # spiritual karma, which is the client's DHARMA. The client's KARMA is career.
    "agam": {"atma": DOMAIN_HIGH, "dharma": DOMAIN_HIGH},

    # "Planets, nakshatras, yogas & cosmic patterns" — technique, not a life domain,
    # and the classifier's fallback Rishi when routing fails or is unrecognised. A
    # fallback must be able to reach everything, so it is uniformly medium.
    "vyom": dict(_ALL_MEDIUM),

    # "Career, wealth, leadership & business" — artha + karma. It also carries YATRA,
    # because property and relocation are material decisions and no other persona is
    # closer. This is the weakest cell in the table: the client gives Yatra its own
    # protocol (D4, the 3rd/4th/9th/12th houses, Prashna) that no persona implements.
    "dhruvan": {
        "artha": DOMAIN_HIGH,
        "karma": DOMAIN_HIGH,
        "yatra": DOMAIN_HIGH,
        "atma": DOMAIN_LOW,
    },

    # "Dashas, transits, muhurta & perfect timing" — the client's cross-domain timing
    # service. Timing applies to every domain, so uniformly medium.
    "ritam": dict(_ALL_MEDIUM),

    # "Remedies, mantras, gemstones & transformative practice". The client keeps
    # remedies out of the Rishi set entirely, attaching them to rules and to a
    # separate corpus, so this persona has no domain it owns outright.
    "tejan": {
        "dharma": DOMAIN_MEDIUM,
        "aarogya": DOMAIN_MEDIUM,
        "atma": DOMAIN_LOW,
        "prema": DOMAIN_LOW,
        "artha": DOMAIN_LOW,
        "karma": DOMAIN_LOW,
        "vansh": DOMAIN_LOW,
        "yatra": DOMAIN_LOW,
    },

    # "Relationships, family, health & emotional wellbeing" — three client Rishis in
    # one persona. Anything routed here may draw on all three rule sets.
    "medhan": {
        "prema": DOMAIN_HIGH,
        "vansh": DOMAIN_HIGH,
        "aarogya": DOMAIN_HIGH,
        "atma": DOMAIN_LOW,
    },

    # "Hidden patterns, strengths & the deeper truth of the chart" — the client's ATMA
    # (identity, tendencies, strengths, weaknesses, chart promise).
    "tattvan": {"atma": DOMAIN_HIGH, "dharma": DOMAIN_LOW},

    # "Spiritual growth, intuition, liberation & inner awakening" — the client's DHARMA.
    "pragnav": {"dharma": DOMAIN_HIGH, "atma": DOMAIN_MEDIUM},
}
"""Persona → client life domain, weighted. Every client domain has at least one
persona rating it High, so no domain is orphaned (Eight Rishis doc §20: "No orphan
questions"). Enforced by test, not by convention."""


def life_domains_for_rishi(
    rishi: str, *, min_weight: float = DOMAIN_MEDIUM
) -> list[str]:
    """Client life domains this persona may draw rules from, strongest first.

    `min_weight` is the retrieval threshold. At the default a persona sees the domains
    it owns or shares; lower it to DOMAIN_LOW to let a persona reach adjacent material
    when its own domains return nothing.
    """
    weights = RISHI_LIFE_DOMAINS.get(rishi.lower(), {})
    return [
        domain
        for domain, weight in sorted(
            weights.items(), key=lambda kv: (-kv[1], LIFE_DOMAIN_KEYS.index(kv[0]))
        )
        if weight >= min_weight
    ]


def rishis_for_life_domain(
    domain: str, *, min_weight: float = DOMAIN_MEDIUM
) -> list[str]:
    """The reverse lookup: which personas can speak to a client life domain."""
    return [
        rishi
        for rishi, weights in RISHI_LIFE_DOMAINS.items()
        if weights.get(domain.lower(), 0.0) >= min_weight
    ]


def rule_relevance(rishi: str, rishi_affinity: dict[str, float] | None) -> float:
    """How relevant one extracted rule is to one persona, in 0..1.

    `rishi_affinity` is the per-rule vector over the CLIENT's eight keys, which the
    extractor produces and the client requires to be generated "chapter/section/rule by
    rule" (§15) rather than inherited from the book. The score is the best single
    domain agreement rather than a sum, so a rule that is strongly about one relevant
    domain outranks one that is weakly about several — the client's instruction is to
    invoke the minimum set that gives independent evidence, not to reward breadth.

    Returns 0.0 for an unknown persona or a missing affinity vector, so an unannotated
    rule is never silently treated as universally relevant.
    """
    weights = RISHI_LIFE_DOMAINS.get(rishi.lower(), {})
    if not weights or not rishi_affinity:
        return 0.0
    return max(
        (
            persona_weight * float(rishi_affinity.get(domain, 0.0) or 0.0)
            for domain, persona_weight in weights.items()
        ),
        default=0.0,
    )
