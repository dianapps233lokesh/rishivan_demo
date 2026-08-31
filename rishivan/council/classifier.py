"""Rishi-aware query classifier.

Uses a single Gemini Flash call to determine:
  - Which Rishi should answer (primary)
  - Which query domain applies (natal/muhurta/prashna/general)
  - Whether birth data is needed
"""
from __future__ import annotations

import json
import logging

from rishivan.council.conversation import is_probable_followup
from rishivan.council.domains import QueryDomain
from rishivan.council.personas import ALL_RISHI_NAMES

logger = logging.getLogger(__name__)

_CHART_TYPES = ("varga", "numerology", "ashtakavarga", "dasha", "shadbala")
"""Every chart kind that has a renderer. Anything else becomes `unsupported`
and is reported to the reader, rather than quietly becoming a D1."""

# Kept in sync with app.astro.kundli.varga.VARGA_REGISTRY (the main repo's
# pure-arithmetic engine that actually computes these) — not imported
# directly, since this module is pure LLM routing and has no chart-engine
# dependency otherwise.
_VARGA_CODES = (
    "D1", "D2", "D3", "D4", "D7", "D9", "D10", "D12",
    "D16", "D20", "D24", "D27", "D30", "D40", "D45", "D60",
)

_CLASSIFY_PROMPT = """\
You are a Vedic astrology query router for the Rishivan Council of Eight Rishis.
Each Rishi specialises in a different domain. Given the user's question, select
the most appropriate Rishi to answer it AND classify the query type.

THE EIGHT RISHIS:
1. agam    — Soul purpose, karma, past-life patterns, birth blueprint
2. vyom    — Planets, nakshatras, yogas, cosmic patterns and combinations
3. dhruvan — Career, wealth, leadership, business, material decisions
4. ritam   — Timing of events, dasha analysis, muhurta, transits
5. tejan   — Remedies, mantras, gemstones, rituals, transformative actions
6. medhan  — Relationships, marriage, family, health, emotions
7. tattvan — Hidden patterns, strengths, weaknesses, personality analysis
8. pragnav — Spiritual growth, meditation, moksha, higher consciousness

QUERY DOMAINS:
- natal    : Requires the user's birth chart (personal horoscope reading)
- muhurta  : Is a specific time/date auspicious for an activity?
- prashna  : Horary — answering from the moment of asking (no birth data needed)
- general  : Conceptual knowledge about astrology, texts, rules, definitions

SMALL TALK / GIBBERISH — is this even an astrology question at all?
Before routing to a Rishi, decide "is_smalltalk_or_gibberish":
- true  : greetings ("hi", "hello", "namaste"), thanks, farewells, casual
  chit-chat with no astrology content ("how are you", "who are you", "what
  can you do"), or text with no discernible meaning (keyboard mashing,
  random characters, an empty or near-empty message).
- false : ANY real astrology question, including broad conceptual ones
  ("explain Gajakesari yoga", "what is a dasha", "how does astrology work").
  When in doubt whether something is a genuine astrology question, say false
  — only mark true when there is truly nothing astrological to answer.
When true, the routing fields below (primary_rishi, query_domain, intent,
etc.) are ignored by the caller — fill them with any valid placeholder.

ROUTING RULES:
- "When will I get married?" → ritam (timing), natal
- "What remedies for Saturn?" → tejan (remedies), natal
- "Career guidance" → dhruvan (career), natal
- "Spiritual path / meditation" → pragnav, general or natal
- "Marriage compatibility" → medhan, natal
- "Explain Gajakesari yoga" → vyom, general
- "Should I buy a house?" (no birth data context) → prashna
- "Is tomorrow good for travel?" → ritam, muhurta
- "What is my life purpose?" → agam, natal
- "What are my hidden strengths?" → tattvan, natal
- "What is my current mahadasha?" / "when does my antardasha change?" /
  "explain my pratyantardasha" / "what dasha am I running?" → ritam (timing),
  natal — dasha is always about THIS seeker's own birth chart, never general,
  even though it is also a piece of astrological theory.

If the question is ambiguous between natal and prashna, prefer natal
(the orchestrator will downgrade to prashna if birth data is unavailable).

INTENT — is the seeker asking to SEE a chart/number, or asking a FACT/guidance
question that needs interpreting?
- "chart" : They want something computed and displayed raw — a divisional
  chart, a numerology number, an ashtakavarga table, planetary positions.
  "show me my chart", "compute my D9", "give me my kundli", "what does my
  navamsa look like", "planetary positions please", "what's my mulank",
  "my bhagyaank number", "give me the ashtakavarga chart", "show my
  sarvashtakavarga/bindus". These get a deterministic table, never the
  Rishi voice.
- "fact"  : Anything asking what something means, whether/when something will
  happen, or for guidance — including questions that name a placement
  ("what sign is my moon in?", "what's in my 7th house?", "what does my
  mulank mean for me?"). These are answered by the Rishi, in prose, as normal.

When intent is "chart", also say which kind:
- "chart_type": "shadbala" for any request about planetary STRENGTH — shadbala,
  bala, "how strong is my Saturn", "planetary strength table", ishta/kashta.
  Then: "varga" (a divisional birth chart), "numerology" (mulank/
  bhagyaank), "ashtakavarga" (the benefic bindu/point table — NOT a
  divisional chart, so never map "ashtakavarga"/"sarvashtakavarga"/"bindu
  table"/"SAV" requests to varga_code "D1" or any other D-code), or "dasha"
  (the Vimshottari Mahadasha timeline — "show me my dasha", "what's my
  mahadasha sequence", "list my dasha periods/timeline", "give me my
  vimshottari dasha table". NOT the same as asking what dasha is currently
  running as a fact/interpretation — that stays intent "fact"). Default
  "varga" when unclear.
- "varga_code" (only when chart_type is "varga"): the divisional chart code
  — D1 Rashi (whole chart, default when none is named), D2 Hora (wealth),
  D3 Drekkana (siblings), D4 Chaturthamsha (home), D7 Saptamsha (children),
  D9 Navamsa (marriage/fortune), D10 Dashamsha (career), D12 Dwadashamsha
  (parents), D16 Shodashamsha (vehicles), D20 Vimshamsha (spiritual practice),
  D24 Chaturvimshamsha (education), D27 Bhamsha (strengths/weaknesses), D30
  Trimshamsha (misfortunes), D40 Khavedamsha (maternal legacy), D45
  Akshavedamsha (paternal legacy), D60 Shashtiamsha (past-life karma).

When intent is "fact" (a natal interpretation question), also say which
divisional charts are relevant to grounding THIS specific question — every
chart has a life area it governs, and only the ones the question actually
touches should be pulled in, never all of them:
- "relevant_vargas": a list of codes from D2 (wealth/resources), D3
  (siblings/courage), D4 (home/property/mother), D7 (children/progeny), D9
  (marriage/spouse/fortune), D10 (career/status), D12 (parents), D16
  (vehicles/comforts), D20 (spiritual practice), D24 (education/learning),
  D27 (strengths/weaknesses), D30 (misfortunes), D40 (maternal legacy), D45
  (paternal legacy), D60 (past-life karma). D1 is always included
  automatically — never list it here.
  Examples: "when will I get married?" → ["D9"]. "career guidance" →
  ["D10"]. "will I have children?" → ["D7"]. "what are my hidden
  strengths?" → ["D27"]. A broad question ("tell me about my life") may
  list several. A question about today's timing or general astrology
  concepts needs none — return an empty list rather than guessing.

When the question is about Vimshottari dasha timing (any "fact"-intent
question naming dasha, mahadasha, antardasha/bhukti, or pratyantardasha),
also decide which level of the dasha hierarchy the seeker actually means —
do not guess from keywords, read what they are actually asking about:
- "dasha_level": "maha" (they said/meant only the Mahadasha — "what
  mahadasha am I in", "when does my Saturn mahadasha end"), "antar" (they
  named the Antardasha/bhukti specifically, or asked about the sub-period
  within a stated mahadasha), "pratyantar" (they named the Pratyantardasha,
  or asked for this level of granularity — "day to day", "right now
  precisely"), or "all" (they asked generally — "what dasha am I running",
  "explain my current dasha period" — with no specific level named, or the
  question needs the full maha→antar→pratyantar chain to answer). "none"
  when the question is not about dasha at all.

Also rewrite the question into an optimised semantic search query for
retrieving pages from classical Sanskrit texts in English translation:
preserve Sanskrit terms (dasha, lagna, yoga), and name the relevant houses,
planetary significators and timing indicators.

Also extract STATED FACTS: things the seeker asserts about their own life,
as distinct from what they are asking. "I got married on 22nd Nov 2025. When
will I have a child" states one fact (the marriage, dated) and asks one
question (the child). "I am working in an IT company as a Product Owner. Its
been 5 yrs in the job" states two.

Extract only what the seeker asserts as already true. A hope, a fear, a
hypothetical or the question itself is not a stated fact. Give "when" as
YYYY-MM-DD, or YYYY-MM, or YYYY when only the year is known, or "" when the
fact carries no date. Resolve relative dates ("next month", "5 yrs in the job")
against the current date where you can, and leave "when" empty where you
cannot. Keep "text" to a short phrase in the third person. Return [] when the
seeker states nothing about themselves.

Return ONLY a JSON object (no markdown, no explanation):
{
  "is_smalltalk_or_gibberish": <true|false>,
  "primary_rishi": "<one of: agam|vyom|dhruvan|ritam|tejan|medhan|tattvan|pragnav>",
  "query_domain": "<natal|muhurta|prashna|general>",
  "needs_birth_data": <true|false>,
  "confidence": <0.0-1.0>,
  "reasoning": "<one sentence>",
  "supporting_rishis": ["<optional secondary rishis who may contribute>"],
  "search_query": "<the optimised retrieval query>",
  "intent": "<chart|fact>",
  "chart_type": "<varga|numerology|ashtakavarga|dasha|shadbala — only meaningful when intent is chart>",
  "varga_code": "<D1|D2|D3|D4|D7|D9|D10|D12|D16|D20|D24|D27|D30|D40|D45|D60 — only meaningful when chart_type is varga>",
  "relevant_vargas": ["<codes from D2|D3|D4|D7|D9|D10|D12|D16|D20|D24|D27|D30|D40|D45|D60 — only meaningful when intent is fact; [] if none apply>"],
  "dasha_level": "<maha|antar|pratyantar|all|none — only meaningful when intent is fact>",
  "stated_facts": [{"text": "<short third-person phrase>", "when": "<YYYY-MM-DD|YYYY-MM|YYYY|>"}]
}
"""


