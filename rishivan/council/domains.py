"""Book domain taxonomy and Rishi → book-domain mapping.

The 8 Rishis are personalities on top of one shared knowledge base.
Domain filters control which books each Rishi draws from at query time.
"""
from __future__ import annotations

from enum import Enum


class BookDomain(str, Enum):
    FOUNDATION   = "foundation"    # BPHS, Phaladeepika, Saravali, Jataka Parijata
    PREDICTION   = "prediction"    # Brihat Jataka, Laghu Parashari, Sarvartha Chintamani
    TIMING       = "timing"        # Laghu Parashari, BPHS timing chapters
    MUHURTA      = "muhurta"       # Muhurta Chintamani
    PRASHNA      = "prashna"       # Prashna Marga, Prashna Tantra
    REMEDIAL     = "remedial"      # BPHS remedies chapters
    NADI         = "nadi"          # Deva Keralam / Chandra Kala Nadi
    WEALTH       = "wealth"        # Bhavartha Ratnakara, Sarvartha Chintamani
    COMPATIBILITY = "compatibility" # Muhurta vivaha sections


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
    "dhruvan": [BookDomain.WEALTH, BookDomain.PREDICTION, BookDomain.FOUNDATION],
    "ritam":   [BookDomain.TIMING, BookDomain.MUHURTA, BookDomain.FOUNDATION],
    "tejan":   [BookDomain.REMEDIAL, BookDomain.FOUNDATION],
    "medhan":  [BookDomain.FOUNDATION, BookDomain.PREDICTION, BookDomain.PRASHNA, BookDomain.COMPATIBILITY],
    "tattvan": [BookDomain.PREDICTION, BookDomain.NADI, BookDomain.FOUNDATION],
    "pragnav": [BookDomain.FOUNDATION, BookDomain.NADI],
}


# ── Query-domain taxonomy (for chart routing) ────────────────────────────────

class QueryDomain(str, Enum):
    NATAL   = "natal"
    MUHURTA = "muhurta"
    PRASHNA = "prashna"
    GENERAL = "general"
