"""The Book × Rishi matrix — Eight Rishis §15, transcribed.

§15 is the document's direct answer to the "books corpus + domain mapping" problem:

    "A book can map to many Rishis. The mapping is weighted by concept coverage, not by
    ownership."

Values below are the document's own High / Medium / Low / Very High, not an
approximation of them. §15's caveat travels with them: "These are routing priorities,
not claims that a source contains equal coverage of every Rishi. The production matrix
must be generated chapter/section/rule by rule." Per-rule affinity does that job
(`knowledge.affinity.derive`); this table only ranks *pages* within a domain, where no
finer signal exists.
"""

from __future__ import annotations

SOURCE_VERY_HIGH = 1.00
SOURCE_HIGH = 0.90
SOURCE_MEDIUM = 0.60
SOURCE_LOW = 0.30
"""§15's four levels. "Very High" appears exactly once in the document — the Gita and
Upanishads for Dharma — so the scale needs a rung above High."""

SOURCE_NEUTRAL = 0.55
"""An unmapped book or domain. Below median so it neither dominates a rated source nor
disappears from a reading, which a zero would do silently."""

_VH, _H, _M, _L = SOURCE_VERY_HIGH, SOURCE_HIGH, SOURCE_MEDIUM, SOURCE_LOW

# Column order matches §21: atma, prema, artha, karma, vansh, aarogya, yatra, dharma.
_COLUMNS = ("atma", "prema", "artha", "karma", "vansh", "aarogya", "yatra", "dharma")

_ROWS: dict[str, tuple[float, ...]] = {
    #                             atma prema artha karma vansh aaro  yatra dharma
    "BPHS":                      (_H,  _H,   _H,   _H,   _H,   _H,   _H,   _H),
    "Brihat Jataka":             (_H,  _H,   _H,   _H,   _H,   _H,   _H,   _M),
    "Phaladeepika":              (_H,  _H,   _H,   _H,   _H,   _H,   _M,   _M),
    "Saravali":                  (_H,  _H,   _H,   _H,   _H,   _H,   _M,   _M),
    "Jataka Parijata":           (_H,  _H,   _H,   _H,   _H,   _H,   _M,   _M),
    "Jaimini Sutras":            (_H,  _H,   _H,   _H,   _H,   _M,   _H,   _H),
    "Deva Keralam / Nadi":       (_M,  _H,   _H,   _H,   _H,   _M,   _H,   _M),
    "KP corpus":                 (_M,  _H,   _H,   _H,   _M,   _M,   _H,   _L),
    "Prashna corpus":            (_M,  _H,   _H,   _H,   _H,   _M,   _H,   _M),
    "Tajika corpus":             (_M,  _H,   _H,   _H,   _M,   _M,   _H,   _L),
    "Muhurta corpus":            (_L,  _H,   _H,   _H,   _M,   _L,   _H,   _M),
    "Samudrika / palmistry":     (_H,  _M,   _M,   _M,   _M,   _L,   _L,   _L),
    "Numerology":                (_H,  _M,   _H,   _H,   _M,   _L,   _L,   _M),
    "Vastu":                     (_M,  _L,   _H,   _M,   _M,   _L,   _H,   _M),
    "Bhagavad Gita / Upanishads": (_M, _L,   _L,   _L,   _M,   _L,   _L,   _VH),
}

SOURCE_RISHI_WEIGHTS: dict[str, dict[str, float]] = {
    family: dict(zip(_COLUMNS, weights)) for family, weights in _ROWS.items()
}
"""Source family -> client domain -> §15 routing weight."""


