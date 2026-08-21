"""The eight Rishi Constitutions — Eight Rishis §16, populated from §4-11.

§16 asks for one comparable object per Rishi so "the eight systems [are] maintainable
and comparable". §4-11 supply the content, and one field of it decides retrieval:

    **Astrological coverage** — the houses, planets, factors and vargas a Rishi's
    questions actually examine.

That set is what makes a rule this Rishi's evidence. Without it, relevance falls back to
the extractor's free-text `life_domains` tag, which does not discriminate: BPHS 22.6
("the native's father will be a king") is tagged `father` and so reached a question about
marriage, though its subject is the 9th house and no Rishi of relationships consults it.

Keyed by the CLIENT's eight domain keys (§21), not by the repo's persona names. A
question routes to a domain; a persona speaks for it. See `domains.RISHI_LIFE_DOMAINS`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Constitution:
    """One Rishi's constitution. §16's schema, minus the fields nothing reads yet."""

    domain: str
    dimension: str
    mission: str
    primary_houses: frozenset[int]
    """The house(s) §4-11 names as this Rishi's own, listed first in its coverage."""
    supporting_houses: frozenset[int]
    """Houses the section also consults. §5 reads "7th house/lord, Venus, Jupiter where
    relevant, 2nd/8th/11th" -- the 7th is the subject and the rest are context, and
    flattening them ranked a 2nd-house rule about wealth level with one about a spouse."""
    planets: frozenset[str]
    vargas: frozenset[str]
    protocol: tuple[str, ...]
    source_families: tuple[str, ...]
    forbidden_claims: tuple[str, ...] = ()
    unavailable_sources: tuple[str, ...] = ()
    """Sources §4-11 requires that this corpus does not hold. Recorded rather than
    omitted: a Rishi answering without its stated corpus is answering from something
    else, and that should be visible."""
    blocked_concepts: tuple[str, ...] = ()
    """Coverage the document names that the fact vocabulary cannot express."""
    notes: str = ""

    @property
    def houses(self) -> frozenset[int]:
        """Every house in this Rishi's coverage. The admission gate uses this; ranking
        inside it distinguishes primary from supporting."""
        return self.primary_houses | self.supporting_houses


