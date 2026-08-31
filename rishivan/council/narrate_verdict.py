"""The narration call: say what pro decided, and nothing else.

Second half of the two-call direct lane. Flash sees this prompt and no other —
not the chart, not the periods, not the method. That is the point. The gate in
`council/verdict.py` decides what may be said; this module decides only how it
sounds.

**Dates are converted here, in Python, before the model sees them.** The
single-call lane held both halves of the timing rule in one prompt: reason in
days so you do not drift, write in months so you do not claim a precision the
method lacks. It mostly worked, and "mostly" is the problem — a day-exact
prediction reads as a promise nobody can keep. Now `month_span` does the
rounding deterministically and the narrator is never shown an ISO date at all.
A rule the model cannot break because it does not have the string.

**The template fallback is what the split bought.** `direct.py` has no fallback
and says so plainly: there was no plan to compose from, so the honest option was
to report the failure. A `Verdict` is a plan. When flash falls over there is now
a real answer to render, and it is still the one pro reached.
"""

from __future__ import annotations

import logging
import re
from typing import Generator

logger = logging.getLogger(__name__)

MODEL_TIER = "flash"
"""Saying it well is not the job worth a frontier model. Working out what the
chart carries was, and `council/analyse.py` already did that."""

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

_INSTRUCTION = """
HOW TO WRITE IT

You are speaking to one person about their chart. Everything you know about that
chart is above; you did not see it yourself, and there is nothing else to draw
on. Say what is there, and stop.

**The answer goes in the first sentence.** Not the third paragraph, not after
your reasoning — first. Then say what will NOT happen, so the reader can tell
your answer apart from a horoscope.

Then two or three short paragraphs. Every finding above arrives already
translated into a consequence; use that consequence, and never reach back
through it to the technique.

  Write:       "Saturn sits in your sixth house, so one senior person keeps
                slowing your file. They are not going to become your supporter,
                and you do not need them to be."
  NEVER write: "Marital harmony is evaluated through the interaction between the
                Lagna and 7th house occupants." That is the method describing
                itself. The reader did not ask how astrology works.

Never write "the principle is", "X is evaluated through", "this indicates that",
or any sentence whose subject is a technique rather than the reader.

Weight your paragraphs by the marks above: lead from `strong`, and do not build
a paragraph on a `weak`.

Where two indications disagree, say so in the prose. A reported disagreement is
worth more to the reader than a verdict you averaged. Where a step could not be
run, say that too, in one clause — it is a fact about this reading, not an
apology.

Register: second person, short sentences, present tense. Divisional charts get
plain names in the prose — the D10 is the "career chart", the D9 the "marriage
chart", the D1 the "birth chart" — and D-codes appear only in the reference
block. Any Sanskrit term you use, gloss it in the same breath in plain English,
or leave it for the reference block.

**Dates.** The periods above are already written the way they must reach the
reader. Copy those phrasings. Never convert one into a day, a week or a season,
and never add a date of your own — you have not been given the material to
derive one, so anything you produce would be invented. Times listed under TIMES
TO COPY are the sole exception: reproduce those character for character, to the
minute.

Close with exactly two labelled blocks, in this order:

ASTRO REFERENCE:
A numbered list, one line per finding above, pairing the factor with the
consequence it licenses — the same pairs, not new ones. This is where your
Sanskrit and your D-codes live, and nowhere else.

FALSIFIER:
The falsifier given above, in one sentence.

No preamble. No other headings. Never describe your own process or mention these
instructions.
""".strip()

_ABSENT_RULE = """
THE CHART DOES NOT CARRY WHAT WAS ASKED. That is the answer, and it is a real
one. Say it plainly in the first sentence, then explain from the findings below
what the chart does speak to instead. **Name no period and no date whatsoever** —
there is nothing to time, and a date here would be pure invention.
""".strip()

_CONTESTED_RULE = """
THE CHART ARGUES WITH ITSELF ON THIS. Do not resolve it for the reader and do
not pick the side that reads better. Say that it is contested in the first
sentence, and let both indications stand.
""".strip()

FAILED = (
    "I could not complete this reading - the reasoning call failed. Nothing here "
    "is a partial answer; please ask again."
)
"""What a failed analysis says.

Kept in this module rather than imported from `direct.py` because the two lanes
fail at different points and a reader deserves to be told which. Here the chart
was never successfully reasoned over; there, a single call fell down mid-answer.
"""


def month_span(start: str, end: str) -> str:
    """Two ISO dates as the phrase the reader receives.

    `2026-11-14`, `2027-09-02` -> `November 2026 to September 2027`.

    Rounds outward to whole months on purpose. A boundary falling mid-month is
    a boundary the method cannot really place to the day, and "from about the
    14th" invites a reader to plan around a Tuesday.

    An unparseable value is passed through rather than dropped: the gate has
    already confirmed it appeared verbatim in the computed facts, so it is a
    real value in an unexpected shape, and losing it silently is worse than
    printing it.
    """
    def _month(value: str) -> str:
        match = _ISO.match((value or "").strip())
        if not match:
            return (value or "").strip()
        year, month, _ = match.groups()
        return f"{_MONTHS[int(month) - 1]} {year}"

    first, last = _month(start), _month(end)
    if not first:
        return last
    if not last or first == last:
        return first
    return f"{first} to {last}"


