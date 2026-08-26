"""What the router emits, and the gates it has to pass before any Koonji work.

`engine.read()` has always taken `domains`, `schools` and `statuses`. Nothing
produced them. The CLI passed `--domain` by hand and the app passed nothing at
all, which means every question was answered against the whole corpus. This
module is the missing half: the shape a question is parsed into, and the
deterministic checks that run on it *before* a chart is computed.

The shape follows the URF's own discipline, for the same reason:

    CLOSED envelope (fixed, versioned)   OPEN payload (grows, no schema change)
    ----------------------------------   --------------------------------------
    spec_version, raw, language          flag registry
    turn_type                            mode payloads
    mode          <- discriminator       sub-question types
    subject_refs                         domains (registry symbols)
    required_inputs / missing_inputs
    routing, flags[], answer_shape

A flat schema with `contains_decision_request: bool` on it invites
`contains_medical`, `contains_third_party`, `contains_two_charts`, forever, and
every one of them is a migration of every stored spec. Flags are registry rows
instead.

Two fields carry most of the weight, and both are easy to leave out:

  `turn_type`      "why?" is not a new question. A large slice of real traffic
                   is follow-up, correction or small talk, and running the full
                   pipeline on those is waste and - worse - a consistency risk,
                   because a recomputed answer can disagree with the one it is
                   supposed to be elaborating.

  `missing_inputs` A compatibility question without a partner chart is a wrong
                   answer with a full audit trail. Resolve it before fan-out,
                   never after.

Nothing here calls a language model, and nothing here reads a chart. Parsing is
in `router.py`; this module only defines the shape and the gates.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

SPEC_VERSION = "1.0.0"


# ==========================================================================
# CLOSED - turn type. Orthogonal to mode: a follow-up can be about any mode.
# ==========================================================================


class TurnType(str, Enum):
    NEW_QUESTION = "new_question"
    FOLLOWUP = "followup"        # "why?", "tell me more", "which house?"
    DRILLDOWN = "drilldown"      # "show me the verse for that"
    CORRECTION = "correction"    # "my birth time is 4:15, not 4:45"
    CHALLENGE = "challenge"      # "that didn't happen" -> ledger reconciliation
    META = "meta"                # "how does this work?"
    SOCIAL = "social"            # greeting, thanks
    OUT_OF_SCOPE = "out_of_scope"


NON_ANALYTIC_TURNS = frozenset({
    TurnType.META,
    TurnType.SOCIAL,
    TurnType.OUT_OF_SCOPE,
    # Served from the stored trace of the turn being drilled into, never
    # recomputed. Recomputing risks answering with a different bundle than the
    # one that produced the claim the user is pointing at.
    TurnType.DRILLDOWN,
})
"""Turn types that skip the engine entirely."""


# ==========================================================================
# CLOSED - the mode discriminator. Each mode needs genuinely different inputs.
# ==========================================================================


class Mode(str, Enum):
    NATAL_PREDICTIVE = "natal_predictive"    # "will I...", "when will I..."
    NATAL_DESCRIPTIVE = "natal_descriptive"  # "what am I like" - no timing
    TIMING_ONLY = "timing_only"              # "what's my next good period"
    COMPATIBILITY = "compatibility"          # TWO charts
    PRASHNA = "prashna"                      # chart from the moment of asking
    MUHURTA = "muhurta"                      # choose a time from candidates
    KNOWLEDGE = "knowledge"                  # "what does BPHS say about..."
    MODALITY = "modality"                    # numerology, palm, face
    RECTIFICATION = "rectification"          # uncertain birth time
    LIFE_MAP = "life_map"                    # every domain, batch
    UNSUPPORTED = "unsupported"              # honestly out of scope


SERVABLE_MODES = frozenset({
    Mode.NATAL_PREDICTIVE,
    Mode.NATAL_DESCRIPTIVE,
    Mode.TIMING_ONLY,
    Mode.LIFE_MAP,
})
"""Modes the compiled corpus can actually answer today.

This is a statement about the rules we hold, not about the frame. Every rule in
`rules/parashari` is a natal Parashari rule; there is no horary corpus, no
muhurta corpus and no synastry corpus. Routing a compatibility question into
the natal engine would produce firings - they would just be answering a
different question than the one asked, with a citation attached to make it look
considered. Better to say the mode is unsupported.

