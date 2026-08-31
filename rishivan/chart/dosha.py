"""Mangal (Kuja) dosha.

The first affliction any classical marriage reading checks, and one the direct
lane has never mentioned — `prema`'s protocol step 6 is "Yoga, affliction and
modification" and Mars was only ever present as a row in a placements table.

**Checked from three reference points, not one.** Mars is judged from the lagna,
from the Moon and from Venus. A chart clear from the lagna and afflicted from the
Moon is the ordinary case rather than an edge one, and checking only the first is
how a reading declares a marriage unobstructed where the tradition would not.
"""

from __future__ import annotations

from typing import Optional

KUJA_HOUSES: tuple[int, ...] = (1, 2, 4, 7, 8, 12)
"""The houses whose occupation by Mars raises the dosha.

**The North Indian convention, which includes the 2nd.** Several South Indian
lineages read 1/4/7/8/12 and omit it. Stated rather than silently chosen: a
verdict that does not name its house set is a verdict nobody can check, and the
two conventions disagree about real charts.
"""

CONVENTION = (
    "Mars in houses 1, 2, 4, 7, 8 or 12, counted separately from the Lagna, from "
    "the Moon and from Venus. North Indian house set — several South Indian "
    "lineages omit the 2nd."
)

_REFERENCES = ("lagna", "moon", "venus")


def _reference_sign(chart, reference: str) -> Optional[int]:
    if reference == "lagna":
        return getattr(chart, "lagna_rashi_index", None)
    position = chart.planets.get(reference.capitalize())
    return None if position is None else position.rashi_index


def kuja_dosha(chart) -> Optional[dict]:
    """The dosha from each reference point, and the combined verdict.

    Returns None when Mars is absent. A chart with no Mars is a broken chart, and
    reporting it as free of dosha would be a false clearance — the one failure
    mode worse than not answering.
    """
    mars = chart.planets.get("Mars")
    if mars is None:
        return None

    seen: dict[str, dict] = {}
    for reference in _REFERENCES:
        origin = _reference_sign(chart, reference)
        if origin is None:
            continue
        house = (mars.rashi_index - origin) % 12 + 1
        seen[reference] = {"house": house, "afflicted": house in KUJA_HOUSES}

    if not seen:
        return None
    return {
        "present": any(entry["afflicted"] for entry in seen.values()),
        "from": seen,
        "houses": KUJA_HOUSES,
        "convention": CONVENTION,
    }
