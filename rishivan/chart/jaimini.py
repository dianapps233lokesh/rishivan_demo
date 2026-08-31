"""Chara karakas and the arudha padas.

`CONSTITUTIONS['prema'].protocol` step 5 is "Jaimini indicators" and
`blocked_concepts` has listed Darakaraka, Upapada and Arudha since the
constitutions were written, because nothing computed them. Every marriage
reading has therefore skipped step 5 — correctly declaring it unavailable, but
skipping it all the same.

**Method, and why it is stated rather than assumed.** Divisional and Jaimini
schemes are exactly where authorities diverge, and `varga/policy.py` already
holds this repo to "no method without a source". So each function names the
scheme it implements and the choice it makes where schemes differ.

Zero I/O and no ephemeris call: everything here is arithmetic on a computed
`Chart`.
"""

from __future__ import annotations

from typing import Optional

KARAKA_ORDER: tuple[str, ...] = (
    "atma", "amatya", "bhratri", "matri", "putra", "gnati", "dara",
)
"""Highest degree to lowest — self, career, siblings, mother, children,
adversity, spouse.

**The seven-karaka Parashari scheme**, which excludes the nodes. The
eight-karaka scheme admits Rahu with its degree reversed (30 minus the degree,
because it moves backwards) and shifts every karaka below it by one position.
Mixing them silently changes who the Darakaraka is, so this implements one and
says which.
"""

KARAKA_NAMES: dict[str, str] = {
    "atma": "Atmakaraka (the self)",
    "amatya": "Amatyakaraka (career, counsel)",
    "bhratri": "Bhratrikaraka (siblings, courage)",
    "matri": "Matrikaraka (mother)",
    "putra": "Putrakaraka (children)",
    "gnati": "Gnatikaraka (adversity, obstruction)",
    "dara": "Darakaraka (the spouse)",
}

_KARAKA_GRAHAS = ("Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")

METHOD = (
    "Seven-karaka Parashari scheme: the seven grahas ranked by degrees traversed "
    "in their own sign, highest first. The nodes are excluded."
)


def chara_karakas(chart) -> dict[str, str]:
    """Which graha holds each chara karaka.

    Ties are broken by the conventional reading order rather than left to
    whatever order the dict happened to be built in. Two grahas at the identical
    degree is vanishingly rare and a non-deterministic answer to it would be a
    reading that changes between two runs of the same chart, which is the one
    thing `temperature=0` was set to prevent.
    """
    ranked = sorted(
        (
            (chart.planets[name].degree_in_rashi, -_KARAKA_GRAHAS.index(name), name)
            for name in _KARAKA_GRAHAS
            if name in chart.planets
        ),
        reverse=True,
    )
    return {
        karaka: name
        for karaka, (_degree, _tie, name) in zip(KARAKA_ORDER, ranked)
    }


def arudha_of(*, house_sign: int, lord_sign: int) -> int:
    """The arudha pada of a house, as a 0-based sign index.

    Count from the house to its lord, then as far again from the lord. The
    classical exception applies: an arudha falling in the 1st or the 7th from the
    house it was derived from is discarded and the 10th from it taken instead —
    without it the pada collapses onto its own house and carries no information.

    Source: Jaimini Sutras 1.1, as given in Parashara's arudha chapter.
    """
    distance = (lord_sign - house_sign) % 12
    pada = (lord_sign + distance) % 12
    if (pada - house_sign) % 12 in (0, 6):
        pada = (pada + 9) % 12
    return pada


def _pada(chart, house: int) -> Optional[dict]:
    from rishivan.chart.ephemeris import RASHI_LORDS, RASHIS

    lagna = getattr(chart, "lagna_rashi_index", None)
    if lagna is None:
        return None
    house_sign = (lagna + house - 1) % 12
    lord = RASHI_LORDS[house_sign]
    position = chart.planets.get(lord)
    if position is None:
        return None
    sign_index = arudha_of(house_sign=house_sign, lord_sign=position.rashi_index)
    return {
        "sign_index": sign_index,
        "sign": RASHIS[sign_index],
        "lord": RASHI_LORDS[sign_index],
        "house_from_lagna": (sign_index - lagna) % 12 + 1,
        "derived_from_lord": lord,
    }


def arudha_lagna(chart) -> Optional[dict]:
    """AL — the arudha of the 1st. How the person is perceived, not who they are."""
    return _pada(chart, 1)


def upapada_lagna(chart) -> Optional[dict]:
    """UL — the arudha of the 12th, and the principal Jaimini marriage indicator.

    The 12th is read for marriage in this scheme because it is the house of what
    is given away; the 2nd from the UL is then read for the durability of the
    partnership. That second step is left to the reading rather than asserted
    here — this function computes the pada and stops.
    """
    return _pada(chart, 12)
