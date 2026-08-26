"""koonji.validate - the checks that happen before a rule exists.

The compiler validates rules. These validate *extractions*, and the difference
is the passage: everything here needs the source text in hand, so none of it can
run at compile time.

Four of the checks below cost nothing and catch most of what goes wrong:

  **Verbatim quote fidelity.** Every extracted rule carries a `quoted_text` that
  must appear in the passage, verified by string match. No model call, no cost,
  and it catches most fabrication deterministically. It is the cheapest check in
  the pipeline and the one that matters most, because a fabricated citation is
  the single most damaging thing a source-grounded product can emit.

  **Approximation.** The extractor is forbidden to substitute a near-miss
  predicate for one it lacks; it must emit an ExtensionProposal instead. The
  approximation rate must be exactly zero, and anything above it means the corpus
  is being corrupted silently.

  **Reference-point discipline.** "The 7th house" may mean the 7th from the
  Lagna, the Moon, the Sun, a karaka or the Arudha. Getting it wrong produces a
  rule that fires on the wrong charts forever and never looks wrong. So a
  passage that names an alternative reference point and an extraction that does
  not are compared directly.

  **Scope inflation.** "Jupiter in Cancer in the 5th" quietly becoming "Jupiter
  in the 5th" widens a rule to charts the author never meant. Direct comparison
  misses this; checking that every entity in the condition is present in the
  passage catches it.

Reviewers are the bottleneck on this whole programme, so the last thing here is
`review_priority`, which orders the queue by impact times uncertainty. A
reviewer working it top-down spends their day where it changes outcomes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional

from pydantic import BaseModel, Field

from rishivan.koonji.registry import (
    GRAHAS,
    NEVER_USER_FACING_CLAIMS,
    _GRAHA_ALIASES,
)
from rishivan.koonji.urf import (
    ClaimConsequent,
    ExtensionProposal,
    Modality,
    Rule,
    iter_leaves,
)

#: Phrases that put a house somewhere other than the Lagna. If one of these is
#: in the passage, the extraction has to say which reference it used.
_REFERENCE_PHRASES = {
    "ref.moon": (
        "from the moon", "from moon", "from chandra", "chandra lagna",
        "from the lunar", "moon sign",
    ),
    "ref.sun": ("from the sun", "from sun", "from surya", "surya lagna"),
}

#: Reference points the vocabulary cannot express at all. These are honest
#: proposals, not failures - but they must never be quietly dropped to Lagna.
_UNSUPPORTED_REFERENCES = (
    "from the arudha", "arudha lagna", "from the karaka", "from the ascendant lord",
    "from the lagna lord", "from the atmakaraka",
)


@dataclass(slots=True)
class Finding:
    code: str
    severity: str
    message: str
    blocking: bool = False

    def __str__(self) -> str:
        return f"{self.severity.upper()} {self.code}: {self.message}"


class ExtractionFlags(BaseModel):
    """What the extractor reports about its own confidence.

    Every one of these exists because a model given no way to say "I am not
    sure" will produce something confident instead. Giving it the words is
    cheaper than catching the consequences.
    """

    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    approximated: bool = Field(
        default=False,
        description="The extractor used a near-miss predicate instead of "
        "proposing an extension. MUST be False. Anything else is "
        "silent corpus corruption.",
    )
    ambiguous_reference_point: bool = Field(
        default=False,
        description="The text does not settle what the house is counted from.",
    )
    anaphora_unresolved: bool = Field(
        default=False,
        description="'that planet', 'the same', with no antecedent in scope.",
    )
    translation_uncertainty: bool = False
    continues_previous: bool = False


class ExtractionCandidate(BaseModel):
    """One extracted rule, before anybody has decided it is a rule."""

    passage_id: str
    passage_text: str
    rule: Rule
    flags: ExtractionFlags = Field(default_factory=ExtractionFlags)
    proposals: list[ExtensionProposal] = Field(default_factory=list)
    findings: list[dict] = Field(default_factory=list)


# ==========================================================================
# Normalisation
# ==========================================================================


def _normalise(text: str) -> str:
    """Fold the differences OCR and typesetting introduce, and nothing more.

    Deliberately conservative: aggressive normalisation would make the quote
    check pass on text that is not actually in the passage, which defeats its
    entire purpose.
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


