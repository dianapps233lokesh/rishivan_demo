"""Arrange what the council said. Do not re-decide it.

Deterministic on purpose. The Rishis reasoned, the auditor objected, and this
node's job is to lay that out for the narrative voice - not to run a ninth
opinion over the eight that already exist.

**Agreement is reported, never averaged.** Two Rishis reading a chart the same
way is corroboration a reader can weigh; two Rishis averaged is a number nobody
can check. The same argument `timing/query.py` makes about dasha systems, for
the same reason.

**Disagreement survives.** A council that produced one positive and one negative
reading has told the reader something true, and collapsing it to the mean tells
them something false with more confidence than either Rishi had.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState

AGREEMENT_BAND = 0.15
"""Below this, a score is neither for nor against. A council of near-zero
scores is undecided, and rounding it into a direction manufactures a verdict."""


def _latest_per_rishi(reports: list) -> list:
    """The last report each Rishi filed.

    `reports` is additive, so a re-examination appends rather than replaces.
    The earlier report stays in state for the trace - what was corrected is
    worth keeping - but the council speaks with its latest voice.
    """
    latest: dict[str, object] = {}
    for report in reports:
        latest[report.rishi] = report
    return list(latest.values())


def synthesis_node(state: RishivanState) -> dict:
    reports = _latest_per_rishi(list(state.get("reports") or []))
    speaking = [r for r in reports if not r.abstained]
    abstained = [r for r in reports if r.abstained]

    positive = [r for r in speaking if r.score > AGREEMENT_BAND]
    negative = [r for r in speaking if r.score < -AGREEMENT_BAND]
    undecided = [
        r for r in speaking if -AGREEMENT_BAND <= r.score <= AGREEMENT_BAND
    ]

    convergence = {
        "speaking": len(speaking),
        "abstained": len(abstained),
        "agreeing": max(len(positive), len(negative)),
        "for": [r.rishi for r in positive],
        "against": [r.rishi for r in negative],
        "undecided": [r.rishi for r in undecided],
        "disagreement": bool(positive and negative),
    }

    return {
        "council_summary": _summary(state, reports, speaking, abstained,
                                    positive, negative),
        "convergence": convergence,
    }


def _summary(state, reports, speaking, abstained, positive, negative) -> str:
    """The block the narrative prompt reads. Never empty."""
    if not reports:
        return (
            "COUNCIL\n  No Rishi was convened for this question — nothing in "
            "the rule base fired in a domain any of them covers. Answer from "
            "the retrieved passages alone, and say that the rule base was "
            "silent rather than implying it agreed."
        )

    lines = ["COUNCIL"]
    if not speaking:
        lines.append(
            f"  All {len(abstained)} Rishi(s) abstained. That is a finding: "
            f"the classical material this engine holds is silent on the "
            f"question as asked. Say so plainly."
        )
        for report in abstained:
            lines.append(f"    {report.rishi} abstained — {report.abstained}")
        return "\n".join(lines)

    for report in speaking:
        lines.append(
            f"  {report.rishi} — score {report.score:+.2f}, confidence "
            f"{report.confidence:.2f}"
        )
        for item in report.supporting[:4]:
            lines.append(
                f"      for:     {item.statement} "
                f"[{', '.join(item.rule_ids[:2])}, {item.tier}]"
            )
        for item in report.weakening[:4]:
            # Never trimmed to nothing, whatever the length budget. Suppressing
            # the disconfirming half is the failure this architecture exists to
            # make impossible, and a quiet truncation is the same failure.
            lines.append(
                f"      against: {item.statement} "
                f"[{', '.join(item.rule_ids[:2])}, {item.tier}]"
            )
        for reason in report.confidence_reasons[:2]:
            lines.append(f"      confidence because: {reason}")
        for assumption in report.assumptions[:2]:
            lines.append(f"      assumed: {assumption}")
        for change in report.would_change_my_mind[:2]:
            lines.append(f"      would change this: {change}")

    for report in abstained:
        lines.append(f"  {report.rishi} abstained — {report.abstained}")

    if positive and negative:
        lines.append(
            f"  THE COUNCIL DISAGREES. "
            f"{', '.join(r.rishi for r in positive)} read this positively; "
            f"{', '.join(r.rishi for r in negative)} read it negatively. "
            f"Report the disagreement. Do not split the difference — an "
            f"average is a position no Rishi held."
        )
    elif len(positive) > 1 or len(negative) > 1:
        agreeing = positive if len(positive) > 1 else negative
        lines.append(
            f"  {len(agreeing)} Rishis agree, reasoning from different "
            f"evidence. That is corroboration and may be stated as such — "
            f"but it is not certainty, and none of them claimed it was."
        )

    audit = state.get("audit")
    if audit is not None and (audit.findings or audit.note):
        lines.append("  THE AUDITOR")
        for finding in audit.findings[:6]:
            lines.append(f"      [{finding.kind}] {finding.detail}")
        if audit.note:
            lines.append(f"      {audit.note}")

    if state.get("reading_is_unreviewed"):
        lines.append(
            "  These rules are extractions from the classical texts that have "
            "not been through human review. Do not present them as verified."
        )

    return "\n".join(lines)