_FOLLOWUP_PROMPT = """\

ONGOING CONVERSATION — the seeker is already speaking with {current_rishi}:
{transcript}

If this new message continues that thread (a reply, a "yes", a request to open
what was withheld, or a question about the same subject), set "is_followup":
true and keep "primary_rishi" as "{current_rishi}" — switching Rishi mid-thread
breaks the illusion of one continuous conversation. Only route to a different
Rishi if the seeker has clearly moved to a new subject.
Add the field: "is_followup": <true|false>
"""


def _clean_stated_facts(raw) -> list[dict]:
    """Model output, so shaped rather than trusted.

    A fact with no text is not a fact; anything that is not a dict is not one
    either. Both are dropped rather than raised on - a malformed entry here must
    not cost the seeker their answer, and the question is still answerable
    without the fact that failed to parse.
    """
    if not isinstance(raw, list):
        return []
    facts: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        facts.append({"text": text, "when": str(entry.get("when") or "").strip()})
    return facts[:6]


def classify_query(
    client,
    question: str,
    model: str = "gemini-2.0-flash",
    conversation=None,
) -> dict:
    """Classify a question and return the Rishi routing result.

    When ``conversation`` has turns, routing also decides whether this message
    continues the existing thread — folded into this call rather than a second
    round-trip.
    """
    prompt = _CLASSIFY_PROMPT
    if conversation is not None and not conversation.is_empty:
        prompt += _FOLLOWUP_PROMPT.format(
            current_rishi=conversation.current_rishi,
            transcript=conversation.render(limit=2),
        )
    try:
        response = client.models.generate_content(
            model=model,
            contents=f"{prompt}\n\nUser question: {question}",
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(raw)

        is_smalltalk_or_gibberish = bool(result.get("is_smalltalk_or_gibberish", False))

        rishi = result.get("primary_rishi", "vyom").lower()
        if rishi not in ALL_RISHI_NAMES:
            rishi = "vyom"

        domain = QueryDomain(result.get("query_domain", "general"))
        # print(f"=========. domain classified by orchestrator is {domain}")
        intent = result.get("intent", "fact")
        if intent not in ("chart", "fact"):
            intent = "fact"
        chart_type = result.get("chart_type", "varga")
        if chart_type not in _CHART_TYPES:
            # NOT silently "varga". That default is what turned "show me my
            # shadbala chart" into a D1 Rashi table: an unknown kind became
            # varga, and varga_code then defaulted to D1. `unsupported` routes
            # to a node that says which chart it cannot draw.
            chart_type = "unsupported"
        varga_code = str(result.get("varga_code", "D1")).upper()
        if varga_code not in _VARGA_CODES:
            varga_code = "D1"

        # D1 is always included separately (see facts.py::derive_facts), so
        # drop it here to avoid asking for the same placements twice; cap
        # the rest since each extra varga costs prompt size and retrieval
        # latency (see MAX_FACT_QUERIES in orchestrator.py).
        raw_vargas = result.get("relevant_vargas") or []
        if not isinstance(raw_vargas, list):
            raw_vargas = []
        relevant_vargas = [
            c for c in (str(v).upper() for v in raw_vargas)
            if c in _VARGA_CODES and c != "D1"
        ][:4]

        stated_facts = _clean_stated_facts(result.get("stated_facts"))

        dasha_level = str(result.get("dasha_level", "none")).lower()
        if dasha_level not in ("maha", "antar", "pratyantar", "all", "none"):
            dasha_level = "none"

        # Keep the thread with one Rishi even if the model forgot to.
        is_followup = bool(result.get("is_followup", False))
        if conversation is not None and not conversation.is_empty:
            if not is_followup:
                is_followup = is_probable_followup(question, conversation)
            if is_followup:
                rishi = conversation.current_rishi or rishi
        # Logged rather than printed: it fired on every request and shared
        # stdout with the direct lane's prompt dump, which is there to be
        # copy-pasted into other platforms.
        logger.debug(
            "classified: rishi=%s domain=%s supporting=%s intent=%s "
            "varga=%s relevant_vargas=%s dasha_level=%s",
            rishi, domain, result.get("supporting_rishis", []), intent,
            varga_code, relevant_vargas, dasha_level,
        )
        return {
            "is_smalltalk_or_gibberish": is_smalltalk_or_gibberish,
            "primary_rishi": rishi,
            "query_domain": domain,
            "needs_birth_data": bool(result.get("needs_birth_data", False)),
            "confidence": float(result.get("confidence", 0.5)),
            "reasoning": result.get("reasoning", ""),
            "supporting_rishis": result.get("supporting_rishis", []),
            # Folded in from what used to be a second, serial LLM round-trip.
            "search_query": (result.get("search_query") or question).strip(),
            "is_followup": is_followup,
            "intent": intent,
            "chart_type": chart_type,
            "varga_code": varga_code,
            "relevant_vargas": relevant_vargas,
            "dasha_level": dasha_level,
            # What the seeker said about their own life, as opposed to what they
            # asked. Answering without it produced a reading that told a man who
            # had just said he married in November 2025 that his marriage window
            # opens in 2030.
            "stated_facts": stated_facts,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rishi classification failed (%s) — defaulting to Vyom/general", exc)
        # Mid-conversation, dropping the seeker onto a different Rishi is more
        # jarring than a wrong domain, so hold the current one.
        return {
            # Classification failed outright — never guess smalltalk on
            # error; that would silently downgrade a real question someone
            # is paying attention to into a throwaway warm reply.
            "is_smalltalk_or_gibberish": False,
            "primary_rishi": (conversation.current_rishi
                              if conversation is not None
                              and not conversation.is_empty else "vyom"),
            "query_domain": QueryDomain.GENERAL,
            "needs_birth_data": False,
            "confidence": 0.0,
            "reasoning": f"Classification error: {exc}",
            "supporting_rishis": [],
            "search_query": question,
            # On failure, stay with whoever the seeker was already talking to.
            "is_followup": is_probable_followup(question, conversation),
            # Classification failed outright — default to the normal
            # Rishi-voiced path rather than guessing at a chart display.
            "intent": "fact",
            "chart_type": "varga",
            "varga_code": "D1",
            # Classification failed outright — no signal on relevance, so
            # add nothing rather than guess.
            "relevant_vargas": [],
            "dasha_level": "none",
            # Every consumer does a plain lookup on this key. Omitting it on the
            # error path moves the failure three nodes downstream, into a broad
            # `except`, where it is indistinguishable from the feature not
            # existing.
            "stated_facts": [],
        }
