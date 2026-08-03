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
  "search_query": "<the optimised retrieval query>"
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
        }
