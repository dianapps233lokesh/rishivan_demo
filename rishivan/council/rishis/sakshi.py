"""The adversarial auditor, and the bound that stops it looping.

Sakshi receives every report and hunts for what the council missed. Seven
things, and **six of them are checkable in code** - so they are:

    unmentioned_cancellation  the VM broke a rule and no report said so
    under_corroborated        a claim below its domain's source floor
    contradiction             two reports disagreeing in sign
    undated_timing            a date asserted with no window behind it
    unexamined_hierarchy      a house the hierarchy names that nobody looked at
    no_evidence               the council abstained wholesale

Doing them deterministically means the audit still works when the model call
fails, and it means each hunt has a test rather than a hope. The seventh -
alternative explanations - is genuinely a model's job and is the only part that
costs a call.

**Sakshi has no persona and never speaks in a voice.** It audits. Adding a ninth
persona would break `ALL_RISHI_NAMES` and the no-orphan-domain test for nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

#: A four-digit year, or an explicit month-and-year. Deliberately narrow: the
#: check is for a report DATING something, and "in the coming period" is not a
#: date. A loose pattern here produces findings on every report and an auditor
#: nobody reads.
_DATE = re.compile(
    r"\b(?:19|20)\d\d\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}\b",
    re.IGNORECASE,
)

MAX_REVISIONS = 1
"""One re-examination, then forward regardless.

An unbounded critic loop is how a graph hangs in production at 3am. The bound
is a single comparison and it is the most important line in this file.
"""


@dataclass(frozen=True, slots=True)
class Finding:
    kind: str
    rishi: str
    """Who must address it. A finding addressed to nobody cannot be acted on,
    and re-examination has nowhere to send it."""

    detail: str
    """Long enough to act on. "missing evidence" is not a finding, it is a
    category."""


@dataclass(frozen=True, slots=True)
class Audit:
    findings: list[Finding] = field(default_factory=list)
    note: str = ""
    """The model's contribution, when there was one - alternative explanations
    and anything the six mechanical hunts cannot see."""

    def by_rishi(self) -> dict[str, tuple[str, ...]]:
        out: dict[str, list[str]] = {}
        for finding in self.findings:
            if finding.rishi:
                out.setdefault(finding.rishi, []).append(finding.detail)
        return {k: tuple(v) for k, v in out.items()}


def _cited(reports) -> set[str]:
    ids: set[str] = set()
    for report in reports:
        for item in list(report.supporting) + list(report.weakening):
            ids.update(item.rule_ids)
    return ids


def _statements(reports) -> list[tuple[str, str]]:
    out = []
    for report in reports:
        for item in list(report.supporting) + list(report.weakening):
            out.append((report.rishi, item.statement))
    return out


def _has_window(timing) -> bool:
    if timing is None or not getattr(timing, "by_system", None):
        return False
    return any(w.promise for w in timing.by_system.values())


def audit_deterministic(reports, *, hierarchy, reading, timing) -> list[Finding]:
    """The six hunts. No model, no network, no clock."""
    findings: list[Finding] = []
    reports = list(reports)
    speaking = [r for r in reports if not r.abstained]
    first = speaking[0].rishi if speaking else (
        reports[0].rishi if reports else ""
    )

    if not speaking:
        findings.append(Finding(
            kind="no_evidence", rishi=first,
            detail="Every Rishi abstained. If the chart genuinely fired "
                   "nothing in this domain, the answer is that the classical "
                   "material is silent here - which must be said, not implied "
                   "by a short reply.",
        ))
        return findings

    cited = _cited(speaking)

    # 1. A cancellation nobody mentioned.
    if reading is not None:
        for rule_id in getattr(reading.evidence, "cancelled", [])[:10]:
            if rule_id not in cited:
                findings.append(Finding(
                    kind="unmentioned_cancellation", rishi=first,
                    detail=f"Rule {rule_id} was CANCELLED by the engine and no "
                           f"report mentions it. A condition that was expected "
                           f"and did not hold belongs in `weakening`; leaving "
                           f"it out describes a yoga as intact when it is not.",
                ))

    # 2. A claim below its domain's corroboration floor.
    if reading is not None:
        for claim in getattr(reading, "claims", []):
            if not getattr(claim, "corroboration_met", True):
                findings.append(Finding(
                    kind="under_corroborated", rishi=first,
                    detail=f"Claim {claim.claim_id} rests on "
                           f"{claim.independent_sources} independent source(s) "
                           f"but this domain requires "
                           f"{claim.corroboration_required}. State it as an "
                           f"indication, not a finding.",
                ))

    # 3. Two reports disagreeing in sign. Surfaced, never resolved - two
    #    Rishis reading the same chart oppositely is what a reader should see.
    positive = [r for r in speaking if r.score > 0.15]
    negative = [r for r in speaking if r.score < -0.15]
    if positive and negative:
        findings.append(Finding(
            kind="contradiction", rishi=positive[0].rishi,
            detail=f"{', '.join(r.rishi for r in positive)} read this "
                   f"positively while {', '.join(r.rishi for r in negative)} "
                   f"read it negatively. Say which evidence separates you, or "
                   f"acknowledge the disagreement stands.",
        ))

    # 4. A date with nothing to rest on.
    if not _has_window(timing):
        for rishi, statement in _statements(speaking):
            if _DATE.search(statement):
                findings.append(Finding(
                    kind="undated_timing", rishi=rishi,
                    detail=f"\"{statement[:80]}\" names a date, but no dasha "
                           f"window supports one. A period is arithmetic; a "
                           f"date needs a promise the timing engine could "
                           f"land in.",
                ))
                break

    # 5. A house the hierarchy names that nobody looked at.
    if hierarchy is not None:
        text = " ".join(s for _, s in _statements(speaking))
        unexamined = [
            h for h in hierarchy.houses
            if not re.search(rf"\b{h}(?:st|nd|rd|th)\b", text)
        ]
        if unexamined:
            findings.append(Finding(
                kind="unexamined_hierarchy", rishi=first,
                detail=f"The hierarchy for "
                       f"{hierarchy.domain.split('.', 1)[-1]} names the "
                       f"{', '.join(f'{h}th' for h in unexamined)} and no "
                       f"report examined them. Either they carry evidence or "
                       f"their silence is itself worth stating.",
            ))

    return findings


def route_after_sakshi(state) -> str:
    """re_examine · synthesis

    Pure, and the bound is the point. `revisions >= MAX_REVISIONS` forwards
    regardless of how much the auditor still objects to - a critic that can
    always send the council back is a graph that never returns.
    """
    audit: Optional[Audit] = state.get("audit")
    if audit is None or not audit.findings:
        return "synthesis"
    if state.get("revisions", 0) >= MAX_REVISIONS:
        return "synthesis"
    return "re_examine"
