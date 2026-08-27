"""One call, one answer, and the prompt on screen.

The dump is not debug output. This lane exists to be compared against ChatGPT,
Gemini and Claude in a browser, and a comparison is only worth running if the
prompt can be pasted into all four places unchanged. So it goes to stdout, it is
delimited, and it is not gated on DEBUG.

Printed immediately BEFORE the call, so what is on screen is provably the string
that was sent - and so a prompt that makes the model fall over is still there to
look at afterwards.
"""

from __future__ import annotations

import logging
from typing import Generator

logger = logging.getLogger(__name__)

MODEL_TIER = "flash"
"""Same tier as the retrieval lane, deliberately. The comparison is about
grounding and the model's own knowledge; changing the tier at the same time
would leave two variables and one result."""

THINKING_BUDGET = -1
"""Dynamic. The right budget for "what colour should I wear" and for "will I
have children" are not the same number, and the model is better placed to judge
that than a constant is.

Verified accepted by google-genai 2.18.1; the only other in-repo use is
`thinking_budget=0` in `knowledge/extract/runner.py`, which turns thinking off
for a graded extraction run and is a different decision entirely.
"""

TEMPERATURE = 0.0
"""Reproducibility. The same prompt must produce the same reading twice, or a
comparison against three other platforms measures sampling noise as though it
were astrology."""

FAILED = (
    "I could not complete this reading - the model call failed partway through. "
    "Nothing here is a partial answer; please ask again."
)
"""What a failure says.

There is no template fallback in this lane. `narrate.render_template` composes
prose from an `AnswerPlan`, and this lane has no plan - so the honest option is
to say the call failed rather than to compose something over nothing.
"""


def _echo(prompt: str) -> None:
    """The prompt, delimited for copying.

    `print` rather than the logger on purpose: a logger's level, handlers and
    format are all things that can silence this, and being silenced defeats the
    only reason it exists. Under Streamlit this lands in the terminal running
    the server, which is where it is wanted.
    """
    rule = "=" * 78
    banner = f"DIRECT PROMPT - {len(prompt):,} chars, ~{len(prompt) // 4:,} tokens"
    print(
        f"\n{rule}\n{banner}\n{rule}\n{prompt}\n{rule}\nEND DIRECT PROMPT\n{rule}\n",
        flush=True,
    )


def stream_direct(
    prompt: str, *, client, echo: bool = True
) -> Generator[str, None, None]:
    """The reading, chunk by chunk.

    A mid-stream failure discards whatever accumulated rather than leaving half
    a sentence on the reader's screen - the same call `narrate.stream_answer`
    makes, and for the same reason: losing three good words costs less than an
    answer that stops mid-clause.
    """
    from google.genai import types

    from rishivan.council.client import model_name

    if echo:
        _echo(prompt)

    emitted: list[str] = []
    try:
        for chunk in client.models.generate_content_stream(
            model=model_name(MODEL_TIER),
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=TEMPERATURE,
                thinking_config=types.ThinkingConfig(
                    thinking_budget=THINKING_BUDGET
                ),
            ),
        ):
            if chunk.text:
                emitted.append(chunk.text)
                yield chunk.text
    except Exception:  # noqa: BLE001
        logger.warning("the direct reading call failed", exc_info=True)
        if emitted:
            # Already on the reader's screen and unretractable. Mark the seam
            # rather than pretending the sentence finished.
            yield "\n\n---\n\n"
        yield FAILED