SLUG_SOURCE_FAMILY: dict[str, str] = {
    # Core Hora / Parashari
    "bphs-gcsharma-vol1": "BPHS",
    "bphs-gcsharma-vol2": "BPHS",
    "brihatjataka-row-1919": "Brihat Jataka",
    "phaladeepika-sastri-1950": "Phaladeepika",
    "saravali-santhanam-en": "Saravali",
    "jatakaparijata-sastri-vol1": "Jataka Parijata",
    "jatakaparijata-sastri-vol2": "Jataka Parijata",
    # §15 has no row of their own; they are classical Hora in the same tradition, and
    # Phaladeepika is the closest rated row by concept coverage.
    "sarvartha-chintamani": "Phaladeepika",
    "bhavartha-ratnakara-by-b-v-raman-text": "Phaladeepika",
    "laghu-parashari": "Phaladeepika",
    "hindupredictiveastrology-raman": "Phaladeepika",
    # Nadi
    "devakeralam-chandrakalanadi-vol1": "Deva Keralam / Nadi",
    "devakeralam-chandrakalanadi-vol2": "Deva Keralam / Nadi",
    # Prashna
    "prasnamarga-raman-part1": "Prashna corpus",
    "prasnamarga-raman-part2": "Prashna corpus",
    "prashna-tantra": "Prashna corpus",
    # Muhurta
    "muhurtachintamani": "Muhurta corpus",
    "dharma-sindhu": "Muhurta corpus",
    "vivaha-patalam": "Muhurta corpus",
    # Numerology
    "cheiros-book-of-numbers": "Numerology",
    "the-complete-book-of-numerology": "Numerology",
    "numerology-key-to-your-inner-self": "Numerology",
    "numerology-and-the-divine-triangle": "Numerology",
}
"""Ingested book slug -> §15 source family.

Four slugs map to Phaladeepika's row rather than one of their own, which is a judgement
recorded rather than hidden: §15 rates fifteen families and the corpus holds books it
does not name. Sarvartha Chintamani, Bhavartha Ratnakara, Laghu Parashari and Hindu
Predictive Astrology are all classical Hora with the same concept coverage as the rated
Parashari rows, so they inherit the nearest one.
"""


def source_family_for_slug(slug: str | None) -> str | None:
    """The §15 family a book belongs to, or None if it is unmapped."""
    if not slug:
        return None
    return SLUG_SOURCE_FAMILY.get(slug.lower().strip())


def source_weight(slug: str | None, domain: str | None) -> float:
    """§15's routing weight for this book against this client domain.

    `SOURCE_NEUTRAL` when either is unknown: an unmapped book should rank in the middle,
    never vanish. Multiply this by `rag.authority.authority_for_slug` to get "how
    authoritative is this book, and how relevant is it to what was asked".
    """
    family = source_family_for_slug(slug)
    if family is None:
        return SOURCE_NEUTRAL
    return SOURCE_RISHI_WEIGHTS[family].get(
        (domain or "").lower().strip(), SOURCE_NEUTRAL
    )


AUTHORITY_TIER: dict[str, str] = {
    # S0 — primary classical text
    "bphs-gcsharma-vol1": "S0",
    "bphs-gcsharma-vol2": "S0",
    "brihatjataka-row-1919": "S0",
    "phaladeepika-sastri-1950": "S0",
    "saravali-santhanam-en": "S0",
    "jatakaparijata-sastri-vol1": "S0",
    "jatakaparijata-sastri-vol2": "S0",
    "sarvartha-chintamani": "S0",
    "muhurtachintamani": "S0",
    "prasnamarga-raman-part1": "S0",
    "prasnamarga-raman-part2": "S0",
    "prashna-tantra": "S0",
    "devakeralam-chandrakalanadi-vol1": "S0",
    "devakeralam-chandrakalanadi-vol2": "S0",
    "vivaha-patalam": "S0",
    "dharma-sindhu": "S0",
    # S1 — traditional commentary or abridgement of a classical text
    "laghu-parashari": "S1",
    "bhavartha-ratnakara-by-b-v-raman-text": "S1",
    # S3 — established practitioner writing in the modern era
    "hindupredictiveastrology-raman": "S3",
    # S4 — modern interpretation outside the Jyotisha canon
    "cheiros-book-of-numbers": "S4",
    "the-complete-book-of-numerology": "S4",
    "numerology-key-to-your-inner-self": "S4",
    "numerology-and-the-divine-triangle": "S4",
}
"""Blueprint §12's source tiers, per ingested book.

§12 is explicit that these are "engineering categories, not claims about spiritual
authority": they exist so BP §8's rule 4 ("Primary classical source > established
commentary > established practitioner > experimental material") is computable.

The tier is about the WORK, not the translation. Saravali in Santhanam's English is
still a primary classical text; Hindu Predictive Astrology is B. V. Raman's own 20th
century synthesis, so it is S3 however respected.
"""

UNRATED_TIER = "S5"
"""An unrated book gets the lowest tier, never a classical one. Defaulting upward would
let a new upload inherit authority nobody granted it."""


def authority_tier(slug: str | None) -> str:
    """Blueprint §12 tier for a book slug; `UNRATED_TIER` if unknown."""
    if not slug:
        return UNRATED_TIER
    return AUTHORITY_TIER.get(slug.lower().strip(), UNRATED_TIER)


