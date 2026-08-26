"""Everything the narrative may say, and nothing else.

**The gate is on the prompt.** This is the load-bearing sentence of the whole
module, and it is a design decision rather than an implementation detail. A
model cannot cite a rule it was never shown, so the reliable place to stop an
over-claim is *before* generation, by never putting the material in front of it.
Asking a model nicely not to over-claim works most of the time, and "most of the
time" is how a product ends up confidently wrong in public.

What that means concretely: a claim below `INSUFFICIENT_BELOW` does not appear
in the plan, so it does not appear in the prompt, so no amount of enthusiasm can
put it in the answer. A date has nowhere to come from unless a dasha window
attached one.

**Phrasing is licensed, not requested.** Each claim carries the exact language
its confidence band permits, taken verbatim from `evidence.BANDS`. The band
vocabulary has no way to say "will definitely" - that is not an oversight to be
fixed later, it is the vocabulary doing its job.

**And it is plain data.** `AnswerPlan` is what leaves the graph. Narration
happens outside, from this, which is what removes the live generator from state
and lets the graph be checkpointed at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rishivan.koonji.evidence import INSUFFICIENT_BELOW

DATED_BANDS = frozenset({"strongly_indicated", "consistently_supported"})
"""Bands confident enough to carry a date at all, given a window.

