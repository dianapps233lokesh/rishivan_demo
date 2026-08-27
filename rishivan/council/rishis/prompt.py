"""What a Rishi is shown before it reasons.

Assembled from structured evidence only - claims, citations, tiers, windows -
and never from prose. That is the point of the whole architecture in one file:
a report built from a list of fired rules can be checked against those rules,
and one built from a paragraph cannot.

Three blocks do disproportionate work:

**RULES THAT WERE CANCELLED.** A yoga the VM broke is the single most important
thing a Rishi can be told and the one it will never infer from the fired list.
Without it, a report confidently describes a Raja yoga that a cancellation
clause destroyed - and the cancellation is right there in the evidence graph,
unread.

**VARGAS WITHHELD.** "I did not use D9 because your birth time is recorded to
the hour" is a sentence the narrative layer can only say if the Rishi knew it.

**THE HIERARCHY.** Telling a Rishi that this domain needs two independent
sources is what makes its `confidence_reasons` about the evidence rather than
about its own tone.
"""

from __future__ import annotations

from typing import Optional

from rishivan.council.hierarchy import EvidenceHierarchy
from rishivan.council.rishis.roster import ROLES

INSTRUCTION = """You are one voice on a council reading one chart. You are not
writing an answer for the person who asked - you are filing evidence for a
synthesis that happens later, and for an auditor whose job is to find what you
missed.

Return JSON matching the schema. Six things it asks for, and the middle two are
where most reports go wrong:

  supporting            evidence for. Each item cites the rule ids it rests on.
  weakening             evidence against. REQUIRED. If the chart genuinely says
                        one thing, say that here - "no contrary indication
                        found, and here is what I looked for" - rather than
                        leaving it empty. An empty list with supporting
                        evidence present is rejected outright.
  assumptions           what you took as given.
  would_change_my_mind  what evidence would reverse this.
  score                 -1 to 1, signed. The chart arguing against the thing
                        asked about is an answer.
  confidence            0 to 1, with reasons that name the evidence.

Rules, hard:

  * Every evidence item cites at least one rule id from the lists below. If
    nothing below supports a statement, do not make the statement.
  * A cancelled rule is not evidence. It is evidence that something was
    expected and did not hold, which is usually worth putting in `weakening`.
  * Do not date anything unless a timing window below says so.
  * If nothing below speaks to your remit, set `abstained` and stop. An
    abstention is a real contribution. A filled-in report about a chart that
    fired nothing is not.
"""


def _bare(symbol: str) -> str:
    return symbol.split(".", 1)[-1].replace("_", " ")


def _hierarchy_block(hierarchy: Optional[EvidenceHierarchy]) -> str:
    if hierarchy is None:
        return ""
    lines = [
        f"EVIDENCE HIERARCHY for {_bare(hierarchy.domain)}",
        "  houses, in priority order: "
        + ", ".join(f"{h}th" for h in hierarchy.houses),
        "  lords that matter: " + ", ".join(f"{h}th lord" for h in hierarchy.lords),
    ]
    if hierarchy.karakas:
        lines.append("  natural karakas: "
                     + ", ".join(_bare(k) for k in hierarchy.karakas))
    if hierarchy.vargas:
        lines.append("  divisional charts in scope: " + ", ".join(hierarchy.vargas))
    if hierarchy.jaimini:
        lines.append("  Jaimini factors: " + ", ".join(hierarchy.jaimini))
    lines.append(
        f"  this domain needs {hierarchy.min_independent_sources} independent "
        f"source(s) before a claim may be stated with confidence."
    )
    if hierarchy.requires_dasha:
        lines.append("  this domain is about events, so a claim about WHEN "
                     "needs a period below to rest on.")
    return "\n".join(lines)


def _claims_block(reading, limit: int = 12) -> str:
    if reading is None or not reading.claims:
        return "RULES THAT FIRED\n  none."
    lines = ["RULES THAT FIRED"]
    for claim in reading.claims[:limit]:
        cites = ", ".join(claim.citations()[:4]) or "uncited"
        ids = ", ".join(s.rule_id for s in claim.support[:4])
        tiers = ",".join(sorted({s.tier for s in claim.support}))
        lines.append(
            f"  [{claim.claim_id}] confidence {claim.confidence:.2f} "
            f"({claim.band}, tier {tiers}) — {cites}"
        )
        lines.append(f"      rule_ids: {ids}")
        if claim.against:
            lines.append(
                f"      {len(claim.against)} rule(s) fire AGAINST this claim: "
                + ", ".join(s.rule_id for s in claim.against[:3])
            )
        if not claim.corroboration_met:
            lines.append(
                f"      corroboration NOT met: {claim.independent_sources} "
                f"independent source(s), {claim.corroboration_required} required."
            )
        if claim.requires_activation:
            lines.append("      this is a PROMISE, not an event. It needs a "
                         "period before it may be dated.")
    return "\n".join(lines)


def _cancelled_block(reading, by_id: Optional[dict] = None) -> str:
    """The block a report will not write without.

    A model shown only what fired describes a yoga that the VM already broke,
    confidently, with a citation - because the citation is real and the
    cancellation is the part it never saw.
    """
    if reading is None or not reading.evidence.cancelled:
        return "RULES THAT WERE CANCELLED\n  none."
    lines = ["RULES THAT WERE CANCELLED — these did NOT hold"]
    for rule_id in reading.evidence.cancelled[:10]:
        firing = next(
            (f for f in reading.firings if f.rule_id == rule_id), None
        )
        why = ""
        if firing is not None and firing.cancelled_by:
            why = " — cancelled by " + ", ".join(firing.cancelled_by[:3])
        lines.append(f"  {rule_id}{why}")
    return "\n".join(lines)


