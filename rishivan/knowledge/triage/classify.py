"""S4 Triage — decide where each verse goes, before any money is spent.

The classifier answers one question per unit: does this statement have a condition
testable against chart facts (destination A, `rule`) or does it state something else
(destination B, `knowledge_item`)? It does **not** extract anything — that is S5's
job, and keeping the two apart is what lets triage be free and deterministic for
most of the corpus.

Three properties are deliberate:

* **Exhaustive.** Every unit gets a verdict. There is no path that returns nothing,
  because a unit with no verdict is a unit silently lost.
* **Conservative when unsure.** Ambiguity routes to `Destination.ambiguous`, which
  escalates to an LLM. It never quietly becomes `narrative` — filing content as
  contentless is the one error that cannot be recovered later.
* **Auditable.** Every verdict carries the signals that produced it, so a wrong
  classification can be diagnosed from the row rather than re-run.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from rishivan.knowledge.triage.chapter_kind import kind_for_title, missing_capability
from rishivan.knowledge.triage.signals import Signal, detect
from rishivan.models.knowledge.item import ItemKind


class Destination(StrEnum):
    rule = "rule"
    """Has a testable condition — goes to S5 extraction."""

    item = "item"
    """States something else — goes to `knowledge_item` with a `kind`."""

    ambiguous = "ambiguous"
    """Deterministic signals are insufficient. Escalate to an LLM; never discard."""


@dataclass(frozen=True)
class Verdict:
    destination: Destination
    kind: ItemKind | None
    confidence: float
    reasons: tuple[str, ...] = field(default_factory=tuple)
    method: str = "deterministic"
    vocabulary_gap: str | None = None
    """The engine capability this unit would need. Feeds the ranked backlog."""

    def __post_init__(self) -> None:
        if self.destination is Destination.item and self.kind is None:
            raise ValueError("an item verdict must name a kind")


def _v(dest, kind, conf, *reasons, method="deterministic", gap=None) -> Verdict:
    return Verdict(dest, kind, conf, tuple(reasons), method, gap)


def classify(
    translation: str,
    *,
    commentary: str = "",
    chapter_is_rule_bearing: bool = True,
    chapter_gating_reason: str | None = None,
    chapter_title: str | None = None,
) -> Verdict:
    """Route one sutra unit. Pure: same input always gives the same verdict."""
    text = (translation or "").strip()
    if not text:
        # A verse with no translation cannot be read, let alone extracted. It is
        # already flagged `needs_review` upstream; here it is captured, not dropped.
        return _v(
            Destination.item,
            ItemKind.unclassified,
            0.0,
            "no translation attached",
        )

    sig = detect(text)

    # Chapter gating (C2). The chapter tree already records that BPHS 1 is cosmology
    # and 7 is reference data. Cheapest possible signal, so it comes first -- but it
    # only *classifies*, it never discards: the text still lands in destination B.
    if not chapter_is_rule_bearing:
        reason = chapter_gating_reason or "chapter gated as not rule-bearing"
        kind = {
            "cosmology": ItemKind.narrative,
            "devotional": ItemKind.invocation,
            "calculation method": ItemKind.formula,
            "reference data": ItemKind.reference_table,
        }.get(reason, ItemKind.out_of_domain)
        return _v(Destination.item, kind, 0.9, f"chapter gate: {reason}")

    # Whole-chapter classification from the printed title. BPHS dedicates entire
    # chapters to remedy, computation and description, so deciding once per chapter is
    # both cheaper and more consistent than guessing per verse. Predictive chapters
    # return None here and fall through untouched.
    gap = missing_capability(chapter_title)
    if gap is not None:
        return _v(
            Destination.item,
            ItemKind.out_of_domain,
            0.9,
            f"chapter subject needs a capability the engine lacks: {gap}",
            gap=gap,
        )
    title_kind = kind_for_title(chapter_title)
    if title_kind is not None:
        return _v(
            Destination.item,
            title_kind,
            0.85,
            f"chapter title classifies as {title_kind.value}",
        )

    # Arithmetic outranks conditionals: BPHS 20.5 carries an `if` and is a formula.
    if Signal.arithmetic in sig:
        return _v(
            Destination.item,
            ItemKind.formula,
            0.85,
            "arithmetic operators present",
            "formula outranks conditional marker",
        )

    # A dasha acting as the antecedent is a condition. BPHS vol 2's dasha-result
    # chapters state no placement at all, and requiring one filed 150+ real rules as
    # ambiguous. S6 is what keeps this honest: with no natal atom to put in
    # `formation`, the rule compiles `timing_only` and cannot assert a promise.
    has_condition = bool(
        sig
        & {
            Signal.conditional,
            Signal.conditional_implicit,
            Signal.timing_condition,
        }
    )
    has_effect = Signal.effect in sig
    has_entity = Signal.astro_entity in sig

    # Invocation only wins when nothing predictive is present -- "Parasara said, if
    # Saturn is in the 7th..." is a rule wearing a frame.
    if Signal.invocation in sig and not (has_condition and has_effect):
        return _v(Destination.item, ItemKind.invocation, 0.8, "invocation markers")

    if Signal.narrative in sig and not has_condition:
        return _v(Destination.item, ItemKind.narrative, 0.75, "narrative markers")

    # The core case. A condition + a consequent + an astrological entity is a rule,
    # whether or not the word "if" appears. Conditionals outrank remedies so that
    # BPHS 54.63 yields a rule with the remedy attached rather than a bare remedy.
    if has_condition and has_effect and has_entity:
        reasons = ["condition present", "consequent present", "astrological entity"]
        if Signal.remedy in sig:
            reasons.append("carries an attached remedy for S5 to link")
        if Signal.timing in sig:
            reasons.append("timing present -> S6 must move it to activation_factors")
        if Signal.timing_condition in sig and not (
            sig & {Signal.conditional, Signal.conditional_implicit}
        ):
            reasons.append("antecedent is a period -> expect timing_only at S6")
        return _v(Destination.rule, None, 0.9, *reasons)

    # Definition-like statements with no consequent: vocabulary, not prediction.
    if Signal.definition in sig and not has_effect:
        return _v(Destination.item, ItemKind.definition, 0.8, "defines a term")

    if Signal.classification in sig and not has_condition:
        return _v(
            Destination.item, ItemKind.classification, 0.75, "classifies entities"
        )

    if Signal.remedy in sig and not has_condition:
        return _v(Destination.item, ItemKind.remedy, 0.8, "remedial prescription")

    if Signal.enumeration in sig and not has_effect:
        return _v(Destination.item, ItemKind.enumeration, 0.7, "enumeration markers")

    # A statement with no astrological entity is almost never a rule, but "almost"
    # is why this is a low-confidence item rather than a discard.
    if not has_entity:
        return _v(
            Destination.item,
            ItemKind.out_of_domain,
            0.6,
            "no astrological entity present",
        )

    # Everything left is genuinely uncertain: an entity is present but the condition
    # or consequent is unclear. This is exactly the population worth paying an LLM
    # for, and it is the only branch that costs money.
    missing = []
    if not has_condition:
        missing.append("no clear condition")
    if not has_effect:
        missing.append("no clear consequent")
    return _v(Destination.ambiguous, None, 0.4, *missing or ("unclear shape",))
