"""A second Rishi's brief perspective — the real backend's P4 council graph
earns up to two secondary voices per answer when a different tradition/
persona has independent, confident support; this is that idea at demo
scale: at most one secondary voice, and only when the SAME classification
call that routed the primary Rishi already named a plausible supporting one
with real confidence — this never costs a second classification round-trip,
only (at most) one extra, short generation call.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MIN_CONFIDENCE_FOR_SECOND_VOICE = 0.6


def pick_secondary_rishi(classification: dict, primary_rishi: str) -> str | None:
    """The first supporting Rishi that both exists and differs from the primary.

    None whenever the primary routing wasn't confident enough to trust a
    second opinion on top of it, or no distinct supporting Rishi was named.
    """
    if classification.get("confidence", 0) < MIN_CONFIDENCE_FOR_SECOND_VOICE:
        return None

    from rishivan.council.personas import ALL_RISHI_NAMES

    for candidate in classification.get("supporting_rishis") or []:
        candidate = str(candidate).strip().lower()
        if candidate and candidate != primary_rishi and candidate in ALL_RISHI_NAMES:
            return candidate
    return None


def build_secondary_prompt(
    rishi_name: str, question: str, context: str, chart_facts: list[str] | None
) -> str:
    from rishivan.council.personas import get_persona

    persona = get_persona(rishi_name)
    facts_text = (
        "\n".join(f"- {f}" for f in chart_facts)
        if chart_facts
        else "No personal chart data was provided for this reading."
    )
    return f"""
{persona.identity}

You are offering a brief SECOND perspective in the Council, after another
Rishi has already given the seeker the main reading. Speak only 2-4
sentences — a short, additional insight from your own domain of expertise
({persona.focus}), not a full reading. Do not repeat what a general answer
would already cover, and do not contradict the main reading without cause.
No headers, no bullet points, no sign-off, no "as the second Rishi" framing
— just speak naturally in your own voice.

SEEKER'S CHART FACTS:
{facts_text}

SOURCE PAGES (use only if directly relevant to your brief addition):
{context}

The seeker asked: {question}
""".strip()


def generate_secondary_voice(
    client,
    model: str,
    rishi_name: str,
    question: str,
    context: str,
    chart_facts: list[str] | None,
) -> str | None:
    """A short, best-effort second voice. Never raises — a bonus is not a
    reason to fail a reading that otherwise succeeded."""
    try:
        prompt = build_secondary_prompt(rishi_name, question, context, chart_facts)
        response = client.models.generate_content(model=model, contents=prompt)
        text = (response.text or "").strip()
        return text or None
    except Exception as exc:  # noqa: BLE001 — a second voice is a bonus, never fatal
        logger.warning("Secondary voice generation failed (%s) — omitting", exc)
        return None


def maybe_generate_secondary_voice(
    result: dict, client, model: str, question: str
) -> dict | None:
    """Convenience wrapper for the caller: given orchestrator.council_consult's
    result dict, decide and (if warranted) generate the second voice.

    Call this only after the primary answer has finished streaming — it is a
    blocking generation call, and running it earlier would delay the first
    token of the primary answer. Returns ``{"rishi": ..., "body": ...}`` or
    None; never raises.
    """
    classification = result.get("classification") or {}
    primary_rishi = result.get("primary_rishi", "")
    secondary_rishi = pick_secondary_rishi(classification, primary_rishi)
    if secondary_rishi is None:
        return None

    body = generate_secondary_voice(
        client,
        model,
        secondary_rishi,
        question,
        result.get("_context_text", ""),
        result.get("chart_facts"),
    )
    if not body:
        return None
    return {"rishi": secondary_rishi, "body": body}
