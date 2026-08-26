"""What a Rishi returns. Structure before prose.

The blueprint's §11 protocol has nine steps and the ones that matter are the
ones a generation will skip unless something insists: state what argues
against you, state what you assumed, state what would change your mind.

**`weakening` is required, not encouraged.** A prompt asking nicely for
counter-evidence gets counter-evidence most of the time, and "most of the time"
is the same as not having it - the reports that omit it are exactly the ones
where the model was most confident and least examined. So a report carrying
supporting evidence and an empty `weakening` list is rejected by the validator
unless it abstained.

The other half of the discipline is that a rejection **costs one opinion, not
the turn.** `parse_report` turns any failure - unparseable, invalid, or merely
uncorroborated - into an abstaining report that names its reason. Synthesis then
proceeds with fewer voices and says how many.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from rishivan.council.hierarchy import TIERS

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


class EvidenceItem(BaseModel):
    """One piece of evidence, traced all the way back to a verse."""

    statement: str = Field(min_length=1)
    rule_ids: list[str] = Field(min_length=1)
    """Every item traces to Koonji. An uncited statement is the model's own
    opinion wearing the format of evidence, and it is indistinguishable from a
    real one at a glance - which is the whole problem."""

    chart_basis: list[str] = Field(min_length=1)
    """The atoms or diagnoses it rests on. A rule that cites no chart fact
    fired against something, and a reviewer has to be able to see what."""

    weight: float = Field(ge=0.0, le=1.0)
    tier: str

    @field_validator("statement")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("an evidence item needs a statement")
        return v

    @field_validator("tier")
    @classmethod
    def _known_tier(cls, v: str) -> str:
        if v not in TIERS:
            raise ValueError(
                f"tier {v!r} is not one of {', '.join(TIERS)} - an unknown tier "
                f"cannot be weighted, so the claim would be scored as though it "
                f"rested on a D1 placement"
            )
        return v


class RishiReport(BaseModel):
    """Blueprint §11's protocol steps 4 through 8, typed."""

    rishi: str = ""
    domain: str = ""

    supporting: list[EvidenceItem] = Field(default_factory=list)
    weakening: list[EvidenceItem] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    would_change_my_mind: list[str] = Field(default_factory=list)

    score: float = Field(default=0.0, ge=-1.0, le=1.0)
    """Signed. A chart arguing *against* the thing asked about is an answer,
    and one of the more useful ones."""

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_reasons: list[str] = Field(default_factory=list)

    abstained: str = ""
    """Why this Rishi declined. Empty means it did not."""

    @model_validator(mode="after")
    def _weakening_is_required(self) -> "RishiReport":
        """A report with supporting evidence and nothing against it is a
        sales pitch with citations.

        The escape hatch is deliberate and is not "leave it empty": a chart
        that genuinely says one thing should say so *in* `weakening` - "no
        contrary indication found, and here is what I looked for" - which is a
        statement a reviewer can check. Silence is not.
        """
        if self.supporting and not self.weakening and not self.abstained:
            raise ValueError(
                f"{self.rishi or 'this Rishi'} gave "
                f"{len(self.supporting)} supporting items and nothing "
                f"weakening. Either the chart genuinely says one thing - in "
                f"which case say that in `weakening`, as 'no contrary "
                f"indication found, and here is what I looked for' - or "
                f"abstain and say why."
            )
        return self


REPORT_SCHEMA: dict = RishiReport.model_json_schema()
"""Handed to the model as the response schema.

Generated rather than hand-written. A hand-written copy is a second thing to
drift, and it drifts towards whatever the model happened to return last.
"""


def parse_report(
    text: str,
    *,
    rishi: str,
    domain: str,
    on_error: Optional[str] = None,
) -> RishiReport:
    """A generation becomes a report, or an abstention that says why.

    `rishi` and `domain` are stamped from the caller and **overwrite** whatever
    the model put there. Who is speaking and about what are the graph's facts,
    not the generation's - a model that names itself differently would fan its
    report into the wrong slot, and nothing downstream would notice.
    """
    def _abstain(reason: str) -> RishiReport:
        return RishiReport(rishi=rishi, domain=domain, abstained=reason)

    if on_error:
        return _abstain(on_error)

    # Models wrap JSON in markdown fences whatever mime type was asked for.
    # Losing a whole opinion to three backticks is not a tradeoff worth making.
    cleaned = _FENCE.sub("", text or "").strip()
    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return _abstain(
            "unparseable response - the model returned prose where the "
            "contract asked for JSON"
        )

    if not isinstance(payload, dict):
        return _abstain("the response was valid JSON but not an object")

    payload["rishi"] = rishi
    payload["domain"] = domain
    try:
        return RishiReport.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - any contract failure, same outcome
        return _abstain(f"the report did not meet the contract: {exc}")
