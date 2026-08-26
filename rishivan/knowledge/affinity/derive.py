"""Derive each rule's Rishi affinity from what the rule is about.

Per-rule, not inherited from the book: Eight Rishis §15 rates BPHS High for all eight,
so the book-level weight says nothing about any individual rule.

Deterministic rather than another model call — affinity follows from `life_domains`,
which the extractor already recorded. So the weighting re-tunes in seconds without
re-reading the book, and the extraction prompt stays untouched.

Keywords rather than an enumeration: BPHS vol 1's 376 rules carry 105 distinct
`life_domains` values, 65 appearing at most twice, so substring matching is what
generalises to the next book. A concept spanning two dimensions gets both, since the
client's own matrix is many-to-many and weighted.
"""

from rishivan.models.knowledge.affinity import (
    RISHI_KEYS,
    WEIGHT_HIGH,
    WEIGHT_MEDIUM,
)

LIFE_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    # §3 ATMA -- who the person is: tendencies, life themes, chart promise.
    "atma": (
        "self", "identity", "personality", "character", "appearance", "physique",
        "physical body", "physical", "mind", "psycholog", "intellig", "intellect",
        "knowledge", "learning", "education", "skill", "art", "valour", "courage",
        "initiative", "enterprise", "speech", "communication", "general", "desires",
        "morality", "ethics", "misery", "comforts", "pleasure", "well-being",
        "happiness", "mental", "emotions", "habits", "behavior", "behaviour",
        "wisdom", "virtue", "fear", "freedom",
        # Values the newly extracted books introduced. `pleasures` above became
        # `pleasure` for the same reason: the match is a substring of the
        # domain value, so the singular catches both and the plural caught one.
        "distress", "sorrow", "temperament", "prowess", "wellbeing", "life",
    ),
    # §3 PREMA -- love, spouse, compatibility, separation, relationship timing.
    "prema": (
        "marriage", "spouse", "relationship", "wife", "husband", "compatib",
        "sexuality", "menses", "menstruation", "interpersonal",
    ),
    # §3 ARTHA -- money, assets, financial cycles, wealth Yogas.
    "artha": (
        "wealth", "money", "financ", "asset", "income", "gain", "possession",
        "sustenance", "expenditure", "prosper", "friendship", "servant",
        "friends", "agriculture", "animals", "cattle", "food", "trade",
        "livestock",
    ),
    # §3 KARMA -- profession, business, leadership, status, achievement.
    "karma": (
        "career", "profession", "business", "status", "reputation", "fame", "honour",
        "authority", "leadership", "work", "legal", "social", "power", "success",
        "achievement", "kingship", "government", "society", "rank",
        "employ", "kingdom", "royal", "service", "crime",
    ),
    # §3 VANSH -- parents, siblings, children, lineage, family dynamics.
    "vansh": (
        "family", "children", "child", "progeny", "sibling", "brother", "sister",
        "father", "mother", "parent", "relative", "domestic", "lineage", "maternal",
        "paternal", "co-born", "coborn",
    ),
    # §3 AAROGYA -- traditional health and vitality indicators.
    "aarogya": (
        "health", "disease", "illness", "longevity", "death", "vitality", "strength",
        "body", "protection", "enem", "afterlife", "physical body", "danger",
        "injur", "wound", "accident", "safety", "imprisonment", "captivity",
        "diet", "theft",
    ),
    # §3 YATRA -- travel, migration, property, residence, life transitions.
    "yatra": (
        "travel", "propert", "convey", "foreign", "residence", "migrat", "reloc",
        "journey", "vehicle", "home", "place of birth", "land", "dwelling",
    ),
    # §3 DHARMA -- dharma, karma, moksha, spiritual purpose, sacred texts.
    "dharma": (
        "religion", "spiritual", "dharma", "karma", "moksha", "occult", "fortune",
        "devotion", "pilgrim", "penance", "yajna", "charity", "remed",
        "auspicious", "inauspicious", "omen", "ritual",
        # `timing` and `timing of birth / lost horoscope` arrive as life domains
        # although timing is really a rule category. Mapped here rather than
        # left unrouted -- Prashna and omen work is DHARMA's -- because an
        # unrouted rule is one no Rishi can cite and therefore one nobody sees.
        # The data problem is upstream, in what the extractor calls a domain.
        "timing",
    ),
}
"""Client dimension -> its concepts, matched as substrings.

Two entries look wrong at a glance and are not:

* `"karma"` sits under DHARMA, not under the Rishi named KARMA. The client's KARMA is
  *career*; spiritual karma is DHARMA's. Routing the spiritual sense to the career
  Rishi is the easiest mistake in this mapping, and it fails silently.
* `"fortune"` is DHARMA, not ARTHA — the 9th house sense the client intends, not the
  monetary one.
"""

SECONDARY_WEIGHT_TERMS: dict[str, tuple[str, ...]] = {
    "vansh": ("education", "learning", "happiness"),
    "artha": ("propert", "convey"),
    "karma": ("skill", "art"),
    "atma": ("longevity", "death", "fortune"),
}
"""Concepts that genuinely belong to a second dimension, at reduced weight.

Education of children is Vansh's where education at large is Atma's; property is
Yatra's with a financial aspect that is Artha's; longevity shapes the life blueprint
without belonging to Atma. MEDIUM, so a secondary Rishi can reach the rule without
competing with the one that owns it.
"""


def affinity_for(life_domains: list[str] | None) -> dict[str, float]:
    """The per-rule Rishi vector, as client key -> weight in 0..1.

    `{}` when nothing matches: an unrouted rule should be visible as such, not quietly
    assigned to whichever Rishi came first. `unrouted_domains` reports the fallout.
    """
    text = " ".join(life_domains or []).lower()
    if not text.strip():
        return {}

    weights: dict[str, float] = {}
    for rishi, keywords in LIFE_DOMAIN_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            weights[rishi] = WEIGHT_HIGH
    for rishi, keywords in SECONDARY_WEIGHT_TERMS.items():
        if rishi in weights:
            continue
        if any(keyword in text for keyword in keywords):
            weights[rishi] = WEIGHT_MEDIUM

    assert set(weights) <= set(RISHI_KEYS), f"unknown rishi key in {sorted(weights)}"
    return weights


def unrouted_domains(all_life_domains: list[list[str]]) -> set[str]:
    """Domain values no keyword matches — a value nothing matches is a rule no Rishi
    can cite, so a test asserts this is empty."""
    unrouted = set()
    for domains in all_life_domains:
        for domain in domains or []:
            if not affinity_for([domain]):
                unrouted.add(domain.lower())
    return unrouted
