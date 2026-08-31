"""What the reasoning call decided, as data the narrator cannot exceed.

The single-call direct lane asked one model to work out the answer and write it
nicely in the same breath, which meant nothing checked the working. This module
is the seam between those two jobs: pro emits a `Verdict`, a gate written in
plain Python removes anything pro was not entitled to say, and flash narrates
what survives and nothing else.

**The gate is subtractive, and that is the whole mechanism.** It never rewrites,
never softens and never adds. A window whose dates the prompt did not print is
removed rather than hedged, because a narrator cannot cite what it was never
shown — the same argument `answer_plan` makes for `plan.allowed`, applied to a
lane that has no rule base to draw its licence from.

Pure. No client, no network, no database — so the contract can be tested, and
broken, for free.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace

PROMISES = ("carried", "absent", "contested")
"""Does the chart carry the thing asked about at all?

Settled before any date exists, and a field rather than a paragraph so the gate
can act on it: under `absent` there is nothing to time, and every window goes.
The single-call prompt asked for this ordering in prose and got it most of the
time; making it structural gets it every time.
"""

STATUSES = ("past", "running", "future")

WEIGHTS = ("strong", "moderate", "weak")

_GRAHAS = (
    "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu",
)

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)


class VerdictError(ValueError):
    """Pro returned something this lane cannot narrate from.

    Raised rather than repaired. A half-understood verdict is worse than a
    failed turn, because the failure is visible and the repair is not.
    """


@dataclass(frozen=True, slots=True)
class Factor:
    """One computed fact, already translated into something the seeker can check.

    Both halves are required. `fact` alone is a placement, and a placement is
    exactly what the prose rules forbid the narrator from printing: "Saturn sits
    in your sixth house" is the method describing itself. Carrying the
    consequence across the seam means flash is never in a position to invent one.
    """

    fact: str
    consequence: str
    weight: str = "moderate"


@dataclass(frozen=True, slots=True)
class Window:
    """A period, in ISO dates, with its position relative to now.

    Dates cross the seam exact and leave it rounded. Pro needs the boundaries to
    the day to reason without drifting; the seeker gets months, because a
    day-exact prediction claims a precision this method does not have. The
    single-call prompt asked one model to hold both rules at once. Here the
    split enforces them.
    """

    start: str
    end: str
    label: str = ""
    status: str = "future"


@dataclass(frozen=True, slots=True)
class ExactTime:
    """Arithmetic for a stated date — Rahu Kaal, a hora, sunrise.

    Separated from `windows` because the rule governing it is the opposite one:
    these are copied to the minute, character for character, and rounding them
    to a month would destroy the answer rather than protect it.
    """

    label: str
    value: str


@dataclass(frozen=True, slots=True)
class Verdict:
    """The reasoning call's whole output, after the gate has run.

    `dropped` is an audit line, not a message: it records what the gate removed
    and why, so a trace can show that a date never reached the reader and say
    which one. It is never shown to the seeker and never reaches the narration
    prompt.
    """

    promise: str
    headline: str
    not_happening: str = ""
    factors: tuple[Factor, ...] = ()
    windows: tuple[Window, ...] = ()
    exact_times: tuple[ExactTime, ...] = ()
    disagreements: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()
    falsifier: str = ""
    dropped: tuple[str, ...] = field(default=())


VERDICT_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "promise": {
            "type": "STRING",
            "enum": list(PROMISES),
            "description": (
                "Does the chart carry the thing asked about at all? Settle this "
                "before any date exists. 'absent' means there is nothing to time "
                "and saying so is the answer."
            ),
        },
        "headline": {
            "type": "STRING",
            "description": (
                "One sentence: the answer itself. Not a summary of your "
                "reasoning, not a preamble. If the promise is absent, this "
                "sentence says so."
            ),
        },
        "not_happening": {
            "type": "STRING",
            "description": (
                "What will NOT occur, so the reader can tell a forecast from a "
                "horoscope. Empty if the question does not admit one."
            ),
        },
        "factors": {
            "type": "ARRAY",
            "description": (
                "Each computed factor paired with the consequence it licenses. "
                "Every 'fact' must trace to a line printed above; if you cannot "
                "point at the line, leave it out."
            ),
            "items": {
                "type": "OBJECT",
                "properties": {
                    "fact": {
                        "type": "STRING",
                        "description": (
                            "The placement, period, transit or condition, as "
                            "printed above. Sanskrit and D-codes belong here."
                        ),
                    },
                    "consequence": {
                        "type": "STRING",
                        "description": (
                            "What it does to the seeker, in terms they could "
                            "check against their own life. Never what it is."
                        ),
                    },
                    "weight": {"type": "STRING", "enum": list(WEIGHTS)},
                },
                "required": ["fact", "consequence"],
            },
        },
        "windows": {
            "type": "ARRAY",
            "description": (
                "Periods that bear on the answer, in ISO dates copied exactly "
                "from the computed periods above. Do not derive a boundary."
            ),
            "items": {
                "type": "OBJECT",
                "properties": {
                    "start": {"type": "STRING", "description": "YYYY-MM-DD"},
                    "end": {"type": "STRING", "description": "YYYY-MM-DD"},
                    "label": {
                        "type": "STRING",
                        "description": "The period's name, e.g. Sun/Rahu antardasha",
                    },
                    "status": {"type": "STRING", "enum": list(STATUSES)},
                },
                "required": ["start", "end", "status"],
            },
        },
        "exact_times": {
            "type": "ARRAY",
            "description": (
                "Clock windows for a stated date — Rahu Kaal, hora, sunrise — "
                "copied character for character from above. These are the only "
                "values the reader receives to the minute."
            ),
            "items": {
                "type": "OBJECT",
                "properties": {
                    "label": {"type": "STRING"},
                    "value": {"type": "STRING"},
                },
                "required": ["label", "value"],
            },
        },
        "disagreements": {
            "type": "ARRAY",
            "description": (
                "Where two indications genuinely point different ways. Report "
                "the disagreement; do not average it away."
            ),
            "items": {"type": "STRING"},
        },
        "unsupported": {
            "type": "ARRAY",
            "description": (
                "Steps of the method you could not run, and why. Declaring a "
                "step unsupported is a correct outcome, not a failure."
            ),
            "items": {"type": "STRING"},
        },
        "falsifier": {
            "type": "STRING",
            "description": (
                "One specific observable that, if it does not occur, means you "
                "were wrong. It must fall inside a window you listed."
            ),
        },
    },
    "required": ["promise", "headline", "factors"],
}
"""The shape pro is forced into.

