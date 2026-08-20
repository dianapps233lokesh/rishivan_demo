"""Query-domain taxonomy and the persona -> client life-domain mapping.

The ten-tag `BookDomain` taxonomy that used to live here is gone. It appeared in neither
client document and flattened three of Blueprint §4's five levels into one list --
`muhurta`/`prashna`/`nadi` are schools (level 2), `wealth`/`compatibility` are life
domains (level 4), `numerology` is a universe (level 1). Retrieval now filters on §4's
own levels; see `council.source_matrix`.
"""
from __future__ import annotations

from enum import Enum


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

Duplicated from `rishivan.models.knowledge.affinity.RISHI_KEYS` rather than imported: the
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


SERVICE_RISHIS: frozenset[str] = frozenset({"vyom", "ritam", "tejan"})
"""Personas that compute for another Rishi and never speak.

Not a new distinction -- the table above already says it. These three rate every life
domain uniformly (vyom and ritam MEDIUM, tejan LOW-MEDIUM) because they are technique
lenses, not life domains: cosmic patterns, timing, remedies. The client agrees --
§13 calls Muhurta a "cross-domain timing service" and Blueprint §17 puts remedies in a
separate corpus.

Letting one of them answer defeats the coverage gate: a persona rating all eight
domains MEDIUM gates nothing, so `ritam` answering "when will I marry?" meant PREMA's
houses filtered no rules at all.
"""

DOMAIN_RISHIS: frozenset[str] = frozenset(RISHI_LIFE_DOMAINS) - SERVICE_RISHIS
"""Personas that own at least one life domain and may therefore answer."""

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
