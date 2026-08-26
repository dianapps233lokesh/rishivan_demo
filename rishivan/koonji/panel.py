"""A Koonji reading as the rules panel reads it.

The panel ("N classical rules match this chart") was filled by the older
Qdrant-backed matcher. That matcher only understands the previous rule format,
so every rule the Koonji extractor has produced since is invisible in it --
274 of them at the time of writing, sitting on disk, firing correctly, and
shown to nobody.

This is the same panel, sourced from the reading the engine already computed a
few nodes earlier. Nothing new is matched here and nothing is re-evaluated: the
firings are read, not recomputed.

**The shape is the old matcher's on purpose.** `RuleHit`'s attribute surface is
what `streamlit_app` renders against, so `KoonjiHit` answers to the same names.
Changing the panel and its data source in one step would mean two things to
review at once, and only one of them is interesting.

The one addition is `condition_text`. The old hit carried a condition in the
old vocabulary and the panel called `rag.describe.describe_condition` on it; a
Koonji condition needs `koonji.describe` instead. Rendering it here rather than
in the template means the panel does not have to know which engine matched the
rule -- which is the whole point of the exercise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from rishivan.koonji.describe import describe_condition
from rishivan.koonji.vm import Outcome

MAX_PANEL_RULES = 10
"""Matched with `graph.nodes.retrieve.MAX_MATCHED_RULES`, and bounded for the
same reason: one verse fans out into siblings that share a condition, and an
unbounded list spends the panel on near-duplicates."""


@dataclass(slots=True)
class KoonjiHit:
    """One fired rule, in the shape the panel already knows how to draw."""

    rule_key: str
    condition: dict
    condition_text: str
    effects: list[dict]
    source: dict
    relevance: float = 0.0
    life_domains: list[str] = field(default_factory=list)
    domain: Optional[str] = None
    school: str = "unknown"
    rule_category: str = "formation"
    tier: str = "S5"
    remedies: list[dict] = field(default_factory=list)
    """Read by `council.contributors.remedy_contribution`, which does a bare
    `r.remedies` rather than a `getattr`. Absent, it raises inside the node's
    broad `except Exception` and the panel silently comes back empty -- which
    is exactly what happened, and why the test that catches it exists."""
    active: Optional[bool] = None
    """True when a timing condition is running now, False when it is dormant,
    None when the rule has no timing at all.

    Three states rather than two, because "this rule has no period" and "this
    rule's period is not running" are different facts and the panel says so
    differently. Collapsing them would let a dormant rule read like a live one.
    """

    @property
    def citation(self) -> str:
        """Book and verse, as a reader would cite it.

        The old `RuleHit.citation` hardcoded the string "BPHS" and appended a
        chapter and verse, so every rule from every book was cited as BPHS --
        harmless while BPHS was the only book with rules, and wrong the moment
        Brihat Jataka and Phaladeepika arrived.
        """
        from rishivan.rag.books import title_for_slug

        title = title_for_slug(self.source.get("edition") or self.source.get("book"))
        locator = self.source.get("locator") or ""
        return f"{title} {locator}".strip()


def _effects_of(rule) -> list[dict]:
    """The rule's consequent, as the panel's `{polarity, statement}` rows."""
    consequent = getattr(rule, "consequent", None)
    if consequent is None:
        return []
    statement = (
        getattr(consequent, "literal_text", "")
        or getattr(consequent, "guidance_text", "")
        or getattr(consequent, "action_text", "")
        or str(getattr(consequent, "claim_id", "") or "")
    )
    if not statement:
        return []
    return [{
        "polarity": getattr(consequent, "polarity", "positive"),
        "statement": statement,
        "claim": getattr(consequent, "claim_id", "") or "",
    }]


def hits_from_reading(
    reading, *, engine, domain: str | None = None, limit: int = MAX_PANEL_RULES
) -> list[KoonjiHit]:
    """The fired rules of a reading, strongest first.

    Only `Outcome.FIRED` becomes a hit. A cancelled rule is one the source
    itself overrules, and putting it in a panel headed "rules that match this
    chart" would assert what the book denies -- the engine already tracks it
    under `cancelled_by` for the audit trail.
    """
    if reading is None:
        return []
    by_id = {r.rule_id: r for r in engine.bundle.rules}

    hits: list[KoonjiHit] = []
    for firing in getattr(reading, "firings", []) or []:
        if firing.outcome is not Outcome.FIRED:
            continue
        rule = by_id.get(firing.rule_id)
        if rule is None:
            continue
        provenance = rule.provenance
        condition = _condition_dict(rule)
        hits.append(KoonjiHit(
            rule_key=rule.rule_id,
            condition=condition,
            condition_text=describe_condition(condition),
            effects=_effects_of(rule),
            source={
                "book": provenance.book_id,
                "edition": provenance.edition_id,
                "locator": provenance.locator,
                "quote": provenance.quoted_text,
                # `prompts.rule_context` puts this in front of the model, and
                # says why: "a citation whose text the model cannot see is one
                # it has to take on trust, and taking a citation on trust is
                # indistinguishable from inventing it." The engine's provenance
                # carries the verbatim quote, so that is what it sees.
                "translation": provenance.quoted_text,
            },
            relevance=float(firing.strength),
            life_domains=[d.removeprefix("domain.") for d in (rule.domains or {})],
            domain=domain,
            school=str(rule.school or "unknown").removeprefix("school."),
            rule_category=("timing" if rule.qualifiers.timing else "formation"),
            tier=provenance.authority_tier or "S5",
            active=_active(rule, firing),
        ))

    hits.sort(key=lambda h: -h.relevance)
    return hits[:limit]


def _condition_dict(rule) -> dict:
    """The rule's antecedent as the plain dict the describer walks.

    The compiled rule holds a `BoolExpr` tree rather than the YAML it came from,
    so it is re-emitted rather than read off. `emit_doc` is the one function
    that knows how to turn a compiled rule back into its document form, and
    using it here means the panel cannot drift from the file on disk.
    """
    from rishivan.koonji.emit import emit_doc

    try:
        return emit_doc(rule).get("when") or {}
    except Exception:  # noqa: BLE001 - a panel must not take down an answer
        return {}


def _active(rule, firing) -> Optional[bool]:
    """Whether this rule's activating period is running.

    `None` when the rule carries no timing, which is most of them. The engine
    only fires a rule whose timing holds, so a fired rule that HAS timing has
    it running by construction -- the value is carried anyway so the panel can
    say so, rather than the reader having to know that.
    """
    return True if rule.qualifiers.timing else None


def counts_from_reading(reading, *, engine) -> dict[str, Any]:
    """The three numbers printed above the panel.

    `rules_true_of_chart` counts every rule that fired, not the ten shown: the
    gap between them is the specialisation doing its job and the caption says so.

    Timing is read from each rule's `qualifiers.timing`, which means the bundle
    is needed. An earlier version inferred it from the firing's `modifiers` list
    to avoid the lookup, and reported zero timed rules on every chart -- a
    number the demo script specifically tells you to check, because zero there
    is supposed to mean a stale index.
    """
    empty = {"rules_true_of_chart": 0, "rules_with_timing": 0,
             "rules_running_now": 0}
    if reading is None:
        return empty
    fired = [f for f in (getattr(reading, "firings", []) or [])
             if f.outcome is Outcome.FIRED]
    if not fired:
        return empty

    by_id = {r.rule_id: r for r in engine.bundle.rules}
    timed = [f for f in fired
             if (by_id.get(f.rule_id) is not None
                 and by_id[f.rule_id].qualifiers.timing)]
    return {
        "rules_true_of_chart": len(fired),
        "rules_with_timing": len(timed),
        # A rule only fires when its timing holds, so every timed rule that
        # fired is running now. Kept as its own number because the panel draws
        # a distinction the engine does not need to.
        "rules_running_now": len(timed),
    }
