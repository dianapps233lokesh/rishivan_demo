"""Dated predictions, written where they can later be scored.

**The falsifiability play.** An astrology product that never records what it
said cannot be wrong, and a system that cannot be wrong is not making claims -
it is producing text. This file is the smallest thing that makes the claims
checkable: what was predicted, for when, on which verses, and how loudly.

**And the reason it is small.** A prediction is written only when the claim
cleared the evidence floor *and* a dasha window gave it somewhere to land. A
ledger of undated statements scores nothing and reads as rigour, which is worse
than not keeping one - it looks like accountability while providing none.

**Nothing here reads the clock.** `asked_at` and `resolved_at` are passed in. A
backtest asks about 1998; a ledger that stamps `now` makes every replayed run
look like it was predicted today, and the calibration figure that comes out of
it is meaningless in a way nobody would notice.

JSONL on disk, appended. Not Postgres: Streamlit Cloud has none, and the demo's
requirements deliberately exclude it. A corrupt line costs one record.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Iterable, Optional

OUTCOMES = frozenset({"open", "occurred", "did_not_occur", "unresolvable"})
"""`unresolvable` is a real outcome and not an evasion: some predictions are
about things the person never reports back on, and quietly leaving those `open`
forever inflates the denominator of every accuracy figure."""


@dataclass(frozen=True, slots=True)
class Prediction:
    prediction_id: str
    run_id: str
    asked_at: str
    claim_id: str
    domain: str
    window: str
    confidence: float
    band: str
    """How loudly it was said. A ledger where a 0.4 and a 0.9 look alike cannot
    tell calibration from luck."""

    citations: tuple[str, ...]
    rule_ids: tuple[str, ...]
    outcome: str = "open"
    resolved_at: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "Prediction":
        payload = dict(payload)
        payload["citations"] = tuple(payload.get("citations", ()))
        payload["rule_ids"] = tuple(payload.get("rule_ids", ()))
        return cls(**payload)


def _identity(run_id: str, claim_id: str, window: str) -> str:
    """Content-addressed, so replaying a run cannot double-count it.

    Keyed on the run as well as the claim: the same chart asked the same
    question next year is a genuinely new prediction, made on evidence that may
    have changed, and collapsing the two would hide a reversal.
    """
    raw = f"{run_id}\n{claim_id}\n{window}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def predictions_from(plan, *, run_id: str, asked_at: str) -> list[Prediction]:
    """The dated claims in a plan, as ledger entries."""
    if plan is None:
        return []
    return [
        Prediction(
            prediction_id=_identity(run_id, claim.claim_id, claim.window),
            run_id=run_id,
            asked_at=asked_at,
            claim_id=claim.claim_id,
            domain=plan.domain,
            window=claim.window,
            confidence=claim.confidence,
            band=claim.band,
            citations=tuple(claim.citations),
            rule_ids=tuple(claim.rule_ids),
        )
        for claim in plan.allowed
        if claim.window
    ]


class Ledger:
    """Append-only JSONL, read whole.

    Read-whole is fine at this scale and honest about it: a few thousand
    predictions is a file, not a database. When it stops being one, the fix is a
    real store behind the same three methods, not a cleverer file format.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def all(self) -> list[Prediction]:
        if not self.path.exists():
            return []
        out: list[Prediction] = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Prediction.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError):
                # One bad append costs one record. Raising here would mean a
                # single truncated write makes every earlier prediction
                # unreadable, which is the opposite of what a ledger is for.
                continue
        return out

    def append(self, prediction: Prediction) -> None:
        """Idempotent on `prediction_id`."""
        existing = {p.prediction_id for p in self.all()}
        if prediction.prediction_id in existing:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(json.dumps(prediction.to_dict()) + "\n")

    def extend(self, predictions: Iterable[Prediction]) -> None:
        for prediction in predictions:
            self.append(prediction)

    def resolve(
        self, prediction_id: str, *, outcome: str, resolved_at: str,
        note: str = "",
    ) -> Prediction:
        """Score one prediction. Rewrites the file.

        Raises on an unknown id rather than doing nothing: a scoring script
        that silently resolves none of what it was given would report a clean
        run, and the number it produced would be an accuracy figure over an
        empty set.
        """
        if outcome not in OUTCOMES:
            raise ValueError(
                f"{outcome!r} is not an outcome; use one of "
                f"{', '.join(sorted(OUTCOMES))}"
            )
        records = self.all()
        found: Optional[Prediction] = None
        for index, record in enumerate(records):
            if record.prediction_id == prediction_id:
                found = replace(record, outcome=outcome,
                                resolved_at=resolved_at, note=note)
                records[index] = found
                break
        if found is None:
            raise KeyError(f"no prediction {prediction_id!r} in {self.path}")

        self.path.write_text(
            "".join(json.dumps(r.to_dict()) + "\n" for r in records)
        )
        return found

    def open_predictions(self) -> list[Prediction]:
        return [p for p in self.all() if p.outcome == "open"]

    def due_before(self, when: str) -> list[Prediction]:
        """Open predictions whose window has closed - what can be scored now.

        String comparison on the raw window is deliberately not attempted:
        `EventWindow` renders "Aug 2026 – Aug 2036" for display, and parsing
        display text to make a scoring decision is how a subtle off-by-a-year
        gets into a calibration report. Callers filter on `asked_at`, which is
        ISO, and read the window themselves.
        """
        return [p for p in self.open_predictions() if p.asked_at < when]
