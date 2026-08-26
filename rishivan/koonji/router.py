"""Raw question -> QuestionSpec -> the retrieval filter, deterministically.

This is the stage the deep dive puts a fine-tuned model on. It is a keyword
router here, and that is a deliberate choice rather than a placeholder:

  * It is in the serving path, and this package's rule is that nothing in the
    serving path calls a language model. A router that sometimes returns
    `domain.progeny` for a career question is a router that sometimes drops the
    career rules, and the drop is invisible - you cannot see the absence of a
    rule in an answer that reads fluently.

  * The output is auditable. `routing.matched` names the exact phrases that
    produced each domain, so a routing complaint is a one-line diff against a
    table rather than an argument about a model's behaviour.

  * It is a baseline a model has to beat on labelled traffic before it replaces
    anything. `parse(...)` is the interface; swapping the body for a classifier
    later changes nothing downstream.

The one thing it must never do is guess quietly. When no phrase matches,
routing returns no domains at all, and that means *unfiltered* - the whole
corpus is considered. Filtering is an optimisation and a relevance aid; it is
never allowed to become a silent recall failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from rishivan.koonji.question import (
    CLARIFY_BELOW,
    SEED_FLAG_REGISTRY,
    AnswerShape,
    CompatibilityPayload,
    Flag,
    InputKind,
    KnowledgePayload,
    LifeMapPayload,
    Mode,
    ModalityPayload,
    MuhurtaPayload,
    NatalDescriptivePayload,
    NatalPredictivePayload,
    PrashnaPayload,
    QuestionSpec,
    RectificationPayload,
    Routing,
    SubQuestion,
    SubjectRef,
    TimeScope,
    TimingOnlyPayload,
    TurnType,
    UnsupportedPayload,
)

# ==========================================================================
# Domain vocabulary
#
# Keyed on the registry's own `domain.*` symbols, not on the eight Rishis.
# `council/routing.py` already routes to Rishis for the RAG path; that table
# cannot be reused here because a Rishi is a voice and a domain is a filter, and
# the two are not the same partition - the client's VANSH covers both children
# and parents, which are `domain.progeny` and `domain.status` to the corpus.
#
# The engine does not import from `council`, and should not. It would make the
# retrieval filter depend on a presentation layer.
# ==========================================================================

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "domain.wealth": (
        "money", "wealth", "rich", "riches", "wealthy", "income", "earnings",
        "savings", "financial", "finances", "finance", "fortune", "prosperity",
        "debt", "loan", "loans", "poverty", "gains", "profit", "profits",
        "inheritance", "windfall", "affluent", "become rich", "financially",
    ),
    "domain.career": (
        "career", "job", "jobs", "work", "profession", "professional",
        "business", "employment", "employer", "promotion", "promoted",
        "workplace", "occupation", "livelihood", "vocation", "startup",
        "resign", "quit my job", "change jobs", "new job", "office",
    ),
    "domain.status": (
        "status", "reputation", "fame", "famous", "recognition", "authority",
        "position", "rank", "standing", "respected", "honour", "honor",
        "father", "my dad", "father's", "paternal",
    ),
    "domain.relationship": (
        "marriage", "married", "marry", "spouse", "wife", "husband", "partner",
        "relationship", "love", "romance", "romantic", "divorce", "separation",
        "engagement", "wedding", "girlfriend", "boyfriend", "compatibility",
        "match", "matchmaking", "kundali matching", "get married",
    ),
    "domain.progeny": (
        "child", "children", "kids", "son", "daughter", "pregnancy", "pregnant",
        "conceive", "conception", "childbirth", "fertility", "progeny",
        "offspring", "become a parent", "have a child",
    ),
    "domain.education": (
        "education", "study", "studies", "studying", "exam", "exams", "degree",
        "college", "university", "school", "learning", "scholarship",
        "academic", "phd", "research", "student",
    ),
    "domain.health": (
        "health", "illness", "ill", "disease", "sick", "sickness", "surgery",
        "hospital", "recovery", "chronic", "ailment", "wellbeing", "immunity",
        "healthy",
    ),
    "domain.longevity": (
        "longevity", "lifespan", "life span", "how long will i live",
        "ayurdaya", "long life", "die", "death", "mortality",
    ),
    "domain.travel": (
        "travel", "abroad", "foreign", "overseas", "relocate", "relocation",
        "migration", "immigration", "visa", "settle abroad", "move abroad",
        "journey", "pilgrimage",
    ),
    "domain.property": (
        "property", "house", "home", "land", "real estate", "apartment",
        "flat", "vehicle", "car", "buy a house", "own a home", "plot",
    ),
    "domain.temperament": (
        "personality", "temperament", "nature", "character", "my traits",
        "who am i", "what am i like", "disposition", "mindset", "behaviour",
        "behavior", "strengths", "weaknesses",
    ),
    "domain.spiritual": (
        "spiritual", "spirituality", "moksha", "liberation", "dharma",
        "meditation", "guru", "devotion", "sadhana", "purpose", "life purpose",
        "enlightenment", "renunciation",
    ),
}

GENERIC_PHRASES: frozenset[str] = frozenset({
    # Owned by no domain in particular. "house" is the worst offender - it is
    # the property sense here and the bhava sense everywhere else in the corpus.
    "house", "home", "work", "match", "nature", "position", "purpose",
    "partner", "school", "research", "match", "money",
})

GENERIC_WEIGHT = 0.5
"""Below any specific single-word match, above nothing. Same reasoning as
`council.routing`: demoting keeps the phrase routable without letting it win."""

MAX_DOMAINS = 3
"""A reading that reaches into every domain is not a reading, it is a horoscope
column. Three is the number of domains one question can genuinely be about."""

INCIDENTAL_DOMAIN_WEIGHT = 0.5
"""Default `min_domain_weight` for a domain-filtered read.

