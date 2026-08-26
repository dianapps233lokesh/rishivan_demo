"""The auditor's turn, and the one bounded loop in the graph.

Deterministic first. `audit_deterministic` runs six mechanical hunts with no
model involved, so the audit still works when the call fails - and when it
fails, the findings are the ones a test covers rather than the ones a model
happened to notice.

The model adds the seventh hunt only: alternative explanations, and anything
the six cannot see. Its output is a note, never a finding, because a finding
sends Rishis back to work and a hallucinated one sends them back to work on
nothing.
"""

from __future__ import annotations

from rishivan.graph.state import RishivanState

MODEL_TIER = "flash"

AUDIT_INSTRUCTION = """You are the auditor on a council reading one chart. You
do not give a reading. You look for what the council got wrong.

Six mechanical checks have already run and their findings are below. Your job
is the seventh, which no check can do: **is there a different explanation for
this evidence that nobody proposed?**

Answer in three sentences or fewer. If the council's reading is the best
account of the evidence shown, say exactly that — an auditor who always finds
something is an auditor nobody reads.
"""


def sakshi_node(state: RishivanState, *, client) -> dict:
    from rishivan.council.client import model_name
    from rishivan.council.rishis.sakshi import Audit, audit_deterministic

    reports = list(state.get("reports") or [])
    findings = audit_deterministic(
        reports,
        hierarchy=state.get("hierarchy"),
        reading=state.get("reading"),
        timing=state.get("timing"),
    )

    note = ""
    if reports:
        try:
            response = client.models.generate_content(
                model=model_name(MODEL_TIER),
                contents=_audit_prompt(state, reports, findings),
                config={"temperature": 0.3},
            )
            note = (response.text or "").strip()
        except Exception:  # noqa: BLE001
            # The six mechanical findings stand on their own. Losing the
            # seventh hunt is a smaller loss than losing the audit.
            note = ""

    return {"audit": Audit(findings=findings, note=note)}


def _audit_prompt(state, reports, findings) -> str:
    lines = [AUDIT_INSTRUCTION, f"THE QUESTION\n  {state['question']}", "THE REPORTS"]
    for report in reports:
        if report.abstained:
            lines.append(f"  {report.rishi}: ABSTAINED — {report.abstained}")
            continue
        lines.append(
            f"  {report.rishi}: score {report.score:+.2f}, confidence "
            f"{report.confidence:.2f}"
        )
        for item in report.supporting[:4]:
            lines.append(f"      for:     {item.statement} [{', '.join(item.rule_ids[:2])}]")
        for item in report.weakening[:4]:
            lines.append(f"      against: {item.statement} [{', '.join(item.rule_ids[:2])}]")
        for assumption in report.assumptions[:3]:
            lines.append(f"      assumed: {assumption}")

    lines.append("FINDINGS THE MECHANICAL CHECKS ALREADY RAISED")
    if findings:
        lines.extend(f"  [{f.kind}] {f.detail}" for f in findings)
    else:
        lines.append("  none.")
    return "\n".join(lines)


def re_examine_node(state: RishivanState) -> dict:
    """Hand the findings back to the Rishis they name, once.

    Writes `findings_for` and increments `revisions`. The increment is what
    `route_after_sakshi` bounds on, so it must happen here rather than in the
    router - a router that mutates is a router the table-driven tests cannot
    exercise.

    `reports` is additive, so the second pass **appends** rather than replaces.
    Synthesis takes the latest report per Rishi and keeps the earlier one in the
    trace, which makes the correction visible instead of overwriting the thing
    that was corrected.
    """
    audit = state.get("audit")
    return {
        "findings_for": audit.by_rishi() if audit else {},
        "revisions": state.get("revisions", 0) + 1,
    }
