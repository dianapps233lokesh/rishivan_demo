"""The warmth node — an LLM-only reply for small talk and gibberish.

Reached before any chart computation or RAG retrieval (see orchestrator.py's
early bypass, gated on the classifier's ``is_smalltalk_or_gibberish`` field):
a "hi", a "thanks", or a keysmash should never cost a Swiss Ephemeris chart
or a Qdrant search. This node speaks as the Council's welcoming voice, not
as a specific Rishi persona — the classifier deliberately does not route
these messages to a domain, so there is no persona to embody here.
"""

from __future__ import annotations

from collections.abc import Generator

_WARMTH_SYSTEM_PROMPT = """
You are the warm, welcoming voice of the Rishivan Council of Rishis — eight
sages of Vedic astrology who read birth charts and classical texts. The
seeker's message was not an astrology question: it was a greeting, thanks,
farewell, casual small talk, or something unclear or nonsensical.

Reply briefly — one to three sentences — warmly and naturally, like a kind
host greeting someone at the door of a sacred space. Do not pretend to read
their chart or invent an astrological observation; you have none to give
here. If their message was unclear or nonsensical, gently invite them to
share what is actually on their mind, or ask a question about their birth
chart, timing, or Vedic astrology.

Never break character into an AI-assistant voice ("As an AI...", "I'm here
to help..."). No bullet points, no headers, no sign-off. If the seeker
wrote in Hindi or Hinglish, reply in the same language and script.
""".strip()


def build_warmth_prompt(question: str, conversation=None) -> str:
    """Assemble the warmth-node prompt: system voice + optional continuity + message."""
    from rishivan.council.conversation import continuity_instruction

    parts = [_WARMTH_SYSTEM_PROMPT]
    history_block = continuity_instruction(conversation)
    if history_block:
        parts.append(history_block)
    parts.append(f"The seeker just said: {question}")
    return "\n\n---\n\n".join(parts)


def respond_warmly(
    client, question: str, model: str, conversation=None
) -> Generator[str, None, None]:
    """Stream a warm, LLM-only reply — no chart facts, no retrieved context."""
    prompt = build_warmth_prompt(question, conversation)
    for chunk in client.models.generate_content_stream(model=model, contents=prompt):
        if chunk.text:
            yield chunk.text
