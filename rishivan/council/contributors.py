"""Evidence one Rishi computes for another.

Eight Rishis §12 asks for a primary Rishi with supporting ones, but a supporting Rishi
that SPEAKS produces two opinions rather than one grounded answer. Here a supporting
Rishi computes instead: it reports what it alone can establish -- the running dasha, the
rules inside its own coverage -- and the primary writes the single reply.

Every contributor is deterministic. No LLM call, so a report is reproducible, unit
testable, and cannot paraphrase a computed value into flavour text.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rishivan.council.constitution import CONSTITUTIONS
from rishivan.council.domains import primary_rishi_for
from rishivan.knowledge.concepts import concepts_of
from rishivan.rag.rules import RuleHit


@dataclass(frozen=True)
class ContributorReport:
    """What one supporting Rishi established, ready to label in the primary's prompt."""

    rishi: str
    computed: dict[str, str] = field(default_factory=dict)
    """Label -> value. Ground truth, copied verbatim into the prompt, never paraphrased."""
    rules: tuple[RuleHit, ...] = ()
    note: str = ""
    """One templated sentence. Never generated."""

    @property
    def is_empty(self) -> bool:
        return not self.computed and not self.rules


def domain_contribution(
    domain: str, applicable: list[RuleHit]
) -> ContributorReport | None:
    """Rules a secondary life domain can add, gated on ITS OWN coverage.

    The gate is the same one the primary's rules pass through -- a rule whose subject
    house sits outside the domain's houses is not evidence for that domain, whatever its
    affinity tag says. So a secondary broadens the houses consulted without loosening
    the standard on any of them.
    """
    constitution = CONSTITUTIONS.get((domain or "").lower())
    if constitution is None:
        return None

    houses = constitution.houses
    inside = tuple(
        rule
        for rule in applicable
        if concepts_of(rule.condition).subject_houses & houses
    )
    if not inside:
        return None
    return ContributorReport(
        rishi=primary_rishi_for(domain),
        rules=inside,
        note=f"{len(inside)} rules on the houses {domain.upper()} owns",
    )