A window says *when* a promise could activate. A weak claim with a window is
still a weak claim, and pinning a year to it makes it sound like the year is the
uncertain part.
"""

AGREEMENT_BAND = 0.15
"""Below this a Rishi's score is neither for nor against. Rounding an undecided
council into a direction manufactures a verdict nobody reached."""


@dataclass(frozen=True, slots=True)
class AllowedClaim:
    """One statement the prose may make, with everything needed to check it."""

    claim_id: str
    band: str
    phrasing: str
    """The language this band licenses, verbatim from `evidence.BANDS`. Copied
    from the claim rather than re-derived here: a second copy of the band
    vocabulary is a second thing to drift."""

    confidence: float
    citations: tuple[str, ...]
    rule_ids: tuple[str, ...]
    tier: str
    """The weakest kind of evidence this claim rests on. A reader shown a claim
    should be able to see it came from a divisional chart rather than from the
    D1 placement it is confirming."""

    counter: tuple[str, ...] = ()
    """What argues against it. Never dropped - if counter-evidence survives the
    evidence graph and dies here, it has been suppressed, just later and less
    visibly."""

    corroborated: bool = True
    window: str = ""
    """Only when a dasha window supports a date for this claim. Empty means the
    prose has nowhere to get a year from."""


@dataclass(frozen=True, slots=True)
class AnswerPlan:
    """The narrative gate. Plain data, deliberately."""

    question: str
    domain: str
    allowed: tuple[AllowedClaim, ...] = ()

    must_say: tuple[str, ...] = ()
    """Withheld vargas, unmet corroboration, abstentions, unreviewed rules.
    Things a reader is entitled to and a model would otherwise smooth over,
    because they make the answer less satisfying."""

    must_not_say: tuple[str, ...] = ()
    """The specific over-claims *this run* is at risk of. Not a generic
    style guide - a generic prohibition is one a model reads past."""

    disagreement: str = ""
    insufficient: bool = False
    unreviewed: bool = False

    @property
    def top_band(self) -> str:
        return self.allowed[0].band if self.allowed else ""

    def claim_ids(self) -> tuple[str, ...]:
        return tuple(c.claim_id for c in self.allowed)


def _weakest_tier(claim) -> str:
    from rishivan.council.hierarchy import TIERS

    order = ("house", "jaimini", "dasha", "varga", "transit")
    tiers = {getattr(s, "tier", "house") for s in claim.support} or {"house"}
    known = [t for t in tiers if t in TIERS] or ["house"]
    return max(known, key=order.index)


def _active_window(timing) -> str:
    """The activation window, when there is a promise behind it.

    A promise-less window is not a window. `EventWindow` already returns every
    stage as None in that case, and treating the object's existence as a date
    source would undo the gate `timing/windows.py` exists to hold.
    """
    if timing is None or not getattr(timing, "by_system", None):
        return ""
    for window in timing.by_system.values():
        if getattr(window, "promise", False) and window.activation is not None:
            return str(window.activation)
    return ""


def build_answer_plan(
    *,
    question: str,
    domain: str,
    hierarchy=None,
    reading=None,
    reports=(),
    audit=None,
    timing=None,
    vargas=None,
    unreviewed: bool = False,
) -> AnswerPlan:
    """Assemble the gate. Deterministic - no client, no clock."""
    reports = list(reports)
    speaking = [r for r in reports if not r.abstained]
    abstained = [r for r in reports if r.abstained]

    window = _active_window(timing)
    allowed: list[AllowedClaim] = []
    must_say: list[str] = []

    claims = list(getattr(reading, "claims", []) or [])
    for claim in sorted(claims, key=lambda c: -c.confidence):
        if claim.confidence < INSUFFICIENT_BELOW:
            # Not filtered downstream, not down-weighted: absent. This is the
            # gate, and it works because it is subtractive.
            continue
        corroborated = getattr(claim, "corroboration_met", True)
        allowed.append(AllowedClaim(
            claim_id=claim.claim_id,
            band=claim.band,
            phrasing=claim.phrasing,
            confidence=round(claim.confidence, 4),
            citations=tuple(claim.citations()),
            rule_ids=tuple(s.rule_id for s in claim.support),
            tier=_weakest_tier(claim),
            counter=tuple(s.citation for s in claim.against if s.citation),
            corroborated=corroborated,
            window=window if (window and claim.band in DATED_BANDS) else "",
        ))
        if not corroborated:
            must_say.append(
                f"{claim.claim_id} is not corroborated to this domain's "
                f"standard: {claim.independent_sources} independent source(s) "
                f"where it asks for {claim.corroboration_required}. Say it as "
                f"an indication, not as a finding."
            )

    if vargas is not None:
        for withheld in getattr(vargas, "withheld", ()):
            must_say.append(withheld.reason)

    for report in abstained:
        must_say.append(
            f"{report.rishi} abstained — {report.abstained}. An abstention is "
            f"a real contribution and belongs in the answer."
        )

    if unreviewed:
        must_say.append(
            "These rules were extracted from the classical texts and have not "
            "been through human review. Do not present them as verified."
        )

    must_not_say: list[str] = []
    if not window:
        must_not_say.append(
            "Do not name a date, a year or a month. No dasha window supports "
            "one, and the periods would be arithmetic rather than a prediction."
        )
    top = allowed[0].band if allowed else ""
    if top and top not in DATED_BANDS:
        must_not_say.append(
            f"The strongest evidence here is only \"{allowed[0].phrasing}\". Do "
            f"not write certainly, definitely, guaranteed, or without doubt."
        )
    if not allowed:
        must_not_say.append(
            "Nothing in the rule base cleared the evidence floor. Do not "
            "compose a reading; say the classical material is silent here."
        )

    positive = [r for r in speaking if r.score > AGREEMENT_BAND]
    negative = [r for r in speaking if r.score < -AGREEMENT_BAND]
    disagreement = ""
    if positive and negative:
        disagreement = (
            f"{', '.join(r.rishi for r in positive)} read this positively; "
            f"{', '.join(r.rishi for r in negative)} read it negatively. "
            f"Report the disagreement. Do not split the difference — an "
            f"average is a position no Rishi held."
        )

    return AnswerPlan(
        question=question,
        domain=domain,
        allowed=tuple(allowed),
        must_say=tuple(must_say),
        must_not_say=tuple(must_not_say),
        disagreement=disagreement,
        # Nothing above the floor, or a council that wholly declined. Both are
        # answers, and both are answered by saying so rather than by composing
        # something that reads like a reading.
        insufficient=not allowed or (bool(reports) and not speaking),
        unreviewed=unreviewed,
    )