def _indeterminate_block(reading) -> str:
    if reading is None or not reading.evidence.indeterminate:
        return ""
    return (
        "RULES THAT COULD NOT BE EVALUATED — a predicate this chart cannot "
        "answer\n  "
        + ", ".join(reading.evidence.indeterminate[:10])
        + "\n  These are not evidence either way. Do not treat them as absent "
          "indications."
    )


def _stated_facts_block(facts) -> str:
    """What the seeker said about their own life.

    Placed directly under the question because it is part of the question. A
    reading that tells someone their marriage window opens in 2030, in reply to
    a message beginning "I got married on 22nd Nov 2025", has not been careful -
    it has been talking past them, and no amount of correct chart work recovers
    that.

    These are assertions about the *past and present*, and the chart is being
    read for what it says about the future. So the instruction is not "agree
    with these": a chart may perfectly well indicate a difficult marriage for
    someone who says they are happily married. It is "do not contradict the
    record" - do not date an event they have told you already happened, and do
    not describe as prospective something they have told you is done.
    """
    if not facts:
        return ""
    lines = ["WHAT THE SEEKER HAS TOLD YOU ABOUT THEIR LIFE"]
    for fact in facts:
        when = (fact.get("when") or "").strip()
        lines.append(f"  {fact.get('text', '')}" + (f" — {when}" if when else ""))
    lines.append(
        "  These are established, not inferred. Do not contradict them: do not "
        "put a date on something they have said already happened, and do not "
        "treat a settled fact as an open question. The chart may still weigh "
        "against a thing they report - say that as a reading of the thing, not "
        "as a doubt about whether it occurred."
    )
    return "\n".join(lines)


def _vargas_block(selection) -> str:
    if selection is None:
        return ""
    lines = [f"DIVISIONAL CHARTS USED: {', '.join(selection.selected)}"]
    for withheld in selection.withheld:
        lines.append(f"  WITHHELD {withheld.code}: {withheld.reason}")
    for note in selection.notes:
        lines.append(f"  NOTE: {note}")
    return "\n".join(lines)


def _timing_block(report) -> str:
    if report is None or not report.by_system:
        return ""
    lines = ["TIMING"]
    for system, window in report.by_system.items():
        if not window.promise:
            lines.append(f"  {system}: no promise, so no window. "
                         + " ".join(window.reasons))
            continue
        lines.append(f"  {system}: activation {window.activation}, "
                     f"trigger {window.trigger}, peak {window.peak} "
                     f"(confidence {window.confidence})")
        lines.extend(f"    {reason}" for reason in window.reasons)
    agreement = report.agreement()
    if agreement is not None:
        lines.append(f"  systems agree: {agreement}")
    return "\n".join(lines)


def _chart_block(chart_state, hierarchy: Optional[EvidenceHierarchy]) -> str:
    """The diagnosis, narrowed to what this hierarchy points at.

    A full §6 diagnosis is nine planets and twelve houses of detail. Handing
    all of it to a marriage Rishi buries the 7th under the 3rd, and a model
    reading past the relevant part is indistinguishable from one that had no
    access to it.
    """
    if chart_state is None:
        return ""
    lines = [f"CHART DIAGNOSIS (lagna {chart_state.lagna}, "
             f"{chart_state.framework})"]
    houses = hierarchy.houses if hierarchy else tuple(range(1, 13))
    for bhava in houses[:6]:
        try:
            house = chart_state.house(bhava)
        except KeyError:
            continue
        lines.append(
            f"  {bhava}th ({house.rashi}): lord {house.lord} in the "
            f"{house.lord_placement}th, occupants "
            f"{', '.join(house.occupants) or 'none'}, influence "
            f"{house.benefic_influence:+.2f}"
        )
        lines.extend(f"      {r}" for r in house.influence_reason[:2])

    grahas = [_bare(k) for k in (hierarchy.karakas if hierarchy else ())]
    for graha in grahas:
        try:
            planet = chart_state.planet(graha.capitalize())
        except KeyError:
            continue
        lines.append(
            f"  {planet.graha}: {planet.rashi}, {planet.dignity}, in the "
            f"{planet.bhava}th, {planet.functional_nature} "
            f"({planet.functional_reason}), strength "
            f"{planet.strength.claimable_band.value}"
        )
    return "\n".join(lines)


def build_rishi_report_prompt(
    *,
    rishi: str,
    question: str,
    hierarchy=None,
    chart_state=None,
    reading=None,
    vargas=None,
    timing=None,
    unreviewed: bool = False,
    findings: tuple[str, ...] = (),
    stated_facts=(),
) -> str:
    """One Rishi's whole context. Deterministic given the state."""
    role = ROLES.get(rishi)
    blocks = [
        INSTRUCTION,
        f"YOUR REMIT\n  {role.remit if role else 'the classical reading'}",
        f"THE QUESTION\n  {question}",
        _stated_facts_block(stated_facts),
        _hierarchy_block(hierarchy),
        _chart_block(chart_state, hierarchy),
        _claims_block(reading),
        _cancelled_block(reading),
        _indeterminate_block(reading),
        _vargas_block(vargas),
        _timing_block(timing),
    ]
    if unreviewed:
        blocks.append(
            "PROVENANCE\n  These rules were extracted from the classical texts "
            "and have not yet been through human review. Weigh them as "
            "unverified extractions, and say so in `assumptions`."
        )
    if findings:
        blocks.append(
            "THE AUDITOR RETURNED THIS TO YOU\n"
            + "\n".join(f"  {f}" for f in findings)
            + "\n  Address each point. If a finding is wrong, say why in "
              "`weakening` rather than ignoring it."
        )
    return "\n\n".join(b for b in blocks if b)
