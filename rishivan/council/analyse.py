"""The reasoning call. One model, one schema, no prose.

This is the first half of the two-call direct lane. It sends the same chart, the
same method and the same facts the single-call lane sends, closes with a
different OUTPUT block, and forces the answer through `VERDICT_SCHEMA` — so what
comes back is a decision rather than a paragraph, and the gate in
`council/verdict.py` can act on it before any of it reaches a reader.

Split from the prompt builder for the same reason `direct.py` is: the builder is
a pure function that can be snapshotted without credentials, and the call is the
part that needs them. Split from the narration for a different reason — what
this returns is plain data, so it can live in graph state and be checkpointed,
which a live stream cannot.
"""

from __future__ import annotations

import logging

from rishivan.council.verdict import VERDICT_SCHEMA, VerdictError, parse_verdict

logger = logging.getLogger(__name__)

MODEL_TIER = "pro"
"""The reason this lane exists.

Working out what a chart carries and writing it warmly are different jobs, and
only the first is worth a frontier model. If this silently ran on flash the
second call would be an extra round trip that bought nothing.
"""

THINKING_BUDGET = -1
"""Dynamic, matching `direct.py`. A "what colour should I wear" and a "will I
have children" do not deserve the same budget, and the model judges that better
than a constant does."""

TEMPERATURE = 0.0
"""Reproducibility. The same chart must yield the same verdict twice, or the
comparison against the single-call lane measures sampling noise."""

ATTEMPTS = 2
"""One retry, and no more.

A model that has failed the schema twice at temperature 0 is not going to pass
it on the third try, and a lane that keeps paying pro to find out is a lane that
turns a bad turn into an expensive one.
"""

RETRY_PREFACE = (
    "\n\n---\n\nYOUR PREVIOUS RESPONSE COULD NOT BE READ.\n\n"
    "The problem: "
)
"""Why the retry is not simply the same call again.

At temperature 0 an identical prompt produces an identical failure, so a blind
retry buys a second invoice and nothing else. The parse error travels back.
"""


def _echo(prompt: str) -> None:
    """The analysis prompt, delimited, on stdout.

    Same reasoning as `direct._echo`: a logger's level and handlers are all
    things that can silence this, and being silenced defeats the only reason it
    exists. This lane cannot be pasted into a browser chat — the schema does not
    travel — but the prompt is still the first thing to look at when a verdict
    comes back wrong.
    """
    rule = "=" * 78
    banner = f"ANALYSIS PROMPT - {len(prompt):,} chars, ~{len(prompt) // 4:,} tokens"
    print(
        f"\n{rule}\n{banner}\n{rule}\n{prompt}\n{rule}\nEND ANALYSIS PROMPT\n{rule}\n",
        flush=True,
    )


def _call(prompt: str, *, client) -> str:
    from google.genai import types

    from rishivan.council.client import model_name

    print(f"================prompt is {prompt}")

    response = client.models.generate_content(
        model=model_name(MODEL_TIER),
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=TEMPERATURE,
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
            response_mime_type="application/json",
            response_schema=VERDICT_SCHEMA,
        ),
    )
    return getattr(response, "text", "") or ""


def analyse(prompt: str, *, client, echo: bool = True):
    """The chart, reasoned over, as a `Verdict`.

    Raises `VerdictError` when both attempts fail — including when the transport
    failed rather than the model, so the caller has one thing to catch and does
    not have to tell "unreachable" apart from "incoherent" to decide what to do.

    **Nothing is repaired here and nothing falls back.** A half-understood
    verdict narrated confidently is worse than a turn that says it failed,
    because the failure is visible to the reader and the repair is not.
    """
    if echo:
        _echo(prompt)

    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        body = prompt if last is None else f"{prompt}{RETRY_PREFACE}{last}"
        try:
            return parse_verdict(_call(body, client=client))
        except VerdictError as exc:
            last = exc
            logger.warning("the reasoning call returned an unusable verdict: %s", exc)
        except Exception as exc:  # noqa: BLE001
            last = exc
            logger.warning("the reasoning call failed", exc_info=True)
        if attempt + 1 < ATTEMPTS:
            logger.info("retrying the reasoning call with the parse error attached")

    raise VerdictError(f"the reasoning call failed after {ATTEMPTS} attempts: {last}")
