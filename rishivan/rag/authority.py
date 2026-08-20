"""Source authority weights — a demo-scaled echo of the main backend's P3
retrieval ranking (``score = specificity x source_authority x confidence``).

Not every classical text carries equal weight: a foundational treatise like
Brihat Parashara Hora Shastra is the primary source most later authors build
on, so a page from it should outrank an equally-matched page from a minor
or narrowly-scoped text when both are candidates for the same reading.

This is a static, hand-set table (mirroring the main backend's own
``SOURCE_AUTHORITY``, which is likewise hardcoded pending domain-expert
review) rather than anything learned or computed — the demo has no
mechanism to derive authority from the corpus itself.
"""

from __future__ import annotations

# Highest = the foundational, most-cited classics; lowest = narrow or
# supplementary texts. Kept in the same 0-1 range as the main backend's
# table so the two stay easy to compare if they are ever reconciled.
SOURCE_AUTHORITY: dict[str, float] = {
    "bphs-gcsharma-vol1": 1.00,
    "bphs-gcsharma-vol2": 1.00,
    "phaladeepika-sastri-1950": 0.90,
    "saravali-santhanam-en": 0.90,
    "jatakaparijata-sastri-vol1": 0.85,
    "jatakaparijata-sastri-vol2": 0.85,
    "brihatjataka-row-1919": 0.85,
    "laghu-parashari": 0.80,
    "sarvartha-chintamani": 0.80,
    "hindupredictiveastrology-raman": 0.75,
    "bhavartha-ratnakara-by-b-v-raman-text": 0.70,
    "muhurtachintamani": 0.75,
    "dharma-sindhu": 0.65,
    "vivaha-patalam": 0.65,
    "prasnamarga-raman-part1": 0.75,
    "prasnamarga-raman-part2": 0.75,
    "prashna-tantra": 0.70,
    "devakeralam-chandrakalanadi-vol1": 0.65,
    "cheiros-book-of-numbers": 0.60,
    "the-complete-book-of-numerology": 0.60,
    "numerology-key-to-your-inner-self": 0.60,
}

DEFAULT_AUTHORITY = 0.55
"""Fallback weight for any book slug not yet in the table above — a
below-median value so an untagged book neither dominates a well-known
classic nor is treated as worthless."""


def authority_for_slug(slug: str | None) -> float:
    """Authority weight in [0, 1] for a book slug; ``DEFAULT_AUTHORITY`` if unknown."""
    if not slug:
        return DEFAULT_AUTHORITY
    return SOURCE_AUTHORITY.get(slug.lower().strip(), DEFAULT_AUTHORITY)
