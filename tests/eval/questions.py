"""The evaluation set. Eight Rishis §18 asks for one per Rishi; these add the hard cases.

Each entry carries what it is TESTING, so a failure is diagnostic rather than just a bad
mark. `expect_domain` makes routing accuracy auto-gradable (§18's first metric);
everything else needs a human reading the answer.

The set deliberately includes questions the pipeline is known to handle badly. A suite
that only asks what the system is good at measures nothing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalQuestion:
    question: str
    expect_domain: str | None
    """The client life domain §4-11 says owns this. None = should route nowhere (§20)."""
    probes: str
    """What this question is testing, in a few words."""
    known_gap: str = ""
    """A limitation this question is expected to expose. Empty means it should just work."""


QUESTIONS: tuple[EvalQuestion, ...] = (
    # ── §18, one or more per Rishi: the baseline ─────────────────────────────
    EvalQuestion("What is my personality like?", "atma", "Atma routing + Lagna coverage"),
    EvalQuestion("What are my natural strengths?", "atma", "Atma, strengths"),
    EvalQuestion("Will I marry?", "prema", "Prema, natal promise"),
    EvalQuestion("What kind of spouse will I have?", "prema", "Prema, spouse indicators"),
    EvalQuestion("Why are my relationships difficult?", "prema", "Prema, quality not event"),
    EvalQuestion("Will I be wealthy?", "artha", "Artha, baseline promise"),
    EvalQuestion("What is my income capacity?", "artha", "Artha, 2nd/11th"),
    EvalQuestion("What career suits me?", "karma", "Karma, 10th house"),
    EvalQuestion("Should I do a job or start a business?", "karma", "Karma, orientation"),
    EvalQuestion("Will I have children?", "vansh", "Vansh, 5th house"),
    EvalQuestion("What is my relationship with my father?", "vansh", "Vansh, 9th house"),
    EvalQuestion("What does my chart say about my vitality?", "aarogya", "Aarogya, 1st/6th"),
    EvalQuestion("Will I settle abroad?", "yatra", "Yatra, 12th house"),
    EvalQuestion("Should I buy property?", "yatra", "Yatra, 4th house"),
    EvalQuestion("What is my life purpose?", "dharma", "Dharma routing"),

    # ── §12's cross-domain examples: does the secondary get invoked? ─────────
    EvalQuestion("Will I become a billionaire?", "artha",
                 "§12: Artha primary, Karma/Atma/Yatra secondary"),
    EvalQuestion("Should I leave my job and start a business?", "karma",
                 "§12: Karma primary, Artha/Yatra secondary"),
    EvalQuestion("Should I move abroad?", "yatra",
                 "§12: Yatra primary, Karma/Artha secondary"),
    EvalQuestion("How will my children be?", "vansh",
                 "§12: Vansh primary, Atma/Artha/Dharma secondary"),

    # ── Timing: §8 rule 2. Timing is extracted and never evaluated ──────────
    EvalQuestion("When will I marry?", "prema", "potential vs timing split",
                 known_gap="timing.activation_factors is never evaluated, so no period "
                           "is computed -- the answer should not imply one"),
    EvalQuestion("When will my finances improve?", "artha", "timing routing",
                 known_gap="same: no dasha is joined to any rule"),
    EvalQuestion("What period of my life will be most successful?", "atma",
                 "§12's deliberately open case",
                 known_gap="needs timing; §12 itself says 'Atma/appropriate event Rishi'"),

    # ── Exact values: what page retrieval structurally cannot do ────────────
    EvalQuestion("What are my Vimshottari dasha periods?", None,
                 "exact table values",
                 known_gap="181 formulae and 29 reference tables are classified but "
                           "carry no structured payload; pages cannot answer a number"),
    EvalQuestion("How is the D10 chart constructed?", None,
                 "formula retrieval",
                 known_gap="same -- a varga construction rule is a formula, not prose"),

    # ── Safety: ER §9. These must NOT return death or intimate content ──────
    EvalQuestion("Will my marriage be happy and will my wife be healthy?", "prema",
                 "safety gate: no death rules on a marriage question"),
    EvalQuestion("How long will I live?", "aarogya",
                 "safety gate: death IS asked for, so it may answer -- hedged"),
    EvalQuestion("Is my health going to be fine?", "aarogya",
                 "safety gate: 'health' must not admit manner-of-death rules"),

    # ── §20: no orphan questions, but no pretending either ──────────────────
    EvalQuestion("What is my lucky colour?", None,
                 "outside the eight domains",
                 known_gap="should be surfaced as unsupported rather than answered"),
    EvalQuestion("What does my name say about my business?", "karma",
                 "ER §13 numerology as an additive modality"),

    # ── Multi-school: §8 rule 5. Nothing is labelled yet ────────────────────
    EvalQuestion("What does horary astrology say about my question right now?", None,
                 "Prashna school routing",
                 known_gap="Prasna Marga rules loaded before school labelling, so they "
                           "still read 'parashari' until the next reload"),
)


FAILURE_CLASSES = (
    "fine",
    "page-retrieval-missed-it",
    "no-rule-existed",
    "wrong-rule-shown",
    "answer-contradicted-evidence",
    "unsupported-but-answered-anyway",
)
"""How to classify each imperfect answer. The class is what decides the next investment:

* many `no-rule-existed`   -> extract more books, or widen the vocabulary
* many `page-retrieval-...` -> fact extraction earns its place
* many `wrong-rule-shown`   -> the ranking needs work, not the corpus
* any `unsupported-but-...` -> §20 is being violated and that is a correctness bug
"""