Uppercase types deliberately: this goes to Vertex through `response_schema`, and
`OBJECT`/`ARRAY`/`STRING` is the form that path accepts without relying on the
SDK's case coercion.

Only three fields are required, and the omissions are the interesting part. A
question with no timing in it should return no `windows`, and requiring them
would make a model invent one to satisfy the schema — the exact failure this
whole seam exists to prevent.
"""


def _text(value) -> str:
    return str(value).strip() if value is not None else ""


def _payload(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    body = _text(raw)
    fenced = _FENCE.match(body)
    if fenced:
        # Models fence JSON even when told not to. A fence is not a reason to
        # fail a turn the model otherwise got right.
        body = fenced.group(1)
    try:
        loaded = json.loads(body)
    except (ValueError, TypeError) as exc:
        raise VerdictError(f"the reasoning call did not return JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise VerdictError("the reasoning call returned JSON that is not an object")
    return loaded


def _factors(items) -> tuple[Factor, ...]:
    out: list[Factor] = []
    for item in items or ():
        if not isinstance(item, dict):
            continue
        fact, consequence = _text(item.get("fact")), _text(item.get("consequence"))
        if not fact or not consequence:
            # A bare placement is what the prose rules forbid outright, and a
            # consequence with nothing behind it is uncheckable. Either half
            # missing makes the pair useless, so it never reaches the gate.
            continue
        weight = _text(item.get("weight")).lower()
        out.append(Factor(
            fact=fact,
            consequence=consequence,
            weight=weight if weight in WEIGHTS else "moderate",
        ))
    return tuple(out)


def _windows(items) -> tuple[Window, ...]:
    out: list[Window] = []
    for item in items or ():
        if not isinstance(item, dict):
            continue
        start, end = _text(item.get("start")), _text(item.get("end"))
        if not start or not end:
            continue
        status = _text(item.get("status")).lower() or "future"
        if status not in STATUSES:
            raise VerdictError(f"unknown window status: {status!r}")
        out.append(Window(
            start=start, end=end, label=_text(item.get("label")), status=status,
        ))
    return tuple(out)


def _exact_times(items) -> tuple[ExactTime, ...]:
    out: list[ExactTime] = []
    for item in items or ():
        if not isinstance(item, dict):
            continue
        label, value = _text(item.get("label")), _text(item.get("value"))
        if label and value:
            out.append(ExactTime(label=label, value=value))
    return tuple(out)


def _strings(items) -> tuple[str, ...]:
    return tuple(
        _text(item) for item in (items or ()) if isinstance(item, str) and _text(item)
    )


def parse_verdict(raw) -> Verdict:
    """A model response into a `Verdict`, or `VerdictError`.

    Strict about the three things a narration cannot proceed without — a known
    promise, a headline to lead with, a legible window status — and forgiving
    about everything else, because a dropped disagreement costs the reader a
    nuance and a misread promise costs them the answer.
    """
    payload = _payload(raw)

    print(f"===============. payload in the parse verdict is \n\n{payload}")

    promise = _text(payload.get("promise")).lower()
    if promise not in PROMISES:
        raise VerdictError(f"unknown promise: {promise!r}")

    headline = _text(payload.get("headline"))
    if not headline:
        # The headline IS the answer, and the output block's first instruction
        # is to lead with it. A verdict without one leaves the narrator nothing
        # to open on, and an opening it invents is unlicensed by construction.
        raise VerdictError("the reasoning call returned no headline")

    return Verdict(
        promise=promise,
        headline=headline,
        not_happening=_text(payload.get("not_happening")),
        factors=_factors(payload.get("factors")),
        windows=_windows(payload.get("windows")),
        exact_times=_exact_times(payload.get("exact_times")),
        disagreements=_strings(payload.get("disagreements")),
        unsupported=_strings(payload.get("unsupported")),
        falsifier=_text(payload.get("falsifier")),
    )


def _grahas_in(text: str) -> list[str]:
    return [g for g in _GRAHAS if re.search(rf"\b{g}\b", text)]


def apply_gate(verdict: Verdict, prompt: str) -> Verdict:
    """Remove everything the prompt did not license. Add nothing.

    Four rules, each guarding a failure that has actually been seen in this lane
    or its predecessor:

    * **A window whose dates the prompt never printed is dropped.** Swiss
      Ephemeris owns every date. A boundary that does not appear verbatim above
      was derived by the model, whatever the model says about it.
    * **A `past` window is dropped.** It is not an answer about the future, and
      the narrator has no way to tell one from the other once the status field
      is gone.
    * **Under an `absent` promise every window goes.** There is nothing to time.
      This is how a "the chart does not carry this" reading grows a date.
    * **A factor naming a graha, or carrying a date, the prompt never printed is
      dropped.** Same argument as the windows, one level down.

    Houses are deliberately not checked. They print as bare integers in a table
    column, so a literal-substring test would drop true factors — and a gate
    that removes correct material is worse than the looser one it replaced.
    """
    dropped: list[str] = []

    windows: list[Window] = []
    for window in verdict.windows:
        if verdict.promise == "absent":
            dropped.append(
                f"window {window.start}..{window.end}: the promise is absent, "
                "so there is nothing to time"
            )
            continue
        if window.status == "past":
            dropped.append(f"window {window.start}..{window.end}: past")
            continue
        missing = [d for d in (window.start, window.end) if d not in prompt]
        if missing:
            dropped.append(
                f"window {window.start}..{window.end}: "
                f"{', '.join(missing)} was not printed in the prompt"
            )
            continue
        windows.append(window)

    factors: list[Factor] = []
    for factor in verdict.factors:
        body = f"{factor.fact} {factor.consequence}"
        unseen_graha = [g for g in _grahas_in(factor.fact) if g not in prompt]
        unseen_dates = [d for d in _ISO.findall(body) if d not in prompt]
        if unseen_graha:
            dropped.append(
                f"factor {factor.fact!r}: {', '.join(unseen_graha)} "
                "was not printed in the prompt"
            )
            continue
        if unseen_dates:
            dropped.append(
                f"factor {factor.fact!r}: {', '.join(unseen_dates)} "
                "was not printed in the prompt"
            )
            continue
        factors.append(factor)

    exact_times: list[ExactTime] = []
    for entry in verdict.exact_times:
        if entry.value in prompt:
            exact_times.append(entry)
            continue
        # Copied to the minute or wrong. A time the prompt did not print was
        # not copied from it, and these are the one class of value the reader
        # receives at full precision.
        dropped.append(
            f"exact time {entry.label} {entry.value!r}: not printed in the prompt"
        )

    return replace(
        verdict,
        windows=tuple(windows),
        factors=tuple(factors),
        exact_times=tuple(exact_times),
        dropped=tuple(dropped),
    )
