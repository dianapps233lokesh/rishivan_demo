"""Multi-turn conversation state for the Council.

Rule 9 of the Rishi prompt makes every answer end with a question or a
deliberately withheld thread ("ask me when you are ready"). That promise is
empty unless the next turn remembers what was offered — so this module carries
the recent exchange into the prompt, and keeps the seeker with the same Rishi
while a thread is still open.

Deliberately small: a capped, in-memory transcript. Persistence belongs in the
production app (``app/``), not the demo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Older turns add prompt tokens (and so latency) for little benefit — the hook
# a seeker is replying to is almost always the most recent one.
MAX_TURNS = 4


@dataclass(frozen=True)
class Turn:
    """One question and the answer the Council gave."""

    question: str
    answer: str
    rishi: str
    claims: tuple[tuple[str, str], ...] = ()
    """(claim_id, band) for everything this turn was licensed to assert.

    Claim ids rather than more prose. The prose is already in the transcript
    and the model can read it; what it cannot do is notice on its own that it
    is about to say the same thing more confidently than last time. A band is
    comparable, a paragraph is not.
    """


@dataclass
class Conversation:
    """Ordered transcript, newest last."""

    turns: list[Turn] = field(default_factory=list)

    def add(
        self, question: str, answer: str, rishi: str,
        claims: tuple[tuple[str, str], ...] = (),
    ) -> None:
        """`claims` is optional so every existing caller is unchanged."""
        self.turns.append(
            Turn(question.strip(), answer.strip(), rishi, tuple(claims))
        )

    @property
    def is_empty(self) -> bool:
        return not self.turns

    @property
    def last(self) -> Turn | None:
        return self.turns[-1] if self.turns else None

    @property
    def current_rishi(self) -> str | None:
        return self.turns[-1].rishi if self.turns else None

    def recent(self, limit: int = MAX_TURNS) -> list[Turn]:
        return self.turns[-limit:]

    def render(self, limit: int = MAX_TURNS) -> str:
        """The transcript as the Rishi should read it back."""
        if not self.turns:
            return ""
        return "\n\n".join(
            f"Seeker asked: {t.question}\nYou answered: {t.answer}"
            for t in self.recent(limit)
        )


def continuity_instruction(convo: Conversation | None) -> str:
    """Prompt block telling the Rishi to honour what it already offered."""
    if convo is None or convo.is_empty:
        return ""
    return (
        "THIS IS AN ONGOING CONVERSATION — you have already been speaking with "
        "this seeker. What you said before is below.\n\n"
        f"{convo.render()}\n\n"
        "Continue naturally. Do not greet them again or restate what you have "
        "already told them. If they are taking up the thread you offered, open "
        "it now and give them the substance you held back — do not defer a "
        "second time. If they are answering a question you asked, respond to "
        "their answer directly. End on a NEW hook, never the same one twice."
    )


def is_probable_followup(question: str, convo: Conversation | None) -> bool:
    """Cheap heuristic: does this read as a reply rather than a fresh query?

    Used only as a fallback when the classifier does not decide; a wrong guess
    costs a re-route, not a crash.
    """
    if convo is None or convo.is_empty:
        return False
    q = question.strip().lower().rstrip("?.!")
    if len(q.split()) <= 4:
        return True
    openers = (
        "yes", "no", "yeah", "yep", "nope", "sure", "okay", "ok",
        "tell me more", "go on", "continue", "what about", "and ",
        "why", "how so", "explain", "open it", "show me", "more",
        "that one", "the second", "please do", "i am", "i'm", "it is",
    )
    return q.startswith(openers)


# ==========================================================================
# Consistency across turns
# ==========================================================================

_BAND_ORDER = (
    "some_indications", "moderately_supported",
    "strongly_indicated", "consistently_supported",
)


def claims_of(plan) -> tuple[tuple[str, str], ...]:
    """A plan's licensed claims, in the shape a `Turn` stores."""
    if plan is None:
        return ()
    return tuple((c.claim_id, c.band) for c in plan.allowed)


def _rank(band: str) -> int:
    try:
        return _BAND_ORDER.index(band)
    except ValueError:
        return -1


def consistency_instruction(convo, plan) -> str:
    """What this turn must not contradict, given what earlier turns asserted.

    **Turn 14 disagreeing with turn 13 about a fact is the failure a reader
    notices fastest and forgives least.** It is also the one a model cannot
    avoid unaided: it sees the earlier prose, but "strongly indicated" and
    "some indications suggest" are a tone difference in text and a real
    difference in evidence, and nothing in the transcript marks which.

    Three things get flagged, and a fourth deliberately does not:

      * a claim stated more strongly than before - nothing changed but the
        retelling
      * a claim stated more weakly - the reader deserves to hear why
      * a claim that has dropped out entirely - silently ceasing to mention
        something you asserted is the quietest way to be inconsistent
      * a NEW claim is not flagged. A different question was asked; saying
        something new is the point.
    """
    if convo is None or convo.is_empty:
        return ""

    previous: dict[str, str] = {}
    for turn in convo.recent():
        for claim_id, band in turn.claims:
            previous[claim_id] = band
    if not previous:
        return ""

    current = {c.claim_id: c.band for c in (plan.allowed if plan else ())}
    lines: list[str] = []

    for claim_id, was in previous.items():
        now = current.get(claim_id)
        if now is None:
            lines.append(
                f"  {claim_id} — you asserted this earlier and this turn's "
                f"evidence no longer supports it. Say so if it comes up; do "
                f"not quietly stop mentioning it."
            )
        elif _rank(now) > _rank(was):
            lines.append(
                f"  {claim_id} — you said \"{was}\" earlier and the evidence "
                f"now reads \"{now}\". Do not present it as stronger than you "
                f"already did unless you say what changed."
            )
        elif _rank(now) < _rank(was):
            lines.append(
                f"  {claim_id} — you said \"{was}\" earlier and it now reads "
                f"weaker. If you soften it, say that you are softening it."
            )
        else:
            lines.append(
                f"  {claim_id} — already stated at \"{was}\". Stay consistent "
                f"with that."
            )

    if not lines:
        return ""
    return (
        "WHAT YOU HAVE ALREADY TOLD THIS SEEKER\n"
        + "\n".join(lines)
        + "\n  Contradicting yourself across turns is the failure a reader "
          "notices fastest. Changing your mind is allowed; changing it "
          "silently is not."
    )