BOOK_SCHOOL: dict[str, str] = {
    # Blueprint §5's own School column, per book family.
    "bphs-gcsharma-vol1": "parashari",
    "bphs-gcsharma-vol2": "parashari",
    "phaladeepika-sastri-1950": "parashari",
    "saravali-santhanam-en": "parashari",
    "laghu-parashari": "parashari",
    "hindupredictiveastrology-raman": "parashari",
    "brihatjataka-row-1919": "classical_hora",
    "jatakaparijata-sastri-vol1": "classical_hora",
    "jatakaparijata-sastri-vol2": "classical_hora",
    "sarvartha-chintamani": "classical_hora",
    "bhavartha-ratnakara-by-b-v-raman-text": "classical_hora",
    "devakeralam-chandrakalanadi-vol1": "nadi",
    "devakeralam-chandrakalanadi-vol2": "nadi",
    "prasnamarga-raman-part1": "prashna",
    "prasnamarga-raman-part2": "prashna",
    "prashna-tantra": "prashna",
    "muhurtachintamani": "muhurta",
    "dharma-sindhu": "muhurta",
    "vivaha-patalam": "muhurta",
    "cheiros-book-of-numbers": "numerology",
    "the-complete-book-of-numerology": "numerology",
    "numerology-key-to-your-inner-self": "numerology",
    "numerology-and-the-divine-triangle": "numerology",
}
"""Blueprint §4 level 2, per ingested book, transcribed from §5's School column.

Recorded so §8's rule 5 is enforceable: "Never mix schools silently. If a Jaimini rule
is used alongside Parashari, label both." It is a LABEL, not a filter -- every §4-11
protocol ends in "cross-school confirmation", so excluding other schools would remove
the corroboration the documents ask for. Retrieval groups by school; it never excludes.
"""

UNKNOWN_SCHOOL = "unknown"
"""Never defaulted to `parashari`. A mislabelled school is precisely the silent
doctrine-mixing §8 rule 5 forbids, and it would be invisible."""

BOOK_UNIVERSE: dict[str, str] = {
    slug: ("numerology" if school == "numerology" else "jyotisha")
    for slug, school in BOOK_SCHOOL.items()
}
"""Blueprint §4 level 1. Only two universes are represented in this corpus.

The separation is load-bearing rather than tidy: ER §13 makes numerology a modality a
Rishi may *call*, and "must never silently override natal astrology". Retrieving a
numerology page as though it were natal evidence is that override.
"""


def school_for(slug: str | None) -> str:
    """Blueprint §4 level 2 for a book slug; `UNKNOWN_SCHOOL` if unclassified."""
    if not slug:
        return UNKNOWN_SCHOOL
    return BOOK_SCHOOL.get(slug.lower().strip(), UNKNOWN_SCHOOL)


def universe_for(slug: str | None) -> str:
    """Blueprint §4 level 1 for a book slug; `UNKNOWN_SCHOOL` if unclassified."""
    if not slug:
        return UNKNOWN_SCHOOL
    return BOOK_UNIVERSE.get(slug.lower().strip(), UNKNOWN_SCHOOL)


def slugs_for_universe(universe: str | None) -> frozenset[str]:
    """Every book slug in a Blueprint §4 level-1 universe.

    Retrieval filters by slug rather than by a stored `book_domain` tag: `book_slug` is
    written consistently and already indexed, whereas `book_domain` holds two
    incompatible shapes in the live collection (`'foundation'` alongside the stringified
    list `"['numerology']"`), so a quarter of the corpus was unmatchable through it.

    An unknown universe yields the empty set, never everything -- a typo must not
    silently widen retrieval to the whole corpus.
    """
    wanted = (universe or "").lower().strip()
    return frozenset(
        slug for slug, value in BOOK_UNIVERSE.items() if value == wanted
    )


def slugs_for_school(school: str | None) -> frozenset[str]:
    """Every book slug of one Blueprint §4 level-2 school.

    Provided for grouping and reporting. Retrieval does NOT filter by school: §8 rule 5
    asks for labelling, and every §4-11 protocol ends in "cross-school confirmation", so
    excluding a school would remove the corroboration the documents ask for.
    """
    wanted = (school or "").lower().strip()
    return frozenset(
        slug for slug, value in BOOK_SCHOOL.items() if value == wanted
    )
