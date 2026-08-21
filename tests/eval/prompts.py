"""The evaluation prompt suite for the Rishivan Council RAG/routing pipeline.

Two tiers, matching how expensive each check is:

  - CLASSIFICATION_CASES: checked against ``classify_query()`` alone (one
    Gemini call each) — routing, intent, domain, and the smalltalk/gibberish
    bypass. Cheap enough to run ~50 of them.
  - PIPELINE_CASES: checked against the full ``council_consult()`` pipeline
    (chart computation, real Qdrant retrieval, real generation) — the actual
    end-to-end RAG behavior, at real per-call cost/latency, so kept to a
    smaller representative set.

Every field on a case that is left as ``None`` (or the class default) means
"don't check this" — cases assert only what they explicitly set, since an
LLM router can reasonably vary on genuinely ambiguous questions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rishivan.chart.ephemeris import BirthData

# One fixed birth chart reused across every case that needs one, so results
# are comparable across runs. (1990-08-29, 09:41, Jaipur — same example used
# throughout the project's own plans/tests.)
FIXED_BIRTH_DATA = BirthData(
    year=1990, month=8, day=29, hour=9, minute=41,
    tz_offset_hours=5.5, lat=26.9124, lon=75.7873, place="Jaipur",
)


@dataclass
class ClassificationCase:
    id: str
    category: str
    question: str
    expect_smalltalk: bool | None = None
    expect_domain: str | None = None            # "natal"|"muhurta"|"prashna"|"general"
    expect_intent: str | None = None            # "chart"|"fact"
    expect_chart_type: str | None = None        # "varga"|"numerology"|"ashtakavarga"|"dasha"
    expect_varga_code: str | None = None
    expect_rishi: str | None = None             # hard pin — only for unambiguous cases
    expect_rishi_in: tuple[str, ...] | None = None  # soft check — any of these is a pass
    expect_dasha_level: str | None = None        # "maha"|"antar"|"pratyantar"|"all"|"none"
    expect_relevant_vargas_include: tuple[str, ...] | None = None
    conversation_seed: tuple[str, str, str] | None = None  # (question, answer, rishi)
    notes: str = ""


@dataclass
class PipelineCase:
    id: str
    category: str
    question: str
    needs_birth_data: bool = False
    expect_is_warmth: bool | None = None
    expect_chart_table: bool | None = None      # True/False = must/must-not be set
    expect_sources_nonempty: bool | None = None
    expect_domain: str | None = None
    expect_devanagari: bool = False
    min_answer_chars: int = 0
    conversation_seed: tuple[str, str, str] | None = None
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────
# TIER 1 — classification / routing (fast: one LLM call each)
# ─────────────────────────────────────────────────────────────────────────

CLASSIFICATION_CASES: list[ClassificationCase] = [
    # ── A. Smalltalk / gibberish — must bypass to the warmth node ──────────
    ClassificationCase("smalltalk-01", "smalltalk", "hi", expect_smalltalk=True),
    ClassificationCase("smalltalk-02", "smalltalk", "hello there!", expect_smalltalk=True),
    ClassificationCase("smalltalk-03", "smalltalk", "thanks so much, that helped", expect_smalltalk=True),
    ClassificationCase("smalltalk-04", "smalltalk", "namaste \U0001F64F", expect_smalltalk=True),
    ClassificationCase("smalltalk-05", "smalltalk", "who are you?", expect_smalltalk=True),
    ClassificationCase("smalltalk-06", "smalltalk", "what can you do?", expect_smalltalk=True),
    ClassificationCase("smalltalk-07", "smalltalk", "lol ok bye", expect_smalltalk=True),
    ClassificationCase("smalltalk-08", "smalltalk", "namaste, kaise ho?", expect_smalltalk=True,
                        notes="Hinglish greeting"),
    ClassificationCase("gibberish-01", "gibberish", "asdkj alksjd alksjdlk qwop", expect_smalltalk=True),
    ClassificationCase("gibberish-02", "gibberish", "aaaaa bbbbb ccccc ddddd", expect_smalltalk=True),
    ClassificationCase("gibberish-03", "gibberish", "asdf;lkj1234!!!???", expect_smalltalk=True),

    # ── B. General conceptual astrology — real questions, NOT smalltalk ────
    ClassificationCase("general-01", "general", "explain Gajakesari yoga",
                        expect_smalltalk=False, expect_domain="general", expect_rishi_in=("vyom",)),
    ClassificationCase("general-02", "general", "what is a dasha in vedic astrology",
                        expect_smalltalk=False, expect_domain="general"),
    ClassificationCase("general-03", "general", "how does ashtakavarga work",
                        expect_smalltalk=False, expect_domain="general"),
    ClassificationCase("general-04", "general", "what is the difference between D1 and D9 charts",
                        expect_smalltalk=False, expect_domain="general", expect_intent="fact"),
    ClassificationCase("general-05", "general", "what is prashna astrology",
                        expect_smalltalk=False, expect_domain="general"),

    # ── C. Natal — career / wealth (dhruvan) ────────────────────────────────
    ClassificationCase("career-01", "natal-career", "will I be successful in my career",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="dhruvan"),
    ClassificationCase("career-02", "natal-career", "career guidance please",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="dhruvan",
                        expect_relevant_vargas_include=("D10",)),
    ClassificationCase("career-03", "natal-career", "should I start my own business",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="dhruvan"),
    ClassificationCase("career-04", "natal-career", "what does my chart say about wealth",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="dhruvan"),

    # ── D. Natal — marriage / relationships ─────────────────────────────────
    ClassificationCase("marriage-01", "natal-marriage", "when will I get married",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="ritam",
                        expect_relevant_vargas_include=("D9",),
                        notes="Explicit routing rule in the classifier prompt itself"),
    ClassificationCase("marriage-02", "natal-marriage", "will my marriage be happy",
                        expect_smalltalk=False, expect_domain="natal",
                        expect_rishi_in=("medhan", "ritam")),
    ClassificationCase("marriage-03", "natal-marriage", "tell me about my compatibility with my partner",
                        expect_smalltalk=False, expect_domain="natal"),
    ClassificationCase("marriage-04", "natal-marriage", "why is my relationship so difficult right now",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi_in=("medhan",)),

    # ── E. Natal — timing / dasha (ritam) ────────────────────────────────────
    ClassificationCase("timing-01", "natal-timing", "what is my current mahadasha",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="ritam",
                        expect_intent="fact", expect_dasha_level="maha"),
    ClassificationCase("timing-02", "natal-timing", "when does my antardasha change",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="ritam",
                        expect_dasha_level="antar"),
    ClassificationCase("timing-03", "natal-timing", "explain my pratyantardasha",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="ritam",
                        expect_dasha_level="pratyantar"),
    ClassificationCase("timing-04", "natal-timing", "what dasha am I running right now",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="ritam",
                        expect_dasha_level="all"),
    ClassificationCase("timing-05", "natal-timing", "is next year a good year for me",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="ritam"),

    # ── F. Natal — remedies (tejan) ──────────────────────────────────────────
    ClassificationCase("remedy-01", "natal-remedy", "what remedies should I do for Saturn",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="tejan"),
    ClassificationCase("remedy-02", "natal-remedy", "suggest a gemstone for me",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="tejan"),
    ClassificationCase("remedy-03", "natal-remedy", "what mantra should I chant daily",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="tejan"),

    # ── G. Natal — health / family (medhan) ──────────────────────────────────
    ClassificationCase("health-01", "natal-health", "will I have children",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="medhan",
                        expect_relevant_vargas_include=("D7",)),
    ClassificationCase("health-02", "natal-health", "what does my chart say about my health",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="medhan"),

    # ── H. Natal — hidden patterns (tattvan) ─────────────────────────────────
    ClassificationCase("shadow-01", "natal-shadow", "what are my hidden strengths",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="tattvan",
                        expect_relevant_vargas_include=("D27",)),
    ClassificationCase("shadow-02", "natal-shadow", "what are my biggest weaknesses",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="tattvan"),

    # ── I. Natal — spiritual (pragnav) ───────────────────────────────────────
    ClassificationCase("spirit-01", "natal-spiritual", "how can I grow spiritually",
                        expect_smalltalk=False, expect_rishi_in=("pragnav",)),
    ClassificationCase("spirit-02", "natal-spiritual", "what is my life purpose",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="agam"),

    # ── J. Natal — soul / karma (agam) ───────────────────────────────────────
    ClassificationCase("karma-01", "natal-karma", "what karma am I working through in this life",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi_in=("agam",)),

    # ── K. Natal — cosmic patterns (vyom) ────────────────────────────────────
    ClassificationCase("cosmic-01", "natal-cosmic", "what nakshatra is my moon in",
                        expect_smalltalk=False, expect_domain="natal", expect_intent="fact"),

    # ── L. Chart display requests (intent=chart, deterministic table) ───────
    ClassificationCase("chart-01", "chart-display", "show me my D9 chart",
                        expect_smalltalk=False, expect_intent="chart",
                        expect_chart_type="varga", expect_varga_code="D9"),
    ClassificationCase("chart-02", "chart-display", "compute my D10 chart",
                        expect_smalltalk=False, expect_intent="chart",
                        expect_chart_type="varga", expect_varga_code="D10"),
    ClassificationCase("chart-03", "chart-display", "what's my mulank number",
                        expect_smalltalk=False, expect_intent="chart",
                        expect_chart_type="numerology"),
    ClassificationCase("chart-04", "chart-display", "give me my ashtakavarga table",
                        expect_smalltalk=False, expect_intent="chart",
                        expect_chart_type="ashtakavarga"),
    ClassificationCase("chart-05", "chart-display", "show my vimshottari dasha timeline",
                        expect_smalltalk=False, expect_intent="chart",
                        expect_chart_type="dasha"),
    ClassificationCase("chart-06", "chart-display", "give me my kundli",
                        expect_smalltalk=False, expect_intent="chart",
                        expect_chart_type="varga", expect_varga_code="D1"),
    ClassificationCase("chart-07", "chart-display", "what does my navamsa look like",
                        expect_smalltalk=False, expect_intent="chart",
                        expect_chart_type="varga", expect_varga_code="D9",
                        notes="Named by classical term, not the D-code"),
    ClassificationCase("chart-08", "chart-display", "show my sarvashtakavarga bindus",
                        expect_smalltalk=False, expect_intent="chart",
                        expect_chart_type="ashtakavarga",
                        notes="Must NOT be mapped to a varga code (regression case)"),

    # ── M. Muhurta ────────────────────────────────────────────────────────────
    ClassificationCase("muhurta-01", "muhurta", "is tomorrow good for travel",
                        expect_smalltalk=False, expect_domain="muhurta"),
    ClassificationCase("muhurta-02", "muhurta", "is today a good day to start a new business",
                        expect_smalltalk=False, expect_domain="muhurta"),
    ClassificationCase("muhurta-03", "muhurta", "when is a good muhurta for marriage this month",
                        expect_smalltalk=False, expect_domain="muhurta"),

    # ── N. Prashna (horary, no birth data implied) ───────────────────────────
    ClassificationCase("prashna-01", "prashna", "should I buy this house",
                        expect_smalltalk=False, expect_domain="prashna"),
    ClassificationCase("prashna-02", "prashna", "will this business deal work out",
                        expect_smalltalk=False, expect_domain="prashna"),

    # ── O. Hindi / Hinglish ───────────────────────────────────────────────────
    ClassificationCase("hindi-01", "language", "meri shaadi kab hogi",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="ritam",
                        notes="Hinglish for 'when will I get married'"),
    ClassificationCase("hindi-02", "language", "mera career kaisa rahega",
                        expect_smalltalk=False, expect_domain="natal", expect_rishi="dhruvan"),
    ClassificationCase("hindi-03", "language", "क्या मैं सफल होउंगा",
                        expect_smalltalk=False, expect_domain="natal",
                        notes="Devanagari: 'will I be successful'"),

    # ── P. Panchang / daily timing ────────────────────────────────────────────
    ClassificationCase("panchang-01", "panchang", "what time is rahu kaal today",
                        expect_smalltalk=False),
    ClassificationCase("panchang-02", "panchang", "what is a good muhurta today for starting work",
                        expect_smalltalk=False, expect_domain="muhurta"),

    # ── Q. Follow-up / conversation continuity ───────────────────────────────
    ClassificationCase(
        "followup-01", "followup", "tell me more",
        expect_smalltalk=False, expect_rishi="ritam",
        conversation_seed=("when will I get married", "Marriage is close for you.", "ritam"),
        notes="Should stay with the same Rishi rather than re-route",
    ),
    ClassificationCase(
        "followup-02", "followup", "yes",
        expect_smalltalk=False, expect_rishi="medhan",
        conversation_seed=("will I have children", "It is possible, in time.", "medhan"),
    ),

    # ── R. Edge / ambiguous ───────────────────────────────────────────────────
    ClassificationCase("edge-01", "edge", "asdlkfj my career asdlkj",
                        expect_smalltalk=False,
                        notes="Real content buried in noise — must NOT be dropped as gibberish"),
    ClassificationCase("edge-02", "edge", "?",
                        notes="No expectation pinned — just must not crash"),
    ClassificationCase(
        "edge-03", "edge",
        "so basically I've been thinking about my career and also my marriage and "
        "whether I should move cities and also what my dasha is doing and honestly "
        "I don't even know where to start",
        expect_smalltalk=False, expect_domain="natal",
        notes="Rambling multi-topic question — must still classify as a real question",
    ),
]


# ─────────────────────────────────────────────────────────────────────────
# TIER 2 — full pipeline (slow: real chart + retrieval + generation)
# ─────────────────────────────────────────────────────────────────────────

PIPELINE_CASES: list[PipelineCase] = [
    PipelineCase("pipe-smalltalk-01", "smalltalk", "hi there",
                 expect_is_warmth=True, expect_sources_nonempty=False, min_answer_chars=1),
    PipelineCase("pipe-gibberish-01", "gibberish", "asdkj alksjd qwop zzzz",
                 expect_is_warmth=True, expect_sources_nonempty=False, min_answer_chars=1),
    PipelineCase("pipe-general-01", "general", "explain Gajakesari yoga",
                 expect_is_warmth=False, expect_domain="general",
                 expect_sources_nonempty=True, min_answer_chars=50),
    PipelineCase("pipe-marriage-01", "natal-marriage", "when will I get married",
                 needs_birth_data=True, expect_is_warmth=False, expect_domain="natal",
                 expect_sources_nonempty=True, min_answer_chars=50),
    PipelineCase("pipe-career-01", "natal-career", "will I be successful in my career",
                 needs_birth_data=True, expect_is_warmth=False, expect_domain="natal",
                 expect_sources_nonempty=True, min_answer_chars=50),
    PipelineCase("pipe-remedy-01", "natal-remedy", "what remedies should I do for Saturn",
                 needs_birth_data=True, expect_is_warmth=False, expect_domain="natal",
                 expect_sources_nonempty=True, min_answer_chars=50),
    PipelineCase("pipe-chart-d9", "chart-display", "show me my D9 chart",
                 needs_birth_data=True, expect_chart_table=True, min_answer_chars=0),
    PipelineCase("pipe-chart-numerology", "chart-display", "what's my mulank number",
                 needs_birth_data=True, expect_chart_table=True, min_answer_chars=0),
    PipelineCase("pipe-chart-dasha", "chart-display", "show my vimshottari dasha timeline",
                 needs_birth_data=True, expect_chart_table=True, min_answer_chars=0),
    PipelineCase("pipe-muhurta-01", "muhurta", "is tomorrow good for travel",
                 expect_is_warmth=False, expect_domain="muhurta", min_answer_chars=30),
    PipelineCase("pipe-prashna-01", "prashna", "should I buy this house",
                 expect_is_warmth=False, expect_domain="prashna", min_answer_chars=30),
    PipelineCase("pipe-hindi-01", "language", "meri shaadi kab hogi",
                 needs_birth_data=True, expect_is_warmth=False, expect_domain="natal",
                 min_answer_chars=30,
                 notes="Answer should come back in Hindi/Devanagari or Hinglish, not plain English"),
    PipelineCase(
        "pipe-followup-01", "followup", "tell me more",
        needs_birth_data=True, expect_is_warmth=False,
        conversation_seed=("when will I get married", "Marriage is close for you, in time.", "ritam"),
        min_answer_chars=30,
    ),
    PipelineCase("pipe-spiritual-01", "natal-spiritual", "what is my life purpose",
                 needs_birth_data=True, expect_is_warmth=False, expect_domain="natal",
                 expect_sources_nonempty=True, min_answer_chars=50),
]