Adding a school moves a mode into this set. Nothing else changes.
"""


# ==========================================================================
# OPEN - the flag registry. Not booleans on the model.
#
# Adding `safety.pregnancy` is a row here plus a policy decision. It does not
# touch this file's schema, does not invalidate a stored spec, and does not
# require the router to relearn an output shape.
# ==========================================================================


class Flag(BaseModel):
    flag_id: str = Field(description="Registry entry, e.g. 'safety.decision_request'.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_span: Optional[str] = Field(
        default=None, description="The substring that triggered it. Auditable."
    )


SEED_FLAG_REGISTRY: frozenset[str] = frozenset({
    # -- safety: each maps to a policy row, not to a branch in code --
    "safety.decision_request",   # asking to be told what to do
    "safety.third_party",        # about a non-consenting, identifiable person
    "safety.medical",
    "safety.legal",
    "safety.financial_specific",
    "safety.mortality",
    "safety.distress",           # routes out of astrology entirely
    "safety.minor_subject",
    # -- handling: affects tone and length, never the evidence --
    "handling.emotional_charge",
    "handling.skeptical_framing",
    "handling.urgency",
    "handling.requests_brevity",
    # -- structure --
    "structure.multi_part",
    "structure.hypothetical",
    "structure.comparative",
})

REFUSING_FLAGS: frozenset[str] = frozenset({
    "safety.distress",
    "safety.medical",
    "safety.mortality",
})
"""Flags that stop the engine rather than shape its answer.

