"""Which rules may be shown, and under what question.

Eight Rishis §9 states this as an absolute for the health domain: "Never diagnose a
disease, predict death as certainty, prescribe treatment, or tell the user to avoid
medical care. Present traditional interpretations with clear uncertainty."

BPHS says these things plainly and often -- "Death will certainly occur due to worms or
insects or leprosy", "his death is quite certain" -- and those verses belong in the rule
base. The constraint is on presentation, not on storage. Two separate obligations follow,
and only the second is about wording:

**Relevance.** A death rule surfacing on a question about marriage is wrong before any
question of tone arises. Measured on a real chart: "will my marriage be happy and will my
wife be healthy?" returned four rules predicting the manner of the querent's death, because
they are tagged `aarogya` and the answering Rishi owns that domain. Domain ownership is too
coarse an instrument here.

**Framing.** When such a rule IS relevant -- the querent asked about longevity -- it must
be presented as a traditional indication rather than a prediction.

So sensitive rules are gated on the question rather than dropped, and carry a flag the
prompt and the UI both act on.
"""

import re

DEATH_CLAIM = re.compile(
    r"\bdeath\b|\bdies?\b|\bdying\b|\bmaraka\b|will be killed|end of life|"
    r"longevity|life ?span|maraca",
    re.IGNORECASE,
)
"""Language that makes a rule a statement about mortality.

Deliberately broad. A false positive costs a hedge on a rule that did not need one; a false
negative puts "his death is quite certain" in front of somebody who asked about their
career.
"""

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
"""Classical texts describe bodies and sexual conduct in terms that are gratuitous when
surfaced unasked. BPHS 20.9 rates the shape of the querent's future wife's breasts; it
answered a question about her health. Faithful to the source and indefensible unbidden.
"""

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

Gated on the question's own words rather than on the answering Rishi's domains, because
domain ownership is circular here: Medhan owns health, so every Medhan question would admit
every death rule. Measured on the real corpus -- "will my marriage be happy and will my
wife be healthy?" surfaced four rules predicting the manner of the querent's death, all of
them legitimately inside the answering Rishi's remit.

The word "healthy" in a question about one's *wife* is also not a request to be told how
one will die. So `death` requires an explicit ask about death or longevity, and is not
satisfied by a general health question -- the narrower gate is the honest one, and a
querent who wants that answer can ask for it directly.
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
    """Whether this question may see this category of claim.

    The rule has not changed; the appropriateness has. A verse about the manner of death is
    admissible to someone asking how long they will live and inadmissible to someone asking
    about their marriage.
    """
    pattern = ASKED_FOR.get(sensitivity)
    return True if pattern is None else bool(pattern.search(question or ""))


def withhold_reasons(rule, question: str) -> list[str]:
    """Sensitivity categories this rule carries that this question did not ask for."""
    return [
        sensitivity
        for sensitivity in sorted(sensitivities(rule))
        if not question_admits(sensitivity, question)
    ]
