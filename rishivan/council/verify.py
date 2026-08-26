"""Did the prose stay inside the plan?

**A measurement, not a guardrail, and the distinction is worth being exact
about.** Once a chunk has been yielded to the transport it is on the reader's
screen. Nothing in this module can retract it, and any design that claims
otherwise is promising something the transport cannot do.

So the three pieces of the discipline are separate things:

    the gate       `narrate.build_narration_prompt` — subtractive, and the only
                   one that actually prevents anything
    the verifier   this module — tells you afterwards that the gate leaked, in
                   a form you can act on next release
    the fallback   `narrate.render_template` — a grounded answer with no model

The verifier earns its keep in two places: the trace, where a violation is
evidence for a prompt fix, and the eval harness, where it fails loudly.

**Three checks, all mechanical.** No model, no clock. A verifier that needs a
model to decide whether a model over-claimed has the same problem twice, and
one that fires on everything gets switched off - which is why
`test_a_faithful_answer_produces_no_violations` and
`test_the_template_never_violates_its_own_plan` matter more than any of the
positive cases.

**A fourth check - "did the prose assert something not in `allowed`?" - is
deliberately absent.** Deciding whether a sentence asserts an unlicensed claim
is a semantic judgement, and the only tools for it are a model (which brings
back the problem this is checking for) or keyword matching (which fires on
every paraphrase). The gate handles that case structurally instead: an
unlicensed claim has no citation to attach, and a citation that is not in the
plan is not in the prompt. Leaving the check out is better than shipping one
that is wrong in both directions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CERTAINTY = (
    "will definitely", "definitely will", "guaranteed", "certainly",
    "without doubt", "no doubt", "for sure", "undoubtedly", "assuredly",
    "is certain", "are certain",
)
"""Language no band in this system licenses.

`consistently_supported` is the strongest thing the evidence graph can say and
it is not certainty - `MAX_CONFIDENCE` is 0.97 precisely so that the arithmetic
cannot report certainty either. A prose layer that reintroduces it has undone
the ceiling.
"""

DATE = re.compile(
    r"\b(?:19|20)\d\d\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(?:19|20)\d\d\b",
    re.IGNORECASE,
)
"""A year, or a month with a year.

Deliberately narrow. "in the coming years" is not a prediction anyone can
score, and flagging it would make the verifier noise - which is the failure
mode that gets a verifier switched off.
"""


@dataclass(frozen=True, slots=True)
class Violation:
    kind: str
    detail: str
    """Specific enough to fix. "over-claimed" is a category, not a finding."""


def _licensed_dates(plan) -> list[str]:
    return [c.window for c in plan.allowed if c.window]


def _mentions(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def verify_answer(text: str, plan) -> list[Violation]:
    """What the prose said that the plan did not license."""
    if plan is None or not text.strip():
        # An empty answer is a different problem, and judging length is not
        # this module's business.
        return []

    violations: list[Violation] = []
    lower = text.lower()

    # 1. A date with nothing behind it.
    windows = _licensed_dates(plan)
    for match in DATE.finditer(text):
        found = match.group(0)
        if not any(found.lower() in w.lower() for w in windows):
            violations.append(Violation(
                kind="uncited_date",
                detail=f"The answer names {found!r}, and no dasha window in the "
                       f"plan supports a date. A period is arithmetic; a date "
                       f"needs a promise the timing engine could land in.",
            ))
            break

    # 2. Certainty language, which nothing licenses.
    for word in CERTAINTY:
        if word in lower:
            top = plan.allowed[0].phrasing if plan.allowed else "nothing"
            violations.append(Violation(
                kind="overclaimed_band",
                detail=f"The answer says {word!r}. The strongest phrasing this "
                       f"evidence licenses is \"{top}\", and no band in this "
                       f"system licenses certainty at all.",
            ))
            break

    # 3. A claim stated with its counter-evidence dropped.
    for claim in plan.allowed:
        if not claim.counter:
            continue
        stated = any(_mentions(text, c) for c in claim.citations)
        countered = any(_mentions(text, c) for c in claim.counter)
        if stated and not countered:
            violations.append(Violation(
                kind="suppressed_counter",
                detail=f"{claim.claim_id} was stated on {claim.citations[0]} "
                       f"without {', '.join(claim.counter)}, which argues "
                       f"against it. Counter-evidence belongs in the same "
                       f"breath as the finding, not in a paragraph nobody "
                       f"reads.",
            ))

    return violations