A rule tagged `domain.wealth: 0.95, domain.career: 0.35` is a wealth rule that
happens to touch career. Letting the 0.35 tag pull it into a career reading is
how a corpus's strongest wealth rules end up as a career answer's headline
evidence. The threshold does not delete the rule - it stops it being retrieved
*as* a career rule.
"""


# ==========================================================================
# Turn type, mode and flag markers
# ==========================================================================

_SOCIAL = re.compile(
    # Anchored at both ends. "thanks" is social; "thanks, but when will I
    # marry?" is a question with a courtesy on the front, and matching the
    # greeting alone would drop the question.
    r"^\s*(hi|hello|hey|namaste|namaskar|thanks|thank you|thankyou|ok|okay|"
    r"good (morning|afternoon|evening|night)|bye|goodbye|see you)\b"
    r"(\s+(there|again|friend|so much|a lot|everyone))?[\s!.,]*$",
    re.IGNORECASE,
)
_META = re.compile(
    r"\bhow (does|do) (this|you|it) work\b|\bwhat can you do\b|\bwho are you\b|"
    r"\bare you (an? )?(ai|bot|human)\b|\bhow accurate\b|\bwhat is rishivan\b",
    re.IGNORECASE,
)
_FOLLOWUP = re.compile(
    r"^\s*(why|why\?|why is that|how so|tell me more|go on|and\?|explain|"
    r"say more|elaborate|what else)\b",
    re.IGNORECASE,
)
_DRILLDOWN = re.compile(
    r"\b(which|what) (verse|shloka|sutra|source|book|rule|chapter)\b|"
    r"\bshow me the (source|verse|citation|rule)|\bcite\b|\bwhere does it say\b",
    re.IGNORECASE,
)
_CORRECTION = re.compile(
    r"\b(actually|correction|i meant|not \d{1,2}[:.]\d{2}|my birth (time|date) is"
    r"|it'?s actually)\b",
    re.IGNORECASE,
)
_CHALLENGE = re.compile(
    r"\b(that (didn'?t|did not) happen|you were wrong|that'?s wrong|"
    r"nothing happened|it never happened|you said .* but)\b",
    re.IGNORECASE,
)

TIMING_MARKERS = re.compile(
    r"\bwhen\b|\bwhat time\b|\bwhich year\b|\bwhich period\b|\bwhat period\b|"
    r"\bhow soon\b|\bat what age\b|\btiming\b|\bdasha\b|\bmahadasha\b|"
    r"\bantardasha\b|\bbhukti\b|\btransit\b|\bperiods?\b|\bby (?:19|20)\d\d\b|"
    r"\bnext year\b|\bthis year\b|\bnext \d+ (?:months?|years?)\b",
    re.IGNORECASE,
)
"""Language that makes a question about WHEN rather than WHETHER.

