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


@dataclass
class Conversation:
    """Ordered transcript, newest last."""

    turns: list[Turn] = field(default_factory=list)

    def add(self, question: str, answer: str, rishi: str) -> None:
        self.turns.append(Turn(question.strip(), answer.strip(), rishi))

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
