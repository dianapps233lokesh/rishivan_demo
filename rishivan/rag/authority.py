"""Source authority, from Blueprint §12's tiers.

§12 defines six tiers — S0 primary classical text, S1 traditional commentary, S2
scholarly/critical edition, S3 established practitioner, S4 modern interpretation, S5
experimental — and calls them "engineering categories, not claims about spiritual
authority". §8's rule 4 is what consumes them: "Primary classical source > established
commentary > established practitioner > experimental material."

This replaces a hand-set table of 21 books at invented floats (BPHS 1.00, Phaladeepika
0.90, Bhavartha Ratnakara 0.70) with no stated basis for any value. The tiers do not
rank within themselves, and neither does this: pretending BPHS outranks Saravali by 0.10
was precision nobody had grounds for.
"""

from __future__ import annotations

from rishivan.council.source_matrix import authority_tier

TIER_WEIGHT: dict[str, float] = {
    "S0": 1.00,
    "S1": 0.85,
    "S2": 0.75,
    "S3": 0.60,
    "S4": 0.45,
    "S5": 0.30,
}
"""§12's tiers as retrieval weights, monotonically decreasing per §8 rule 4.

S5 is 0.30 rather than 0 so an unrated book still surfaces when nothing better matches —
a zero would delete it from every reading silently, which is the failure mode this
codebase keeps finding.
"""

DEFAULT_AUTHORITY = TIER_WEIGHT["S5"]
"""An unrated book is treated as experimental, never as classical. Defaulting upward
would let a new upload inherit authority nobody granted it."""


def authority_for_slug(slug: str | None) -> float:
    """Retrieval weight in (0, 1] for a book slug, derived from its §12 tier."""
    return TIER_WEIGHT.get(authority_tier(slug), DEFAULT_AUTHORITY)