# ==========================================================================
# The checks
# ==========================================================================


def check_quote_fidelity(candidate: ExtractionCandidate) -> list[Finding]:
    """The fabrication tripwire. String matching, no model, no cost."""
    quote = candidate.rule.provenance.quoted_text
    if not quote.strip():
        return [Finding(
            "no_quote", "error",
            "extraction carries no quoted text, so nothing anchors it to the "
            "passage", blocking=True,
        )]

    passage = _normalise(candidate.passage_text)
    if _normalise(quote) in passage:
        return []

    # Try again ignoring punctuation, which OCR mangles freely. Still a string
    # match - a quote that fails even this is not in the passage.
    loose_quote = re.sub(r"[^\w\s]", "", _normalise(quote))
    loose_passage = re.sub(r"[^\w\s]", "", passage)
    if loose_quote and loose_quote in loose_passage:
        return [Finding(
            "quote_punctuation_drift", "warning",
            "quote matches only after punctuation is stripped - probably OCR, "
            "worth a glance",
        )]

    return [Finding(
        "quote_not_in_passage", "error",
        f"quoted text does not appear in {candidate.passage_id}. This is the "
        f"fabrication tripwire and it has tripped.", blocking=True,
    )]


def check_no_approximation(candidate: ExtractionCandidate) -> list[Finding]:
    """Approximation rate must be zero. Not low. Zero."""
    if not candidate.flags.approximated:
        return []
    return [Finding(
        "approximated", "error",
        "extractor substituted a near-miss predicate instead of emitting an "
        "ExtensionProposal. The proposal is the correct and expected outcome "
        "when the vocabulary falls short; the substitution is silent corpus "
        "corruption.", blocking=True,
    )]


def check_reference_point(candidate: ExtractionCandidate) -> list[Finding]:
    """The most damaging extraction error in Jyotish, checked directly."""
    passage = _normalise(candidate.passage_text)
    out: list[Finding] = []

    used = {
        str(call.args.get("reference", ""))
        for call in iter_leaves(candidate.rule.antecedent.expr)
        if call.predicate == "occupies_bhava_from"
    }
    implicit_lagna = any(
        call.predicate == "occupies_bhava"
        for call in iter_leaves(candidate.rule.antecedent.expr)
    )

    for reference, phrases in _REFERENCE_PHRASES.items():
        if any(p in passage for p in phrases) and reference not in used:
            out.append(Finding(
                "reference_point_dropped", "error",
                f"the passage counts from {reference.split('.')[1]}, and the "
                f"extraction does not say so"
                + (" - it was stored as from-Lagna" if implicit_lagna else ""),
                blocking=True,
            ))

    for phrase in _UNSUPPORTED_REFERENCES:
        if phrase in passage and not candidate.proposals:
            out.append(Finding(
                "reference_point_unsupported", "error",
                f"the passage counts from something the vocabulary cannot "
                f"express ({phrase!r}) and no ExtensionProposal was emitted",
                blocking=True,
            ))

    if candidate.flags.ambiguous_reference_point:
        out.append(Finding(
            "reference_point_ambiguous", "warning",
            "the extractor could not settle the reference point - route to a "
            "reviewer rather than defaulting to Lagna",
        ))
    return out


def check_scope_inflation(candidate: ExtractionCandidate) -> list[Finding]:
    """Every graha the condition names should be named in the passage.

    Catches the quiet widening that direct comparison misses: "Jupiter in Cancer
    in the 5th" becoming "Jupiter in the 5th" is not a paraphrase, it is a rule
    that now fires on twelve times as many charts.
    """
    passage = _normalise(candidate.passage_text)
    named = {
        alias for alias, canonical in _GRAHA_ALIASES.items() if alias in passage
    }
    present = {f"graha.{_GRAHA_ALIASES[a]}" for a in named}

    out: list[Finding] = []
    for call in iter_leaves(candidate.rule.antecedent.expr):
        for value in call.args.values():
            value = str(value)
            if not value.startswith("graha."):
                continue
            if value.split(".")[1] not in GRAHAS:
                continue
            if present and value not in present:
                out.append(Finding(
                    "scope_inflation", "warning",
                    f"the condition names {value}, which does not appear in the "
                    f"passage - check the extraction did not widen or narrow it",
                ))
    return out


