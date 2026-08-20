"""Which rules may be shown, and under what question.

Eight Rishis §9 is absolute for health: "Never diagnose a disease, predict death as
certainty, prescribe treatment, or tell the user to avoid medical care."

BPHS says these things plainly and those verses belong in the rule base — the
constraint is on presentation, not storage. Two obligations follow:

- **Relevance.** A death rule on a marriage question is wrong before tone enters it.
  Measured: "will my marriage be happy and will my wife be healthy?" returned four
  rules predicting the manner of the querent's death, all legitimately inside the
  answering Rishi's remit. Domain ownership is too coarse an instrument.
- **Framing.** When such a rule IS relevant, it is a traditional indication and not a
  prediction.

So sensitive rules are gated on the question, and carry a flag the prompt and UI act on.
"""

import re

DEATH_CLAIM = re.compile(
    r"\bdeath\b|\bdies?\b|\bdying\b|\bmaraka\b|will be killed|end of life|"
    r"longevity|life ?span|maraca",
    re.IGNORECASE,
)
"""Deliberately broad. A false positive costs a needless hedge; a false negative puts
"his death is quite certain" in front of somebody who asked about their career."""

DIAGNOSIS_CLAIM = re.compile(
    r"\bleprosy\b|\bconsumption\b|\btumour|\btumor|\bcancer\b|\bulcer|\bfever\b|"
    r"\bdisease|\billness\b|\binsan|\bleper\b|\bblind\b|\bdeaf\b|\bimpoten|"
    r"\bsterile\b|\bbarren\b|\bworms\b|\bpoison\b",
    re.IGNORECASE,
)
"""Named conditions. §9 forbids diagnosing, and a rule naming a disease reads as one."""

INTIMATE_CLAIM = re.compile(
    r"\bbreasts?\b|\bharlot\b|\bmenses\b|\bcopulat|\bsexual\b|\bprostitut|"
    r"\bbase woman\b|\badulter",
    re.IGNORECASE,
)
"""BPHS 20.9 rates the shape of the querent's future wife's breasts, and answered a
question about her health. Faithful to the source and indefensible unbidden."""

ASKED_FOR: dict[str, re.Pattern] = {
    "death": re.compile(
        r"\bdeath\b|\bdie\b|\bdying\b|\blongevity\b|how long will i live|"
        r"\blife ?span\b|\bmortality\b|when will i die",
        re.IGNORECASE,
    ),
    "diagnosis": re.compile(
        r"\bhealth\b|\bdisease\b|\bill\b|\billness\b|\bsick\b|\bmedical\b|"
        r"\bbody\b|\bvitality\b|\bailment\b|what.s wrong with me",
        re.IGNORECASE,
    ),
    "intimate": re.compile(
        r"\bsex\b|\bsexual\b|\bintimacy\b|\bintimate\b|\bfidelity\b|"
        r"\baffair\b|\bphysical relationship\b",
        re.IGNORECASE,
    ),
}
"""What the QUESTION must say for each category to be admissible.

Gated on the question's words, not the Rishi's domains: that is circular, since Medhan
owns health so every Medhan question would admit every death rule. And "healthy" asked
of one's *wife* is not a request to be told how one will die — so `death` needs an
explicit ask, which a querent who wants that answer can make directly.
"""


def sensitivities(rule) -> set[str]:
    """Categories of claim this rule makes, from its effects and its source text."""
    effects = " ".join(
        effect.get("statement", "") for effect in (getattr(rule, "effects", None) or [])
    )
    text = f"{effects} {(getattr(rule, 'source', None) or {}).get('translation', '')}"
    found = set()
    if DEATH_CLAIM.search(text):
        found.add("death")
    if DIAGNOSIS_CLAIM.search(text):
        found.add("diagnosis")
    if INTIMATE_CLAIM.search(text):
        found.add("intimate")
    return found


def question_admits(sensitivity: str, question: str) -> bool:
    """Whether this question may see this category of claim. The rule has not changed;
    the appropriateness has."""
    pattern = ASKED_FOR.get(sensitivity)
    return True if pattern is None else bool(pattern.search(question or ""))


def withhold_reasons(rule, question: str) -> list[str]:
    """Sensitivity categories this rule carries that this question did not ask for."""
    return [
        sensitivity
        for sensitivity in sorted(sensitivities(rule))
        if not question_admits(sensitivity, question)
    ]
