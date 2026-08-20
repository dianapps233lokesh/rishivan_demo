"""Derive each rule's Rishi affinity from what the rule is about.

Eight Rishis §15 requires this to be per-rule rather than inherited from the book: the
Book × Rishi matrix is "routing priorities, not claims that a source contains equal
coverage of every Rishi", and "the production matrix must be generated chapter/section/rule
by rule". BPHS is High for all eight, so the book-level weight says nothing useful about
any individual rule.

**Deterministic, not another model call.** A rule's affinity follows from its own content,
which the extractor already recorded in `life_domains`. Deriving it here means the
weighting can be re-tuned in seconds without re-reading the book, and it keeps the
extraction prompt untouched -- which matters, because that prompt demonstrably swings 50
points of precision on a single wording change.

**Keywords, not an enumeration.** The 376 rules loaded from BPHS vol 1 carry 105 distinct
`life_domains` values, 65 of which appear at most twice: "wealth and assets", "mind and
psychology", "foreign residence & travel". A lookup table would miss the tail on the next
book, so matching is by substring and the tail generalises.

The mapping below is a judgement call about which of the client's eight dimensions each
concept belongs to, made against the §3 definitions. Where a concept genuinely spans two
dimensions it gets both, because the client's own matrix is many-to-many and weighted.
"""

from app.models.knowledge.affinity import (
    RISHI_KEYS,
    WEIGHT_HIGH,
    WEIGHT_MEDIUM,
)

LIFE_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    # §3 ATMA -- "Who the person is, fundamental tendencies, strengths, weaknesses,
    # life themes, identity and overall chart promise."
    "atma": (
        "self", "identity", "personality", "character", "appearance", "physique",
        "physical body", "physical", "mind", "psycholog", "intellig", "intellect",
        "knowledge", "learning", "education", "skill", "art", "valour", "courage",
        "initiative", "enterprise", "speech", "communication", "general", "desires",
        "morality", "ethics", "misery", "comforts", "pleasures", "well-being",
        "happiness", "mental",
    ),
    # §3 PREMA -- "Love, spouse, marriage, compatibility, relationship quality,
    # separation, remarriage and relationship timing."
    "prema": ("marriage", "spouse", "relationship", "wife", "husband", "compatib"),
    # §3 ARTHA -- "Money, wealth, income, assets, financial cycles, business
    # prosperity, wealth Yogas and financial timing."
    "artha": (
        "wealth", "money", "financ", "asset", "income", "gain", "possession",
        "sustenance", "expenditure", "prosper", "friendship", "servant",
    ),
    # §3 KARMA -- "Profession, employment, business, leadership, status, reputation,
    # achievement and career timing."
    "karma": (
        "career", "profession", "business", "status", "reputation", "fame", "honour",
        "authority", "leadership", "work", "legal", "social",
    ),
    # §3 VANSH -- "Parents, siblings, family, children, childbirth, lineage, family
    # dynamics and children's themes."
    "vansh": (
        "family", "children", "child", "progeny", "sibling", "brother", "sister",
        "father", "mother", "parent", "relative", "domestic", "lineage", "maternal",
        "paternal", "co-born", "coborn",
    ),
    # §3 AAROGYA -- "Traditional astrological health/vitality indicators,
    # vulnerabilities and wellness-oriented interpretation."
    "aarogya": (
        "health", "disease", "illness", "longevity", "death", "vitality", "strength",
        "body", "protection", "enem", "afterlife", "physical body", "danger",
        "injur", "wound", "accident",
    ),
    # §3 YATRA -- "Travel, foreign settlement, migration, relocation, property,
    # residence and major life transitions."
    "yatra": (
        "travel", "propert", "convey", "foreign", "residence", "migrat", "reloc",
        "journey", "vehicle",
    ),
    # §3 DHARMA -- "Bhagavad Gita, shlokas, Dharma, Karma, Moksha, spiritual purpose,
    # philosophical context and sacred-text interpretation."
    "dharma": (
        "religion", "spiritual", "dharma", "karma", "moksha", "occult", "fortune",
        "devotion", "pilgrim", "penance", "yajna", "charity", "remed",
    ),
}
"""Client dimension -> the concepts that belong to it, matched as substrings.

Two entries deserve their reasoning stated, because both look wrong at a glance:

* `"karma"` appears under DHARMA and not under the Rishi named KARMA. The client's KARMA
  is **career** (§3: "Profession, employment, business, leadership"); spiritual karma is
  DHARMA's ("Dharma, Karma, Moksha, spiritual purpose"). A rule tagged "karma" in the
  spiritual sense routed to the career Rishi would be a silent mis-routing, and this is
  the single easiest mistake to make in this whole mapping.
* `"fortune"` is DHARMA rather than ARTHA. In Jyotisha the 9th house is fortune *and*
  dharma; the client puts "higher learning, father, dharma" there, so the 9th-house sense
  is the intended one rather than the monetary sense.
"""

SECONDARY_WEIGHT_TERMS: dict[str, tuple[str, ...]] = {
    "vansh": ("education", "learning", "happiness"),
    "artha": ("propert", "convey"),
    "karma": ("skill", "art"),
    "atma": ("longevity", "death", "fortune"),
}
"""Concepts that genuinely belong to a second dimension at reduced weight.

"Education of children" is a Vansh question in §3 while education in general is Atma's;
property is Yatra's dimension while its financial aspect is Artha's; longevity shapes the
whole life blueprint, so Atma has a stake in it without owning it. Plain "happiness" is a
general life theme -- Atma's -- but the 4th house sense is domestic, so Vansh keeps a
secondary claim. Recorded at MEDIUM so a secondary Rishi can reach the rule without
competing with the Rishi that owns it.
"""


def affinity_for(life_domains: list[str] | None) -> dict[str, float]:
    """The per-rule Rishi vector, as client key -> weight in 0..1.

    Returns `{}` when nothing matches, which is honest rather than convenient: a rule with
    no derivable affinity should be visible as unrouted, not quietly assigned to whichever
    Rishi happened to be first. `unrouted_domains` reports what fell through so the
    keyword table can be extended against real data.
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
    """Domain values no keyword matches -- the list to extend the table from.

    Kept as a function rather than a script because it is the coverage assertion a test
    makes: a value nothing matches is a rule no Rishi can cite.
    """
    unrouted = set()
    for domains in all_life_domains:
        for domain in domains or []:
            if not affinity_for([domain]):
                unrouted.add(domain.lower())
    return unrouted