A promise and its activation are different reasoning problems, and conflating
them is why "will I marry" and "when will I marry" retrieve the same rules in
most systems. Here the distinction picks the mode, and the mode picks whether a
time scope is resolved at all.
"""

_TIMING_ONLY = re.compile(
    r"\b(next|upcoming|current) (good |favourable |favorable |auspicious )?"
    r"(period|phase|dasha|window|time)\b|\bwhat'?s my (current|next) dasha\b|"
    r"\bwhich dasha\b",
    re.IGNORECASE,
)
_DESCRIPTIVE = re.compile(
    r"\bwhat am i like\b|\bwho am i\b|\bmy (personality|nature|temperament|"
    r"character|strengths|weaknesses)\b|\bdescribe me\b|\bwhat kind of person\b",
    re.IGNORECASE,
)
_LIFE_MAP = re.compile(
    r"\b(full|complete|whole|entire|overall) (reading|report|analysis|chart|"
    r"horoscope|life)\b|\blife map\b|\btell me everything\b|\bread my chart\b",
    re.IGNORECASE,
)
_COMPATIBILITY = re.compile(
    r"\b(compatib\w*|kundali matching|kundli matching|guna milan|horoscope "
    r"matching|match(ing)? (our|my) (chart|kundali|kundli|horoscope)s?|"
    r"are we compatible|do we match)\b",
    re.IGNORECASE,
)
_PRASHNA = re.compile(
    r"\bprashna\b|\bprasna\b|\bhorary\b|\bright now, will\b|"
    r"\b(without|don'?t know) my birth (time|details)\b",
    re.IGNORECASE,
)
_MUHURTA = re.compile(
    r"\bmuhurta\b|\bmuhurat\b|\bauspicious (date|day|time) (to|for)\b|"
    r"\bbest (date|day|time) (to|for)\b|\bwhen should i (start|begin|launch|buy)\b",
    re.IGNORECASE,
)
_KNOWLEDGE = re.compile(
    r"\bwhat does (bphs|parashara|parasara|saravali|phaladeepika|the "
    r"(text|book|classics?)) say\b|\baccording to (bphs|parashara)\b|"
    r"\bwhat is (a |an )?(yoga|dasha|nakshatra|bhava|rashi|graha|drishti)\b|"
    r"\bexplain the \w+ (yoga|house|lord)\b",
    re.IGNORECASE,
)
_MODALITY = re.compile(
    r"\bnumerolog\w*|\bmulank\b|\bbhagyaank\b|\bbhagyank\b|\blucky number\b|"
    r"\bname number\b|\bpalm\w*|\bface reading\b|\bvastu\b",
    re.IGNORECASE,
)
_RECTIFICATION = re.compile(
    r"\brectif\w*|\b(unsure|not sure|don'?t know) (of|about) my birth time\b|"
    r"\bbirth time (is )?(uncertain|approximate|unknown)\b",
    re.IGNORECASE,
)

_FLAG_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("safety.decision_request", re.compile(
        r"\bshould i\b|\bwhat should i do\b|\btell me what to do\b|"
        r"\bmust i\b|\bdo you recommend\b|\bis it (a good idea|wise) (to|for)\b",
        re.IGNORECASE)),
    ("safety.third_party", re.compile(
        r"\b(my (friend|colleague|boss|neighbour|neighbor|ex)|is (he|she) )\b",
        re.IGNORECASE)),
    ("safety.medical", re.compile(
        r"\b(cancer|tumou?r|diagnos\w+|surgery|treatment|medication|therapy|"
        r"symptoms?|cure(d)?|disease)\b", re.IGNORECASE)),
    ("safety.legal", re.compile(
        r"\b(lawsuit|court case|litigation|legal case|sue|jail|imprisonment|"
        r"bail)\b", re.IGNORECASE)),
    ("safety.financial_specific", re.compile(
        r"\b(should i (buy|sell|invest)|which stock|crypto|bitcoin|"
        r"how much (should i )?invest|shares? to buy)\b", re.IGNORECASE)),
    ("safety.mortality", re.compile(
        r"\bwhen will i die\b|\bhow long will i live\b|\bmy death\b|"
        r"\bdate of (my )?death\b|\bwill i die\b", re.IGNORECASE)),
    ("safety.distress", re.compile(
        r"\b(suicide|kill myself|end my life|self.harm|want to die|"
        r"no reason to live)\b", re.IGNORECASE)),
    ("safety.minor_subject", re.compile(
        r"\bmy (\d|1[0-7])[- ]year[- ]old\b|\bmy (toddler|infant|baby)\b",
        re.IGNORECASE)),
    ("handling.emotional_charge", re.compile(
        r"\b(desperate|terrified|scared|anxious|worried sick|exhausted|"
        r"can'?t take it|frustrated|hopeless|miserable)\b", re.IGNORECASE)),
    ("handling.skeptical_framing", re.compile(
        r"\b(prove it|do you (really )?believe|is this (even )?real|"
        r"astrology is|nonsense|pseudoscience|convince me)\b", re.IGNORECASE)),
    ("handling.urgency", re.compile(
        r"\b(urgent|urgently|as soon as possible|asap|tomorrow|by tonight|"
        r"right now|immediately)\b", re.IGNORECASE)),
    ("handling.requests_brevity", re.compile(
        r"\b(briefly|in short|one line|short answer|just tell me|"
        r"keep it short|tl;?dr)\b", re.IGNORECASE)),
    ("structure.multi_part", re.compile(r"\?.*\?", re.DOTALL)),
    ("structure.hypothetical", re.compile(
        r"\bwhat if\b|\bsuppose\b|\bhypothetically\b|\bif i were to\b",
        re.IGNORECASE)),
    ("structure.comparative", re.compile(
        r"\b(better|worse) (than|option)\b|\bcompared to\b|\bor should i\b|"
        r"\bwhich (one|of the two)\b", re.IGNORECASE)),
)

_SUBJECT_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("partner", re.compile(r"\bmy (wife|husband|spouse|partner|fianc[ée]e?)\b", re.IGNORECASE)),
    ("child", re.compile(r"\bmy (son|daughter|child|kid)\b", re.IGNORECASE)),
    ("parent", re.compile(r"\bmy (father|mother|dad|mom|mum|parents?)\b", re.IGNORECASE)),
    ("other", re.compile(r"\bmy (friend|colleague|boss|brother|sister|ex)\b", re.IGNORECASE)),
)


# ==========================================================================
# Time scope
# ==========================================================================

# The article is optional because both "the next few months" and "the next a
# few months" reach here, and only one of them is English.
_COUNT = r"(\d+|(?:a )?few|(?:a )?couple(?: of)?)"
_REL_YEARS = re.compile(rf"\bnext {_COUNT} years?\b", re.IGNORECASE)
_REL_MONTHS = re.compile(rf"\bnext {_COUNT} months?\b", re.IGNORECASE)
_ABS_YEAR = re.compile(r"\b(?:in|by|during) ((?:19|20)\d\d)\b", re.IGNORECASE)
_NEXT_YEAR = re.compile(r"\bnext year\b", re.IGNORECASE)
_THIS_YEAR = re.compile(r"\bthis year\b", re.IGNORECASE)

_WORD_COUNTS = {"few": 3, "couple": 2, "couple of": 2}

DEFAULT_HORIZON_MONTHS = 36
"""How far a timing question looks when it does not say.