CONSTITUTIONS: dict[str, Constitution] = {
    # ── ER §4 ────────────────────────────────────────────────────────────────
    "atma": Constitution(
        domain="atma",
        dimension="Self / Identity / Life Blueprint",
        mission="Understand the person before understanding their events.",
        # §4: "Lagna, Lagna lord, Sun, Moon, Nakshatra, planetary dignity and
        # strength, aspects, conjunctions, major Yogas affecting identity". Only the
        # Lagna is named as a house, and that faithfulness is deliberate: widening it
        # to "identity is everything" would defeat the point of having coverage.
        primary_houses=frozenset({1}),
        supporting_houses=frozenset(),
        planets=frozenset({"sun", "moon"}),
        vargas=frozenset(),
        protocol=(
            "chart framework",
            "Lagna and Lagna lord",
            "Sun and Moon",
            "strength",
            "Nakshatra",
            "major combinations",
            "relevant Vargas",
            "Jaimini",
            "synthesis",
            "uncertainty",
        ),
        source_families=(
            "BPHS", "Brihat Jataka", "Phaladeepika", "Saravali", "Jataka Parijata",
            "Jaimini Sutras", "Nakshatra literature", "Samudrika",
        ),
        unavailable_sources=("Jaimini Sutras", "Nakshatra literature", "Samudrika"),
        blocked_concepts=("Atmakaraka", "Karakamsha"),
    ),
    # ── ER §5 ────────────────────────────────────────────────────────────────
    "prema": Constitution(
        domain="prema",
        dimension="Love / Marriage / Relationships",
        mission="Own the complete relationship lifecycle, not just marriage prediction.",
        # §5: "7th house/lord, Venus, Jupiter where relevant, 2nd/8th/11th, D9" --
        # the 7th first and by itself, the rest as context.
        primary_houses=frozenset({7}),
        supporting_houses=frozenset({2, 8, 11}),
        planets=frozenset({"venus", "jupiter"}),
        vargas=frozenset({"D9"}),
        protocol=(
            "promise",
            "spouse indicators",
            "relationship quality",
            "D9 confirmation",
            "Jaimini indicators",
            "Yoga, affliction and modification",
            "Dasha",
            "transit",
            "cross-school timing",
            "confidence",
        ),
        source_families=(
            "BPHS", "Phaladeepika", "Saravali", "Jataka Parijata", "Jaimini Sutras",
            "KP corpus", "Nadi",
        ),
        unavailable_sources=("Jaimini Sutras", "KP corpus"),
        blocked_concepts=("Darakaraka", "Upapada", "Arudha", "KP sub-lords"),
    ),
    # ── ER §6 ────────────────────────────────────────────────────────────────
    "artha": Constitution(
        domain="artha",
        dimension="Wealth / Resources / Prosperity",
        mission="Determine the person's relationship with resources and prosperity.",
        # §6: "2nd, 5th, 9th, 10th, 11th; their lords; Lagna/Lagna lord; D2; D10".
        # §17's own decision tree splits them: STEP 2 BASELINE PROMISE is Lagna, 2nd
        # and 11th; STEP 3 SUPPORTING WEALTH HOUSES are the 5th, 9th and 10th.
        primary_houses=frozenset({1, 2, 11}),
        supporting_houses=frozenset({5, 9, 10}),
        planets=frozenset(),
        vargas=frozenset({"D2", "D10"}),
        protocol=(
            "baseline wealth promise",
            "wealth combinations",
            "strength",
            "modification and cancellation",
            "Vargas",
            "Dasha activation",
            "transits",
            "cross-school evidence",
            "event windows",
            "confidence",
        ),
        source_families=(
            "BPHS", "Brihat Jataka", "Phaladeepika", "Saravali", "Jataka Parijata",
            "Sarvartha Chintamani", "Bhavartha Ratnakara", "Jaimini Sutras", "Nadi",
            "KP corpus", "Shadbala/Ashtakavarga corpus",
        ),
        unavailable_sources=(
            "Jaimini Sutras", "KP corpus", "Shadbala/Ashtakavarga corpus",
        ),
        blocked_concepts=(
            "Dhana Yogas", "Raja Yogas", "Mahapurusha Yogas", "Neecha Bhanga",
            "Shadbala", "Avastha", "benefic/malefic influence",
        ),
        notes="§6: 'must be far deeper than a 2nd + 11th house checker'. Most of what "
        "makes it deeper -- yogas, Shadbala, Avastha, benefic/malefic -- is blocked.",
    ),
    # ── ER §7 ────────────────────────────────────────────────────────────────
    "karma": Constitution(
        domain="karma",
        dimension="Career / Business / Achievement",
        mission="Own the entire career, profession, achievement and business dimension.",
        # §7: "10th house/lord" first, then "Lagna/lord; 6th; 2nd; 11th; D10".
        primary_houses=frozenset({10}),
        supporting_houses=frozenset({1, 2, 6, 11}),
        planets=frozenset(),
        vargas=frozenset({"D10"}),
        protocol=(
            "career promise",
            "job or business orientation",
            "profession categories",
            "D10",
            "Yogas",
            "strength",
            "Dasha",
            "transit",
            "cross-school confirmation",
            "timing",
        ),
        source_families=(
            "BPHS", "Brihat Jataka", "Phaladeepika", "Saravali", "Jataka Parijata",
            "Jaimini Sutras", "KP corpus", "Nadi", "D10/profession literature",
        ),
        unavailable_sources=(
            "Jaimini Sutras", "KP corpus", "D10/profession literature",
        ),
        blocked_concepts=("professional Yogas", "Raja Yogas", "Mahapurusha Yogas"),
    ),
    # ── ER §8 ────────────────────────────────────────────────────────────────
    "vansh": Constitution(
        domain="vansh",
        dimension="Family / Children / Lineage",
        mission="Family, children and lineage across the whole life cycle.",
        # §8: "2nd, 3rd, 4th, 5th, 9th; relevant lords; Karakas; D7; D12". The section
        # owns parents (4th, 9th) and children (5th); the 2nd and 3rd carry family
        # wealth and siblings.
        primary_houses=frozenset({4, 5, 9}),
        supporting_houses=frozenset({2, 3}),
        planets=frozenset(),
        vargas=frozenset({"D7", "D12"}),
        protocol=(
            "identify relationship",
            "natal promise",
            "relevant house and lord",
            "Karaka",
            "Varga",
            "combinations",
            "strength and modifiers",
            "Dasha",
            "transit",
            "cross-check",
        ),
        source_families=(
            "BPHS", "Phaladeepika", "Saravali", "Jataka Parijata", "Jaimini Sutras",
            "D7/D12 literature", "Nadi",
        ),
        unavailable_sources=("Jaimini Sutras", "D7/D12 literature"),
        blocked_concepts=("Chara Karakas",),
    ),
    # ── ER §9 ────────────────────────────────────────────────────────────────
    "aarogya": Constitution(
        domain="aarogya",
        dimension="Health / Vitality / Resilience",
        mission="Traditional astrology of vitality, constitution and vulnerability. "
        "A wellness interpretation engine, not a medical diagnostic system.",
        # §9: "Lagna/1st; 6th; 8th; 12th; Sun; Moon; relevant planetary strength".
        # The 1st and 6th are constitution and affliction; the 8th and 12th, context.
        primary_houses=frozenset({1, 6}),
        supporting_houses=frozenset({8, 12}),
        planets=frozenset({"sun", "moon"}),
        vargas=frozenset(),
        protocol=(
            "constitution and vitality",
            "1st, 6th, 8th, 12th",
            "Sun and Moon",
            "planetary strength",
            "traditional combinations",
            "Dasha",
            "transit",
            "uncertainty",
        ),
        source_families=(
            "BPHS", "classical Jyotisha health chapters", "Brihat Jataka",
            "Phaladeepika", "Saravali", "traditional medical-astrology literature",
        ),
        forbidden_claims=(
            "never diagnose a disease",
            "never predict death as a certainty",
            "never prescribe treatment",
            "never tell the user to avoid medical care",
        ),
        unavailable_sources=("traditional medical-astrology literature",),
        notes="§9's strict rule is absolute. Enforced at retrieval by "
        "`knowledge.match.safety`, which gates on the question's own words.",
    ),
    # ── ER §10 ───────────────────────────────────────────────────────────────
    "yatra": Constitution(
        domain="yatra",
        dimension="Movement / Property / Change",
        mission="Movement, property, relocation and major life transitions.",
        # §10: "3rd, 4th, 8th, 9th, 12th; Rahu/Ketu; relevant lords; D4". The section
        # owns property and residence (4th) and foreign settlement (12th).
        primary_houses=frozenset({4, 12}),
        supporting_houses=frozenset({3, 8, 9}),
        planets=frozenset({"rahu", "ketu"}),
        vargas=frozenset({"D4"}),
        protocol=(
            "identify movement or change type",
            "natal promise",
            "relevant houses and lords",
            "Varga",
            "Dasha",
            "transit",
            "Prashna if appropriate",
            "timing",
            "corroboration",
        ),
        source_families=("BPHS", "Jaimini Sutras", "Nadi", "Prashna corpus"),
        unavailable_sources=("Jaimini Sutras",),
    ),
    # ── ER §11 ───────────────────────────────────────────────────────────────
    "dharma": Constitution(
        domain="dharma",
        dimension="Dharma / Karma / Spirituality / Sacred Knowledge",
        mission="Sacred and philosophical knowledge specialist; interpreter of Dharma, "
        "Karma and spiritual questions.",
        # §11 names no houses -- its coverage is "classical Jyotisha spiritual
        # indicators". The 9th (dharma) and 12th (moksha) are the classical pair, and
        # this is the one coverage set inferred rather than transcribed.
        primary_houses=frozenset({9, 12}),
        supporting_houses=frozenset(),
        planets=frozenset(),
        vargas=frozenset(),
        protocol=(
            "identify the philosophical question",
            "select tradition",
            "retrieve source or shloka",
            "contextual interpretation",
            "separately analyse astrology if requested",
            "synthesise without claiming certainty beyond the source",
        ),
        source_families=(
            "Bhagavad Gita", "principal Upanishads", "Yoga Sutras", "Samkhya",
            "Vedanta works", "Puranic karma/rebirth literature",
            "classical Jyotisha spiritual indicators", "Jaimini Sutras",
        ),
        forbidden_claims=(
            "never present an astrological indication as scriptural teaching",
            "never invent a spiritual explanation to make a story sound profound",
        ),
        unavailable_sources=(
            "Bhagavad Gita", "principal Upanishads", "Yoga Sutras", "Samkhya",
            "Vedanta works", "Puranic karma/rebirth literature", "Jaimini Sutras",
        ),
        blocked_concepts=("Atmakaraka", "Karakamsha"),
        notes="§11's entire core corpus is absent from the ingested books, so Dharma "
        "can currently answer only from Jyotisha's 9th/12th indicators -- which §11 "
        "explicitly separates from scriptural teaching.",
    ),
}
"""The eight constitutions, keyed by the client's domain keys.

`houses` is the field that does the work. Every set is transcribed from its §4-11
section except Dharma's, which §11 leaves as "classical Jyotisha spiritual indicators"
and is marked inferred above.
"""
