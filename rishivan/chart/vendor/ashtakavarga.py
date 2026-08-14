"""Ashtakavarga: bindus contributed by seven planets plus the lagna, per sign.

VENDORED from the main repo's app/astro/bala/ashtakavarga.py — see
rishivan/chart/vendor/__init__.py for why. Keep this in sync manually.
"""

from __future__ import annotations

from dataclasses import dataclass

SUBJECTS = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
CONTRIBUTORS = (*SUBJECTS, "lagna")

SAV_TOTAL = 337
BAV_ROW_TOTALS = {
    "sun": 48,
    "moon": 49,
    "mars": 39,
    "mercury": 54,
    "jupiter": 56,
    "venus": 52,
    "saturn": 39,
}
"""Chart-independent classical totals. Never adjust these to match the tables below —
adjust the tables to match these."""

BENEFIC_PLACES: dict[str, dict[str, tuple[int, ...]]] = {
    "sun": {
        "sun": (1, 2, 4, 7, 8, 9, 10, 11),
        "moon": (3, 6, 10, 11),
        "mars": (1, 2, 4, 7, 8, 9, 10, 11),
        "mercury": (3, 5, 6, 9, 10, 11, 12),
        "jupiter": (5, 6, 9, 11),
        "venus": (6, 7, 12),
        "saturn": (1, 2, 4, 7, 8, 9, 10, 11),
        "lagna": (3, 4, 6, 10, 11, 12),
    },
    "moon": {
        "sun": (3, 6, 7, 8, 10, 11),
        "moon": (1, 3, 6, 7, 10, 11),
        "mars": (2, 3, 5, 6, 9, 10, 11),
        "mercury": (1, 3, 4, 5, 7, 8, 10, 11),
        "jupiter": (1, 4, 7, 8, 10, 11, 12),
        "venus": (3, 4, 5, 7, 9, 10, 11),
        "saturn": (3, 5, 6, 11),
        "lagna": (3, 6, 10, 11),
    },
    "mars": {
        "sun": (3, 5, 6, 10, 11),
        "moon": (3, 6, 11),
        "mars": (1, 2, 4, 7, 8, 10, 11),
        "mercury": (3, 5, 6, 11),
        "jupiter": (6, 10, 11, 12),
        "venus": (6, 8, 11, 12),
        "saturn": (1, 4, 7, 8, 9, 10, 11),
        "lagna": (1, 3, 6, 10, 11),
    },
    "mercury": {
        "sun": (5, 6, 9, 11, 12),
        "moon": (2, 4, 6, 8, 10, 11),
        "mars": (1, 2, 4, 7, 8, 9, 10, 11),
        "mercury": (1, 3, 5, 6, 9, 10, 11, 12),
        "jupiter": (6, 8, 11, 12),
        "venus": (1, 2, 3, 4, 5, 8, 9, 11),
        "saturn": (1, 2, 4, 7, 8, 9, 10, 11),
        "lagna": (1, 2, 4, 6, 8, 10, 11),
    },
    "jupiter": {
        "sun": (1, 2, 3, 4, 7, 8, 9, 10, 11),
        "moon": (2, 5, 7, 9, 11),
        "mars": (1, 2, 4, 7, 8, 10, 11),
        "mercury": (1, 2, 4, 5, 6, 9, 10, 11),
        "jupiter": (1, 2, 3, 4, 7, 8, 10, 11),
        "venus": (2, 5, 6, 9, 10, 11),
        "saturn": (3, 5, 6, 12),
        "lagna": (1, 2, 4, 5, 6, 7, 9, 10, 11),
    },
    "venus": {
        "sun": (8, 11, 12),
        "moon": (1, 2, 3, 4, 5, 8, 9, 11, 12),
        "mars": (3, 5, 6, 9, 11, 12),
        "mercury": (3, 5, 6, 9, 11),
        "jupiter": (5, 8, 9, 10, 11),
        "venus": (1, 2, 3, 4, 5, 8, 9, 10, 11),
        "saturn": (3, 4, 5, 8, 9, 10, 11),
        "lagna": (1, 2, 3, 4, 5, 8, 9, 11),
    },
    "saturn": {
        "sun": (1, 2, 4, 7, 8, 10, 11),
        "moon": (3, 6, 11),
        "mars": (3, 5, 6, 10, 11, 12),
        "mercury": (6, 8, 9, 10, 11, 12),
        "jupiter": (5, 6, 11, 12),
        "venus": (6, 11, 12),
        "saturn": (3, 5, 6, 11),
        "lagna": (1, 3, 4, 6, 10, 11),
    },
}


@dataclass(frozen=True, slots=True)
class AshtakavargaResult:
    """BAV rows per subject planet, and the SAV column sums. Both indexed by sign."""

    bav: dict[str, tuple[int, ...]]
    sav: tuple[int, ...]


def compute_ashtakavarga(
    planet_signs: dict[str, int], lagna_sign: int
) -> AshtakavargaResult:
    """BAV per planet and the SAV, as bindus per sign (0-based sign index)."""
    positions = {**{p: planet_signs[p] for p in SUBJECTS}, "lagna": lagna_sign}

    bav: dict[str, tuple[int, ...]] = {}
    for subject in SUBJECTS:
        counts = [0] * 12
        for contributor, places in BENEFIC_PLACES[subject].items():
            origin = positions[contributor]
            for place in places:
                counts[(origin + place - 1) % 12] += 1
        bav[subject] = tuple(counts)

    sav = tuple(sum(row[sign] for row in bav.values()) for sign in range(12))
    return AshtakavargaResult(bav=bav, sav=sav)