Deliberately short. A flag that merely makes an answer awkward belongs in the
narrative layer's problem, not here - the engine's job is to be right, and
refusing things it can answer correctly is its own kind of failure.
`safety.mortality` is on the list even though `domain.longevity` rules exist and
fire: the corpus can compute an ayurdaya, and telling a person their death year
is not a thing this product does.
"""


# ==========================================================================
# CLOSED - subjects and inputs
# ==========================================================================


class SubjectRef(BaseModel):
    """Whose chart. A user has several: self, spouse, child, a friend."""

    role: Literal["self", "partner", "child", "parent", "other"] = "self"
    profile_id: Optional[str] = None
    label: Optional[str] = Field(default=None, description="'my son', 'my wife'")
    consent_required: bool = Field(
        default=False,
        description="True for a non-self identifiable person. Gates the answer.",
    )


class InputKind(str, Enum):
    BIRTH_PROFILE = "birth_profile"
    PARTNER_PROFILE = "partner_profile"
    QUERY_MOMENT = "query_moment"          # Prashna: timestamp + location
    CANDIDATE_WINDOW = "candidate_window"  # Muhurta
    LIFE_EVENTS = "life_events"            # rectification
    NAME_STRING = "name_string"            # numerology
    PALM_IMAGE = "palm_image"
    FACE_IMAGE = "face_image"


class MissingInput(BaseModel):
    kind: InputKind
    blocking: bool = Field(
        default=True,
        description="True = cannot answer at all. False = the answer is narrower.",
    )
    prompt: str = Field(description="What to ask the user, in their language.")


# ==========================================================================
# CLOSED - routing and answer shape
# ==========================================================================


class Routing(BaseModel):
    """Which rules this question may reach. This is the filter, stated once.

    `domains` and `schools` are registry symbols - `domain.wealth`,
    `school.parashari` - and go straight to `RuleIndex.query`. They are not the
    Rishi personas; a Rishi is a voice layered on top of a reading, and mapping
    one to the other here would put a presentation concern inside the retrieval
    filter.
    """

    domains: list[str] = Field(default_factory=list)
    schools: list[str] = Field(default_factory=lambda: ["school.parashari"])
    min_domain_weight: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Ignore a rule's domain tag if it is weighted below this. A rule "
            "tagged `domain.wealth: 0.95, domain.career: 0.35` is a wealth rule "
            "that touches career; it should not lead a career reading."
        ),
    )
    reason: str = Field(
        default="",
        description="Which phrases produced these domains. Logged, and read "
        "when a routing decision looks wrong.",
    )
    matched: dict[str, list[str]] = Field(
        default_factory=dict, description="domain -> the phrases that matched it"
    )


class AnswerShape(BaseModel):
    format: Literal[
        "prose", "prose_with_timeline", "comparison", "list", "report", "single_fact"
    ] = "prose"
    length: Literal["brief", "standard", "deep"] = "standard"
    complexity: Literal["QUICK", "STANDARD", "DEEP", "LIFE_MAP"] = "STANDARD"
    include_sources: bool = True


# ==========================================================================
# OPEN - mode payloads. Each carries only what its own mode needs.
# ==========================================================================


class SubQuestion(BaseModel):
    id: str
    domain: str = Field(description="Registry symbol, e.g. 'domain.career'.")
    raw_span: Optional[str] = Field(
        default=None, description="Which part of the message produced this."
    )


class TimeScope(BaseModel):
    """Resolved to dates at parse time, never left relative.

    "next year" has to become a start and an end here, once. Left as a phrase,
    every downstream component resolves it against its own clock and they
    disagree - and the disagreement surfaces months later as a claim whose
    window nobody can reproduce.
    """

    start: str
    end: str
    granularity: Literal["month", "quarter", "year"] = "quarter"
    user_phrase: Optional[str] = None


class NatalPredictivePayload(BaseModel):
    mode: Literal[Mode.NATAL_PREDICTIVE] = Mode.NATAL_PREDICTIVE
    sub_questions: list[SubQuestion] = Field(default_factory=list)
    time_scope: Optional[TimeScope] = None


class NatalDescriptivePayload(BaseModel):
    mode: Literal[Mode.NATAL_DESCRIPTIVE] = Mode.NATAL_DESCRIPTIVE
    sub_questions: list[SubQuestion] = Field(default_factory=list)


class TimingOnlyPayload(BaseModel):
    mode: Literal[Mode.TIMING_ONLY] = Mode.TIMING_ONLY
    of_what: str = ""
    time_scope: Optional[TimeScope] = None
    systems: list[str] = Field(default_factory=lambda: ["dasha.vimshottari"])


class CompatibilityPayload(BaseModel):
    mode: Literal[Mode.COMPATIBILITY] = Mode.COMPATIBILITY
    subject_a: SubjectRef = Field(default_factory=SubjectRef)
    subject_b: SubjectRef = Field(
        default_factory=lambda: SubjectRef(role="partner", consent_required=True)
    )


class PrashnaPayload(BaseModel):
    mode: Literal[Mode.PRASHNA] = Mode.PRASHNA
    question_text: str = ""
    observables_available: list[str] = Field(
        default_factory=list,
        description=(
            "What the product can actually observe. A chat app cannot see the "
            "querent's active nostril or who walked into the room. A rule "
            "requiring an unavailable observable is withheld, and the model is "
            "never permitted to invent the observation."
        ),
    )


class MuhurtaPayload(BaseModel):
    mode: Literal[Mode.MUHURTA] = Mode.MUHURTA
    activity: str = ""
    time_scope: Optional[TimeScope] = None


class KnowledgePayload(BaseModel):
    """No chart. "What does BPHS say about the 7th lord in the 12th?"

    Passage retrieval and rule lookup, not prediction. It skips the engine
    because there is no chart to compile facts from - the answer is about the
    corpus, not about a person.
    """

    mode: Literal[Mode.KNOWLEDGE] = Mode.KNOWLEDGE
    topic: str = ""
    entities: list[str] = Field(default_factory=list)


class ModalityPayload(BaseModel):
    mode: Literal[Mode.MODALITY] = Mode.MODALITY
    modality: Literal["numerology", "palmistry", "face", "vastu"] = "numerology"
    about: str = ""


class RectificationPayload(BaseModel):
    mode: Literal[Mode.RECTIFICATION] = Mode.RECTIFICATION
    uncertainty_minutes: int = 60


class LifeMapPayload(BaseModel):
    mode: Literal[Mode.LIFE_MAP] = Mode.LIFE_MAP
    emphasis: list[str] = Field(default_factory=list)


class UnsupportedPayload(BaseModel):
    mode: Literal[Mode.UNSUPPORTED] = Mode.UNSUPPORTED
    reason: str = ""
    nearest_supported: Optional[Mode] = None


Payload = Annotated[
    Union[
        NatalPredictivePayload,
        NatalDescriptivePayload,
        TimingOnlyPayload,
        CompatibilityPayload,
        PrashnaPayload,
        MuhurtaPayload,
        KnowledgePayload,
        ModalityPayload,
        RectificationPayload,
        LifeMapPayload,
        UnsupportedPayload,
    ],
    Field(discriminator="mode"),
]


# ==========================================================================
# CLOSED - the envelope
# ==========================================================================


class QuestionSpec(BaseModel):
    """One parsed question. Everything the engine needs to know before it runs."""

    spec_version: str = SPEC_VERSION
    raw: str
    language: str = "en"

    turn_type: TurnType = TurnType.NEW_QUESTION
    mode: Mode = Mode.NATAL_PREDICTIVE
    payload: Payload = Field(default_factory=NatalPredictivePayload)

    subject_refs: list[SubjectRef] = Field(default_factory=lambda: [SubjectRef()])
    required_inputs: list[InputKind] = Field(default_factory=list)
    missing_inputs: list[MissingInput] = Field(default_factory=list)

    routing: Routing = Field(default_factory=Routing)
    flags: list[Flag] = Field(default_factory=list)
    answer_shape: AnswerShape = Field(default_factory=AnswerShape)

    refers_to_claims: list[str] = Field(
        default_factory=list,
        description="Prior claim ids this turn is about. Drives the consistency "
        "check against the ledger.",
    )
    parse_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    ambiguity_note: Optional[str] = None

    # -- the gates, in the order they are evaluated -----------------------

    def is_blocked(self) -> bool:
        """A required input is absent. Ask for it; do not answer around it."""
        return any(m.blocking for m in self.missing_inputs)

    def needs_clarification(self) -> bool:
        return self.parse_confidence < CLARIFY_BELOW or self.is_blocked()

    def refused(self) -> Optional[str]:
        """The flag that stops this turn, if any."""
        for flag in self.flags:
            if flag.flag_id in REFUSING_FLAGS:
                return flag.flag_id
        return None

    def skips_koonji(self) -> bool:
        """True when there is no deterministic reading to compute.

        Not the same as "we cannot answer". A META turn is answered from the
        product's own documentation and a KNOWLEDGE turn from the corpus; both
        are perfectly good answers that simply do not involve firing rules on a
        chart.
        """
        return (
            self.turn_type in NON_ANALYTIC_TURNS
            or self.mode not in SERVABLE_MODES
        )

    def has_flag(self, flag_id: str) -> bool:
        return any(f.flag_id == flag_id for f in self.flags)


CLARIFY_BELOW = 0.55
"""Below this the parse is a guess, and answering a guess confidently is the
single most expensive mistake this layer can make. Ask instead."""


# ==========================================================================
# Required inputs per mode - derived, never asked of a model.
#
# A router is unreliable at remembering that COMPATIBILITY needs two profiles.
# A lookup table is not. Derive deterministically, then diff against what the
# caller actually holds.
# ==========================================================================

REQUIRED_INPUTS: dict[Mode, tuple[InputKind, ...]] = {
    Mode.NATAL_PREDICTIVE: (InputKind.BIRTH_PROFILE,),
    Mode.NATAL_DESCRIPTIVE: (InputKind.BIRTH_PROFILE,),
    Mode.TIMING_ONLY: (InputKind.BIRTH_PROFILE,),
    Mode.LIFE_MAP: (InputKind.BIRTH_PROFILE,),
    Mode.COMPATIBILITY: (InputKind.BIRTH_PROFILE, InputKind.PARTNER_PROFILE),
    Mode.PRASHNA: (InputKind.QUERY_MOMENT,),
    Mode.MUHURTA: (InputKind.CANDIDATE_WINDOW,),
    Mode.RECTIFICATION: (InputKind.BIRTH_PROFILE, InputKind.LIFE_EVENTS),
    Mode.KNOWLEDGE: (),
    Mode.MODALITY: (),
    Mode.UNSUPPORTED: (),
}

MODALITY_INPUTS: dict[str, InputKind] = {
    "numerology": InputKind.NAME_STRING,
    "palmistry": InputKind.PALM_IMAGE,
    "face": InputKind.FACE_IMAGE,
}

_PROMPTS: dict[InputKind, str] = {
    InputKind.BIRTH_PROFILE: "I'll need your birth date, time and place.",
    InputKind.PARTNER_PROFILE: "I'll need their birth date, time and place too.",
    InputKind.QUERY_MOMENT: "I'll use the moment you asked.",
    InputKind.CANDIDATE_WINDOW: "Which date range should I look at?",
    InputKind.LIFE_EVENTS: "Rectification needs a few dated life events.",
    InputKind.NAME_STRING: "I'll need the name exactly as it is written.",
    InputKind.PALM_IMAGE: "Send a clear photo of your palm.",
    InputKind.FACE_IMAGE: "Send a clear, front-facing photo.",
}


def required_inputs(spec: QuestionSpec) -> list[InputKind]:
    kinds = list(REQUIRED_INPUTS.get(spec.mode, ()))
    if isinstance(spec.payload, ModalityPayload):
        extra = MODALITY_INPUTS.get(spec.payload.modality)
        if extra is not None:
            kinds.append(extra)
    return kinds


def resolve_missing(
    spec: QuestionSpec, available: set[InputKind]
) -> list[MissingInput]:
    """Deterministic, and run immediately after parse.

    `QUERY_MOMENT` is never missing - the moment of asking is always known - but
    it stays in the table so that the requirement is stated where every other
    requirement is stated, rather than being an unwritten exception.
    """
    return [
        MissingInput(kind=kind, blocking=True, prompt=_PROMPTS.get(kind, f"I need {kind.value}."))
        for kind in required_inputs(spec)
        if kind not in available and kind is not InputKind.QUERY_MOMENT
    ]