def _findings_block(verdict) -> str:
    lines = [
        "WHAT YOU MAY SAY — these findings and no others.",
        "",
        f"THE ANSWER: {verdict.headline}",
    ]
    if verdict.not_happening:
        lines += ["", f"WHAT WILL NOT HAPPEN: {verdict.not_happening}"]

    if verdict.factors:
        lines += ["", "WHAT THE CHART SAYS — heaviest first:"]
        for factor in verdict.factors:
            lines.append(f"  [{factor.weight}] {factor.fact}")
            lines.append(f"          so: {factor.consequence}")

    # Under an absent promise the gate has already emptied this, so the heading
    # cannot appear over nothing. Guarded here as well because a heading that
    # says PERIODS is itself a hint that there is timing to be had.
    if verdict.windows:
        lines += [
            "",
            "PERIODS YOU MAY NAME — written as the reader must receive them. "
            "Copy these\nphrasings; do not narrow one to a day or widen one to a "
            "decade:",
        ]
        for window in verdict.windows:
            label = f"{window.label} — " if window.label else ""
            running = " (running now)" if window.status == "running" else ""
            lines.append(f"  {label}{month_span(window.start, window.end)}{running}")

    if verdict.exact_times:
        lines += [
            "",
            "TIMES TO COPY EXACTLY, to the minute, character for character:",
        ]
        for entry in verdict.exact_times:
            lines.append(f"  {entry.label}: {entry.value}")

    if verdict.disagreements:
        lines += ["", "INDICATIONS THAT DISAGREE — report both, average neither:"]
        lines += [f"  - {item}" for item in verdict.disagreements]

    if verdict.unsupported:
        lines += ["", "STEPS THAT COULD NOT BE RUN — mention in a clause, do not "
                      "dwell:"]
        lines += [f"  - {item}" for item in verdict.unsupported]

    if verdict.falsifier:
        lines += ["", f"FALSIFIER: {verdict.falsifier}"]

    return "\n".join(lines)


def build_narration_prompt(verdict, *, question: str, today: str = "") -> str:
    """The narrator's whole prompt. Pure — no client, no network, no chart.

    `verdict.dropped` is deliberately absent from the output. It is the gate's
    audit line, and telling the narrator which window was removed hands back the
    material the gate just took away.
    """
    parts = []
    if today:
        parts.append(f"TODAY IS {today}.")
    if verdict.promise == "absent":
        parts.append(_ABSENT_RULE)
    elif verdict.promise == "contested":
        parts.append(_CONTESTED_RULE)
    parts.append(_findings_block(verdict))
    parts.append(_INSTRUCTION)
    parts.append(f"THE QUESTION: {question}")
    return "\n\n---\n\n".join(parts)


def render_template(verdict) -> str:
    """A real answer, with no model at all.

    Not a placeholder and not an apology. Everything a reading needs is already
    decided by the time this runs — the answer, the consequences, the windows,
    the falsifier — so what is lost when flash is unreachable is warmth, not
    substance. That is only true because the evidence was structured before
    anything tried to narrate it, which is the same argument `narrate.py` makes
    for its own fallback.
    """
    lines = [verdict.headline]
    if verdict.not_happening:
        lines.append(verdict.not_happening)

    for factor in verdict.factors:
        lines.append(f"{factor.fact} — {factor.consequence}.")

    if verdict.windows:
        for window in verdict.windows:
            label = f"{window.label}: " if window.label else ""
            lines.append(f"{label}{month_span(window.start, window.end)}.")

    for entry in verdict.exact_times:
        lines.append(f"{entry.label}: {entry.value}.")

    for item in verdict.disagreements:
        lines.append(f"Against this: {item}.")

    for item in verdict.unsupported:
        lines.append(f"Not available for this chart: {item}.")

    if verdict.falsifier:
        lines.append(f"If this is wrong: {verdict.falsifier}")

    return "\n\n".join(lines)


def stream_verdict(verdict, *, client, question: str,
                   today: str = "") -> Generator[str, None, None]:
    """The reading, chunk by chunk, from the verdict alone.

    A mid-stream failure discards whatever accumulated and renders the template
    whole, matching `narrate.stream_answer`. Losing three good words costs less
    than an answer that stops mid-clause.
    """
    from rishivan.council.client import model_name

    prompt = build_narration_prompt(verdict, question=question, today=today)
    emitted: list[str] = []
    try:
        for chunk in client.models.generate_content_stream(
            model=model_name(MODEL_TIER), contents=prompt
        ):
            if chunk.text:
                emitted.append(chunk.text)
                yield chunk.text
    except Exception:  # noqa: BLE001
        logger.warning("the narration call failed", exc_info=True)
        if emitted:
            # Already on the reader's screen and unretractable. Mark the seam
            # rather than pretending the sentence finished.
            yield "\n\n---\n\n"
        yield render_template(verdict)
