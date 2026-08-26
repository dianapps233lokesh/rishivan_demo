"""Blueprint §12: one evidence hierarchy per life domain.

The blueprint's complaint, verbatim: *"the same chart should not be analysed
with one generic scoring formula for every life question."* That is exactly what
happens without this file - `evidence._raw_weight` is magnitude x authority x
strength whatever was asked, so a D9 confirmation of a marriage reading counts
the same as the 7th-lord placement it is confirming, and a Jaimini karaka counts
the same as both.

This table is the fix, and it is declarative on purpose. Three things come out of
one lookup:

    hierarchy.domain        -> the `domains` filter `index.query` already takes
    hierarchy.vargas        -> the divisions `varga_select` may reach for
    hierarchy.tier_weights  -> handed to `build_evidence`, so a D1 house
                               placement outranks a D9 confirmation of it

**Keyed by Koonji `domain.*` symbols.** Those are what the rule corpus is tagged
with, what `varga/policy.py` scopes divisions by, and what
`timing/activation.py` translates into houses. The client's eight life-domain
keys (atma/prema/...) are a different and equally real taxonomy, and
`LIFE_DOMAIN_OF` bridges them rather than replacing either. A third vocabulary
would be a third thing to drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TIERS: tuple[str, ...] = ("house", "varga", "dasha", "transit", "jaimini")
"""The kinds of evidence a firing can rest on.

`transit` is declared and currently unreachable: no registry predicate expresses
a transit, so no rule can fire on one. Declaring it now means that the day a
transit predicate lands, the weight already exists and nothing has to be
re-tiered underneath answers already given.
"""

DEFAULT_DOMAIN = "domain.temperament"
"""What a question nobody could route reads from. The self, broadly - which is
what an unroutable question is usually about."""


@dataclass(frozen=True, slots=True)
class EvidenceHierarchy:
    """What counts as evidence for this kind of question, and how much."""

    domain: str

    houses: tuple[int, ...]
    """In priority order. The first is the bhava the question is *about*."""

    lords: tuple[int, ...]
    karakas: tuple[str, ...]
    vargas: tuple[str, ...]
    jaimini: tuple[str, ...]

    requires_dasha: bool
    """Whether a claim in this domain is about an *event*, and so needs a period
    before it may be dated. Temperament does not; marriage does. Backwards, this
    field produces a dated personality."""

    requires_transit: bool

    min_independent_sources: int
    """The floor beneath which a claim in this domain is not corroborated
    enough to state. Set here, enforced in `evidence.build_evidence`, which is
    where the corroboration machinery already lives."""

    tier_weights: dict[str, float] = field(default_factory=dict)


def _weights(**overrides: float) -> dict[str, float]:
    """The defaults, plus whatever this domain stresses.

    A function rather than twelve literal dicts: the invariant that matters -
    a house placement outranks a varga confirmation - is then true by
    construction for every row that does not deliberately override it, and the
    test asserting it is checking the overrides rather than twelve copies of the
    same numbers.
    """
    base = {
        "house": 1.0,
        "varga": 0.55,
        "dasha": 0.45,
        "transit": 0.30,
        "jaimini": 0.50,
    }
    base.update(overrides)
    return base


# code                    houses          lords    karakas
#   vargas          jaimini              dasha? transit? sources  overrides
_ROWS: tuple[tuple, ...] = (
    ("domain.relationship", (7, 2, 8, 11), (7, 2),
     ("graha.venus", "graha.jupiter"), ("D9",), ("upapada", "darakaraka"),
     True, True, 2, {"varga": 0.75}),

    ("domain.career", (10, 6, 7, 11, 1), (10, 6),
     ("graha.sun", "graha.saturn", "graha.mercury"), ("D10",),
     ("amatyakaraka",), True, True, 2, {"varga": 0.75}),

    ("domain.wealth", (2, 11, 5, 9), (2, 11),
     ("graha.jupiter", "graha.venus"), ("D2",), (),
     True, False, 2, {}),

    ("domain.property", (4, 12), (4,),
     ("graha.mars", "graha.venus"), ("D4", "D16"), (),
     True, False, 1, {}),

    ("domain.education", (4, 5, 9, 2), (4, 5),
     ("graha.mercury", "graha.jupiter"), ("D24",), (),
     False, False, 1, {}),

    ("domain.progeny", (5, 9, 11), (5,),
     ("graha.jupiter",), ("D7",), ("putrakaraka",),
     True, False, 2, {"varga": 0.70}),

    ("domain.travel", (12, 9, 4, 3), (12, 9),
     ("graha.rahu", "graha.ketu"), ("D4",), (),
     True, False, 1, {}),

    ("domain.spiritual", (9, 12, 5), (9, 12),
     ("graha.jupiter", "graha.ketu"), ("D20",), ("atmakaraka",),
     False, False, 1, {"jaimini": 0.65}),

    ("domain.health", (1, 6, 8, 12), (1, 6),
     ("graha.sun", "graha.moon", "graha.saturn"), ("D30",), (),
     True, True, 2, {}),

    # Longevity is the one row where the corroboration floor is a safety
    # decision rather than a doctrinal one. Three independent sources, and most
    # of these questions never arrive here at all - `REFUSING_FLAGS` in
    # `koonji/question.py` stops the mortality ones at the gate. This row is for
    # the ones that get through phrased as something else.
    ("domain.longevity", (8, 1, 3, 10), (8, 1),
     ("graha.saturn",), (), (),
     True, True, 3, {}),

    ("domain.status", (10, 1, 9, 11), (10, 9),
     ("graha.sun", "graha.jupiter"), ("D3", "D12"), (),
     True, False, 2, {}),

    ("domain.temperament", (1, 5, 9), (1,),
     ("graha.sun", "graha.moon"), ("D60",), ("atmakaraka",),
     False, False, 1, {}),
)

HIERARCHIES: dict[str, EvidenceHierarchy] = {
    row[0]: EvidenceHierarchy(
        domain=row[0],
        houses=row[1],
        lords=row[2],
        karakas=row[3],
        vargas=row[4],
        jaimini=row[5],
        requires_dasha=row[6],
        requires_transit=row[7],
        min_independent_sources=row[8],
        tier_weights=_weights(**row[9]),
    )
    for row in _ROWS
}


def hierarchy_for(domain: str) -> EvidenceHierarchy:
    """Falls back rather than raising.

    Deliberately unlike `varga.policy.policy_for`, which raises on an unknown
    code. That one guards a *computable* division nobody scoped - a real gap
    that should stop the build. This one is reached with whatever the router
    produced, and a router that grows a thirteenth domain should degrade to a
    broad reading rather than to a 500.
    """
    return HIERARCHIES.get(domain, HIERARCHIES[DEFAULT_DOMAIN])
