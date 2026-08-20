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