Three years is one Vimshottari antardasha of the longer mahadashas and covers
most of the shorter ones end to end - long enough for a period boundary to fall
inside it, short enough that the window means something.
"""


def _shift_months(when: datetime, months: int) -> datetime:
    total = when.month - 1 + months
    year = when.year + total // 12
    month = total % 12 + 1
    # Clamp rather than roll over: 31 Jan + 1 month is 28/29 Feb, not 3 March.
    day = min(when.day, _days_in_month(year, month))
    return when.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (datetime(year + month // 12, month % 12 + 1, 1) - datetime(year, month, 1)).days


def _count(token: str) -> int:
    token = token.lower().removeprefix("a ").strip()
    return _WORD_COUNTS.get(token) or int(token)


def resolve_time_scope(text: str, now: datetime) -> Optional[TimeScope]:
    """Turn a relative phrase into dates, once, here.

    Returns None when the question names no horizon at all - the caller then
    applies its own default rather than this function inventing one, so that
    "no horizon given" and "a horizon of three years" stay distinguishable in
    the stored spec.
    """
    m = _REL_YEARS.search(text)
    if m:
        n = _count(m.group(1))
        return TimeScope(
            start=now.date().isoformat(),
            end=_shift_months(now, 12 * n).date().isoformat(),
            granularity="year" if n >= 3 else "quarter",
            user_phrase=m.group(0),
        )

    m = _REL_MONTHS.search(text)
    if m:
        n = _count(m.group(1))
        return TimeScope(
            start=now.date().isoformat(),
            end=_shift_months(now, n).date().isoformat(),
            granularity="month",
            user_phrase=m.group(0),
        )

    m = _ABS_YEAR.search(text)
    if m:
        year = int(m.group(1))
        return TimeScope(
            start=f"{year}-01-01", end=f"{year}-12-31",
            granularity="quarter", user_phrase=m.group(0),
        )

    if _NEXT_YEAR.search(text):
        return TimeScope(
            start=f"{now.year + 1}-01-01", end=f"{now.year + 1}-12-31",
            granularity="quarter", user_phrase="next year",
        )

    if _THIS_YEAR.search(text):
        return TimeScope(
            start=f"{now.year}-01-01", end=f"{now.year}-12-31",
            granularity="quarter", user_phrase="this year",
        )

    return None


def default_scope(now: datetime, months: int = DEFAULT_HORIZON_MONTHS) -> TimeScope:
    return TimeScope(
        start=now.date().isoformat(),
        end=_shift_months(now, months).date().isoformat(),
        granularity="quarter",
    )


# ==========================================================================
# Parsing
# ==========================================================================


def _specificity(phrase: str) -> float:
    if phrase in GENERIC_PHRASES:
        return GENERIC_WEIGHT
    return 1.0 + phrase.count(" ")


def _hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    # Word-bounded, so "son" does not match "reason" and "ill" does not match
    # "will" - which it did, and routed half the corpus into domain.health.
    return [p for p in phrases if re.search(rf"(?<!\w){re.escape(p)}(?!\w)", text)]


def score_domains(text: str) -> tuple[dict[str, float], dict[str, list[str]]]:
    """Domain -> score, and domain -> the phrases that earned it."""
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    for domain, phrases in DOMAIN_KEYWORDS.items():
        hits = _hits(text, phrases)
        if hits:
            scores[domain] = sum(_specificity(p) for p in hits)
            matched[domain] = hits
    return scores, matched


def _rank(scores: dict[str, float]) -> list[str]:
    order = list(DOMAIN_KEYWORDS)
    return sorted(scores, key=lambda d: (-scores[d], order.index(d)))[:MAX_DOMAINS]


def detect_flags(text: str) -> list[Flag]:
    flags: list[Flag] = []
    for flag_id, pattern in _FLAG_MARKERS:
        m = pattern.search(text)
        if m:
            assert flag_id in SEED_FLAG_REGISTRY, flag_id
            flags.append(Flag(flag_id=flag_id, evidence_span=m.group(0)))
    return flags


def detect_turn_type(text: str) -> TurnType:
    """Order matters: a correction often reads like a follow-up, and a
    challenge always does."""
    if _SOCIAL.match(text):
        return TurnType.SOCIAL
    if _CHALLENGE.search(text):
        return TurnType.CHALLENGE
    if _CORRECTION.search(text):
        return TurnType.CORRECTION
    if _DRILLDOWN.search(text):
        return TurnType.DRILLDOWN
    if _META.search(text):
        return TurnType.META
    if _FOLLOWUP.match(text):
        return TurnType.FOLLOWUP
    return TurnType.NEW_QUESTION


def detect_mode(text: str, domains: list[str]) -> Mode:
    """Most specific mode first. Every one of these is a different question
    with different inputs, and picking the wrong one is not recoverable
    downstream - a compatibility question answered from one chart is a
    confident answer to a question nobody asked."""
    if _RECTIFICATION.search(text):
        return Mode.RECTIFICATION
    if _MODALITY.search(text):
        return Mode.MODALITY
    if _COMPATIBILITY.search(text):
        return Mode.COMPATIBILITY
    if _MUHURTA.search(text):
        return Mode.MUHURTA
    if _PRASHNA.search(text):
        return Mode.PRASHNA
    if _KNOWLEDGE.search(text):
        return Mode.KNOWLEDGE
    if _LIFE_MAP.search(text):
        return Mode.LIFE_MAP
    if _TIMING_ONLY.search(text):
        return Mode.TIMING_ONLY
    if _DESCRIPTIVE.search(text) or (
        domains == ["domain.temperament"] and not TIMING_MARKERS.search(text)
    ):
        return Mode.NATAL_DESCRIPTIVE
    return Mode.NATAL_PREDICTIVE


def detect_subjects(text: str) -> list[SubjectRef]:
    refs = [SubjectRef(role="self")]
    for role, pattern in _SUBJECT_MARKERS:
        m = pattern.search(text)
        if m:
            refs.append(SubjectRef(
                role=role,  # type: ignore[arg-type]
                label=m.group(0),
                # A named third party has not agreed to be read. The consent
                # gate is the product's decision, not the engine's - the engine
                # only records that one is required.
                consent_required=role in ("partner", "other"),
            ))
    return refs


def _confidence(text: str, scores: dict[str, float], turn: TurnType, mode: Mode) -> float:
    """How much the parse should be trusted.

    Low confidence is not a failure state, it is an instruction to ask. The
    penalties are for the two situations where a plausible answer is most
    likely to be answering the wrong question: nothing matched at all, and a
    message so short that whatever matched was probably incidental.
    """
    if turn in (TurnType.SOCIAL, TurnType.META):
        return 1.0
    score = 0.45
    if scores:
        score += 0.25
        if max(scores.values()) >= 2.0:
            score += 0.10
    if mode is not Mode.NATAL_PREDICTIVE:
        score += 0.15  # an explicit mode marker fired, which is strong evidence
    if len(text.split()) < 3 and turn is TurnType.NEW_QUESTION:
        score -= 0.30
    return max(0.0, min(1.0, round(score, 2)))


def _payload(mode: Mode, text: str, domains: list[str], now: datetime):
    scope = resolve_time_scope(text, now)
    subs = [
        SubQuestion(id=f"sq{i + 1}", domain=d) for i, d in enumerate(domains)
    ]

    if mode is Mode.NATAL_PREDICTIVE:
        return NatalPredictivePayload(
            sub_questions=subs,
            time_scope=scope or (default_scope(now) if TIMING_MARKERS.search(text) else None),
        )
    if mode is Mode.NATAL_DESCRIPTIVE:
        # No time scope, ever. A descriptive question is about the natal
        # promise, and attaching a window to it invites a timing claim the
        # question did not ask for and the evidence does not support.
        return NatalDescriptivePayload(sub_questions=subs)
    if mode is Mode.TIMING_ONLY:
        return TimingOnlyPayload(
            of_what=domains[0] if domains else "",
            time_scope=scope or default_scope(now),
        )
    if mode is Mode.LIFE_MAP:
        return LifeMapPayload(emphasis=domains)
    if mode is Mode.COMPATIBILITY:
        return CompatibilityPayload()
    if mode is Mode.PRASHNA:
        return PrashnaPayload(question_text=text)
    if mode is Mode.MUHURTA:
        return MuhurtaPayload(activity=text, time_scope=scope)
    if mode is Mode.KNOWLEDGE:
        return KnowledgePayload(topic=text)
    if mode is Mode.MODALITY:
        modality = (
            "palmistry" if re.search(r"\bpalm", text, re.IGNORECASE)
            else "face" if re.search(r"\bface reading\b", text, re.IGNORECASE)
            else "vastu" if re.search(r"\bvastu\b", text, re.IGNORECASE)
            else "numerology"
        )
        return ModalityPayload(modality=modality, about=text)
    if mode is Mode.RECTIFICATION:
        return RectificationPayload()
    return UnsupportedPayload(reason="no mode matched", nearest_supported=None)


def _answer_shape(text: str, mode: Mode, flags: list[Flag]) -> AnswerShape:
    brief = any(f.flag_id == "handling.requests_brevity" for f in flags)
    if mode is Mode.LIFE_MAP:
        return AnswerShape(format="report", length="deep", complexity="LIFE_MAP")
    if mode is Mode.TIMING_ONLY:
        return AnswerShape(format="prose_with_timeline", complexity="STANDARD",
                           length="brief" if brief else "standard")
    if mode is Mode.COMPATIBILITY:
        return AnswerShape(format="comparison", complexity="DEEP")
    return AnswerShape(
        format="prose",
        length="brief" if brief else "standard",
        complexity="QUICK" if brief else "STANDARD",
    )


def parse(
    text: str,
    *,
    now: Optional[datetime] = None,
    available: Optional[set[InputKind]] = None,
    language: str = "en",
    schools: Optional[list[str]] = None,
) -> QuestionSpec:
    """Raw text -> a fully gated QuestionSpec.

    `available` is what the caller actually holds. Pass it, or every spec comes
    back blocked on a birth profile that the app has had since sign-up.
    """
    from rishivan.koonji.question import resolve_missing, required_inputs

    now = now or datetime.now()
    raw = text or ""
    lowered = raw.lower()

    turn = detect_turn_type(raw)
    scores, matched = score_domains(lowered)
    domains = _rank(scores)
    mode = detect_mode(raw, domains)
    flags = detect_flags(raw)

    spec = QuestionSpec(
        raw=raw,
        language=language,
        turn_type=turn,
        mode=mode,
        payload=_payload(mode, raw, domains, now),
        subject_refs=detect_subjects(raw),
        routing=Routing(
            domains=domains,
            schools=schools if schools is not None else ["school.parashari"],
            min_domain_weight=INCIDENTAL_DOMAIN_WEIGHT if domains else 0.0,
            reason=(
                "; ".join(f"{d} <- {', '.join(matched[d])}" for d in domains)
                or "no domain phrase matched - the whole corpus is in scope"
            ),
            matched={d: matched[d] for d in domains},
        ),
        flags=flags,
        answer_shape=_answer_shape(raw, mode, flags),
        parse_confidence=_confidence(raw, scores, turn, mode),
        ambiguity_note=(
            None if scores or turn is not TurnType.NEW_QUESTION
            else "no domain phrase matched; reading against the whole corpus"
        ),
    )
    spec.required_inputs = required_inputs(spec)
    spec.missing_inputs = resolve_missing(spec, available or set())
    return spec


# ==========================================================================
# The filter itself
# ==========================================================================


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    """Exactly what `Engine.read` is given, and why.

    Separated from the QuestionSpec on purpose. The spec is what the user asked;
    the plan is what we will therefore look at. Keeping them apart means a
    policy change - serving candidate rules to internal users, widening a narrow
    question after a first pass returns nothing - is a change to the plan and
    leaves the record of what was asked untouched.
    """

    domains: Optional[frozenset[str]]
    """None means unfiltered. An empty set would mean "no rules at all", which
    is never what a router failing to match should produce."""

    schools: Optional[frozenset[str]]
    statuses: frozenset[str]
    min_domain_weight: float = 0.0
    when: Optional[datetime] = None
    widen_if_empty: bool = True
    """If the filtered read produces nothing, retry unfiltered before saying the
    corpus is silent. A router miss and a genuinely silent corpus look identical
    from the outside, and only one of them is an honest 'insufficient
    evidence'."""

    notes: tuple[str, ...] = field(default=())

    def unfiltered(self) -> "RetrievalPlan":
        return RetrievalPlan(
            domains=None, schools=self.schools, statuses=self.statuses,
            min_domain_weight=0.0, when=self.when, widen_if_empty=False,
            notes=self.notes + ("widened: domain filter returned no firings",),
        )


PRODUCTION_ONLY = frozenset({"production"})


def retrieval_plan(
    spec: QuestionSpec,
    *,
    statuses: frozenset[str] = PRODUCTION_ONLY,
    when: Optional[datetime] = None,
) -> RetrievalPlan:
    """The QuestionSpec's routing, turned into engine filters.

    LIFE_MAP deliberately drops the domain filter: it is the one mode whose
    question is "all of it", and narrowing it to three domains would answer a
    different question than the one asked.
    """
    domains = frozenset(spec.routing.domains) or None
    if spec.mode is Mode.LIFE_MAP:
        domains = None

    scope: Optional[TimeScope] = getattr(spec.payload, "time_scope", None)
    at = when
    if at is None and scope is not None:
        at = datetime.fromisoformat(scope.start)

    notes: list[str] = [spec.routing.reason]
    if spec.mode is Mode.LIFE_MAP:
        notes.append("life_map: domain filter dropped by design")

    return RetrievalPlan(
        domains=domains,
        schools=frozenset(spec.routing.schools) or None,
        statuses=statuses,
        min_domain_weight=spec.routing.min_domain_weight if domains else 0.0,
        when=at,
        widen_if_empty=domains is not None,
        notes=tuple(notes),
    )
