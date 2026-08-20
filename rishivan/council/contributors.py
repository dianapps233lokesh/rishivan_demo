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


def timing_contribution(
    chart, applicable: list[RuleHit], *, when=None
) -> ContributorReport | None:
    """Ritam: which dasha periods are running, and the rules that activate a promise.

    §13 calls Muhurta and timing a cross-domain service, which is exactly this shape:
    every domain's §4-11 protocol ends in a Dasha step, so the timing values belong in
    any reading that asks WHEN -- supplied to whoever owns the subject, not spoken by
    Ritam directly.
    """
    from datetime import datetime

    from rishivan.chart.dasha import current_periods

    periods = current_periods(chart, when or datetime.now())
    computed = {
        label: f"{period.lord} until {period.end.date().isoformat()}"
        for label, period in (
            ("Mahadasha", periods.get("maha")),
            ("Antardasha", periods.get("antar")),
            ("Pratyantardasha", periods.get("pratyantar")),
        )
        if period is not None
    }
    rules = tuple(r for r in applicable if r.rule_category == "timing")
    report = ContributorReport(
        rishi="ritam",
        computed=computed,
        rules=rules,
        note=f"{len(rules)} timing rules true of this chart" if rules else "",
    )
    return None if report.is_empty else report


def pattern_contribution(chart, applicable: list[RuleHit]) -> ContributorReport | None:
    """Vyom: the chart's pattern layer -- nakshatra and conjunctions.

    Every §4-11 protocol has a "major combinations" step, and yoga recognition does not
    exist in this repo. Reporting only what IS computed keeps the gap visible rather
    than letting the primary infer combinations nobody verified.
    """
    moon = chart.planets["Moon"]
    computed = {"Janma nakshatra": f"{moon.nakshatra}"}
    rules = tuple(
        r for r in applicable
        if any(
            atom.get("type") in {"conjunct", "planet_in_nakshatra"}
            for atom in (r.condition.get("atoms") or [])
        )
    )
    report = ContributorReport(
        rishi="vyom",
        computed=computed,
        rules=rules,
        note="yoga recognition is not implemented; combinations are unverified",
    )
    return None if report.is_empty else report


def remedy_contribution(applicable: list[RuleHit]) -> ContributorReport | None:
    """Tejan: rules that carry their own remedy.

    Blueprint §17 keeps remedies in a separate corpus and out of the Rishi set, which is
    why Tejan contributes rather than speaks. A remedy is only ever offered attached to
    the rule that diagnosed the affliction -- detached, it is advice with no evidence.
    """
    rules = tuple(r for r in applicable if r.remedies)
    if not rules:
        return None
    return ContributorReport(
        rishi="tejan",
        rules=rules,
        note=f"{len(rules)} of the matched rules state their own remedy",
    )


DASHA_WORDS = ("dasha", "mahadasha", "antardasha", "bhukti", "pratyantar")


def gather(
    chart, applicable: list[RuleHit], *, routing, question: str, when=None
) -> tuple[ContributorReport, ...]:
    """Every non-empty contribution for this question, primary's own rules excluded.

    Triggers are deterministic so a reading is reproducible. `vyom` fires on every
    question because every §4-11 protocol contains a combinations step and a Nakshatra
    step -- pretending that is selective would be a lie about what it does.
    """
    text = (question or "").lower()
    reports: list[ContributorReport | None] = []

    if routing.application == "timing" or any(word in text for word in DASHA_WORDS):
        reports.append(timing_contribution(chart, applicable, when=when))

    reports.append(pattern_contribution(chart, applicable))
    reports.append(remedy_contribution(applicable))

    for domain in routing.secondary:
        reports.append(domain_contribution(domain, applicable))

    return tuple(r for r in reports if r is not None and not r.is_empty)