def check_restriction(candidate: ExtractionCandidate) -> list[Finding]:
    """Longevity and death timing are restricted at extraction, not at output.

    A filter you cannot accidentally remove beats one you have to remember to
    apply, and Brihat Jataka's Balarishta chapters plus Prasna Marga X-XI are
    hundreds of rules of exactly this kind.
    """
    consequent = candidate.rule.consequent
    if not isinstance(consequent, ClaimConsequent):
        return []
    if consequent.claim_id not in NEVER_USER_FACING_CLAIMS:
        return []
    if candidate.rule.qualifiers.restriction.value == "never_user_facing":
        return []
    return [Finding(
        "restriction_missing", "error",
        f"claim {consequent.claim_id!r} must be marked never_user_facing at "
        f"extraction; an output filter is too late and too easy to lose",
        blocking=True,
    )]


def check_proposals(candidate: ExtractionCandidate) -> list[Finding]:
    """A proposal is a correct outcome, and it still has to be well formed."""
    out: list[Finding] = []
    for proposal in candidate.proposals:
        if not proposal.why_insufficient.strip():
            out.append(Finding(
                "proposal_unexplained", "error",
                f"proposal {proposal.proposed_id!r} has no rationale - that "
                f"field is the only thing a reviewer actually reads",
                blocking=True,
            ))
        if not proposal.evidence_passages:
            out.append(Finding(
                "proposal_unevidenced", "error",
                f"proposal {proposal.proposed_id!r} cites no passage",
                blocking=True,
            ))
    return out


def validate_candidate(candidate: ExtractionCandidate) -> list[Finding]:
    """Every deterministic check. No model call anywhere in here."""
    return (
        check_quote_fidelity(candidate)
        + check_no_approximation(candidate)
        + check_reference_point(candidate)
        + check_scope_inflation(candidate)
        + check_restriction(candidate)
        + check_proposals(candidate)
    )


def is_blocked(findings: Iterable[Finding]) -> bool:
    return any(f.blocking for f in findings)


# ==========================================================================
# Review prioritisation
# ==========================================================================

#: Domains where a wrong rule does the most harm, so they are read first.
_HIGH_STAKES = ("domain.health", "domain.longevity")


def review_priority(candidate: ExtractionCandidate, findings: Iterable[Finding] = ()) -> float:
    """impact x uncertainty.

    Reviewers are the bottleneck on the entire programme - roughly 100 to 150
    reviewer-days for two thousand rules - so the order of this queue is a
    schedule decision, not a nicety. A reviewer working it top-down spends their
    day where it changes outcomes.
    """
    flags = candidate.flags
    uncertainty = 1.0 - flags.confidence
    if candidate.proposals:
        uncertainty += 0.40
    if flags.ambiguous_reference_point:
        uncertainty += 0.35
    if flags.anaphora_unresolved:
        uncertainty += 0.25
    if flags.translation_uncertainty:
        uncertainty += 0.20

    impact = 1.0
    if candidate.rule.qualifiers.modality in (Modality.CANCEL, Modality.EXCEPT):
        impact *= 1.6  # cancellations drive headline claims
    if any(d in candidate.rule.domains for d in _HIGH_STAKES):
        impact *= 2.0

    score = impact * uncertainty
    # Anything blocked jumps the queue regardless of its score: it is not going
    # to be fixed by waiting.
    if is_blocked(findings):
        score += 100.0
    return round(score, 4)


def review_queue(
    candidates: Iterable[ExtractionCandidate],
) -> list[tuple[float, ExtractionCandidate, list[Finding]]]:
    scored = []
    for candidate in candidates:
        findings = validate_candidate(candidate)
        scored.append((review_priority(candidate, findings), candidate, findings))
    return sorted(scored, key=lambda row: -row[0])
