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
- "chart_type": "varga" (a divisional birth chart), "numerology" (mulank/
  bhagyaank), or "ashtakavarga" (the benefic bindu/point table — NOT a
  divisional chart, so never map "ashtakavarga"/"sarvashtakavarga"/"bindu
  table"/"SAV" requests to varga_code "D1" or any other D-code). Default
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

Also rewrite the question into an optimised semantic search query for
retrieving pages from classical Sanskrit texts in English translation:
preserve Sanskrit terms (dasha, lagna, yoga), and name the relevant houses,
planetary significators and timing indicators.

Return ONLY a JSON object (no markdown, no explanation):
{
  "primary_rishi": "<one of: agam|vyom|dhruvan|ritam|tejan|medhan|tattvan|pragnav>",
  "query_domain": "<natal|muhurta|prashna|general>",
  "needs_birth_data": <true|false>,
  "confidence": <0.0-1.0>,
  "reasoning": "<one sentence>",
  "supporting_rishis": ["<optional secondary rishis who may contribute>"],
  "search_query": "<the optimised retrieval query>",
  "intent": "<chart|fact>",
  "chart_type": "<varga|numerology|ashtakavarga — only meaningful when intent is chart>",
  "varga_code": "<D1|D2|D3|D4|D7|D9|D10|D12|D16|D20|D24|D27|D30|D40|D45|D60 — only meaningful when chart_type is varga>",
  "relevant_vargas": ["<codes from D2|D3|D4|D7|D9|D10|D12|D16|D20|D24|D27|D30|D40|D45|D60 — only meaningful when intent is fact; [] if none apply>"]
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

        rishi = result.get("primary_rishi", "vyom").lower()
        if rishi not in ALL_RISHI_NAMES:
            rishi = "vyom"

        domain = QueryDomain(result.get("query_domain", "general"))

        intent = result.get("intent", "fact")
        if intent not in ("chart", "fact"):
            intent = "fact"
        chart_type = result.get("chart_type", "varga")
        if chart_type not in ("varga", "numerology", "ashtakavarga"):
            chart_type = "varga"
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

        # Keep the thread with one Rishi even if the model forgot to.
        is_followup = bool(result.get("is_followup", False))
        if conversation is not None and not conversation.is_empty:
            if not is_followup:
                is_followup = is_probable_followup(question, conversation)
            if is_followup:
                rishi = conversation.current_rishi or rishi

        return {
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
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Rishi classification failed (%s) — defaulting to Vyom/general", exc)
        # Mid-conversation, dropping the seeker onto a different Rishi is more
        # jarring than a wrong domain, so hold the current one.
        return {
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
        }
