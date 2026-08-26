"""A `Rule` back to the YAML a reviewer edits. The inverse of `parse_rule`.

This is the link that was missing. `extract.py` produced validated `Rule`
objects and there was nowhere for them to go; the eight rules under
`rules/parashari/` were typed by hand. Everything else - the nine compiler
passes, the lints, the bundle, retrieval - already worked on YAML, so the whole
extraction path was a pipeline with no outlet.

The contract is a **round trip**, and it is tested as one:

    parse_rule(emit_doc(rule), registry) == rule

That equality is the only thing keeping the authoring surface and the runtime
frame from drifting apart. Without it the emitter slowly grows its own dialect,
reviewers edit files that mean something subtly different from what the engine
executes, and the difference surfaces as rules that quietly stop firing.

Emitted YAML is deliberately *authorable*, not a `model_dump`. A reviewer has to
read the verse, read the rule, and agree or not - in about a minute. So the
output keeps the hand-written files' shape: single-key predicate mappings,
`when`/`indicates`/`source` blocks, defaults omitted rather than spelled out.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from rishivan.koonji.urf import (
    AssertionKind,
    AttributeConsequent,
    BoolExpr,
    ClaimConsequent,
    DirectiveConsequent,
    ExampleConsequent,
    FactConsequent,
    GuidanceConsequent,
    Modality,
    ProcedureConsequent,
    Rule,
)

_MODALITY_OUT = {
    Modality.CANCEL: "cancel",
    Modality.EXCEPT: "except",
    Modality.STRENGTHEN: "strengthen",
    Modality.WEAKEN: "weaken",
    Modality.ACTIVATE: "activate",
    Modality.ASSERT: "assert",
}


def quote_sha256(text: str) -> str:
    """Always stored, even where the licence forbids storing the quote itself.

    The hash is what lets a claim be traced to a verse in an edition we may not
    be allowed to reproduce. Dropping it because the quote is present is how a
    corpus loses its audit trail the first time a licence changes.
    """
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


# ==========================================================================
# Expressions
# ==========================================================================


def emit_expr(expr: BoolExpr) -> Any:
    """A `BoolExpr` as the single-key mappings `_parse_expr` reads."""
    if expr.op == "leaf":
        call = expr.leaf
        assert call is not None
        args = dict(call.args)
        if call.negated:
            args["negated"] = True
        return {call.predicate: args}

    if expr.op == "not":
        return {"not": emit_expr(expr.operands[0])}

    if expr.op == "count":
        body: dict[str, Any] = {
            "of": [emit_expr(o) for o in expr.operands],
            "n": expr.count_n,
        }
        if expr.count_op != "gte":
            body["op"] = expr.count_op
        return {"count": body}

    return {expr.op: [emit_expr(o) for o in expr.operands]}


# ==========================================================================
# Consequents
# ==========================================================================


def _emit_consequent(rule: Rule) -> dict[str, Any]:
    c = rule.consequent

    if isinstance(c, ClaimConsequent):
        block: dict[str, Any] = {"claim": c.claim_id, "polarity": c.polarity,
                                 "magnitude": c.magnitude}
        if c.literal_text:
            block["text"] = c.literal_text
        for key, value, default in (
            ("transfer_source", c.transfer_source, None),
            ("transfer_target", c.transfer_target, None),
            ("transfer_cap", c.transfer_cap, 8),
            ("quantity", c.quantity, None),
            ("quantity_max", c.quantity_max, None),
            ("unit", c.unit, None),
            ("bound", c.bound, None),
        ):
            if value != default:
                block[key] = value
        return {"indicates": block}

    if isinstance(c, FactConsequent):
        block = {"fact": c.fact_predicate, "subject": c.subject_expr,
                 "value": c.value}
        if c.object_expr is not None:
            block["object"] = c.object_expr
        return {"derives": block}

    if isinstance(c, AttributeConsequent):
        block = {"entity": c.entity_expr, "attribute": c.attribute,
                 "values": list(c.values)}
        if c.relation_to is not None:
            block["relation_to"] = c.relation_to
        if c.ordered:
            block["ordered"] = True
        if c.exhaustive:
            block["exhaustive"] = True
        return {"defines": block}

    if isinstance(c, DirectiveConsequent):
        block = {"injunction": c.injunction, "acts_on": c.acts_on,
                 "action": c.action_text}
        if c.acts_on_relation is not None:
            block["acts_on_relation"] = c.acts_on_relation
        if c.materials:
            block["materials"] = list(c.materials)
        if c.duration_days is not None:
            block["duration_days"] = c.duration_days
        if c.weekday is not None:
            block["weekday"] = c.weekday
        return {"remedy": block}

    if isinstance(c, ProcedureConsequent):
        block = {"name": c.computes}
        if c.method_note:
            block["note"] = c.method_note
        if c.test_vectors:
            block["test_vectors"] = list(c.test_vectors)
        return {"computes": block}

    if isinstance(c, GuidanceConsequent):
        return {"guidance": {"text": c.guidance_text, "applies_to": c.applies_to}}

    assert isinstance(c, ExampleConsequent)
    block = {"reading": c.authority_reading}
    if c.chart_data:
        block["chart"] = dict(c.chart_data)
    if c.subject_note is not None:
        block["subject"] = c.subject_note
    if c.cited_factors:
        block["cited_factors"] = list(c.cited_factors)
    if c.outcome_known:
        block["outcome_known"] = True
    return {"example": block}


# ==========================================================================
# The document
# ==========================================================================


def emit_doc(rule: Rule) -> dict[str, Any]:
    """One rule as the mapping `parse_rule` reads back.

    Defaults are omitted throughout. A file where every rule spells out
    `binding: literal` and `restriction: open` is a file where the two rules
    that differ are invisible.
    """
    p = rule.provenance
    q = rule.qualifiers

    source: dict[str, Any] = {
        "book": p.book_id,
        "edition": p.edition_id,
        "locator": p.locator,
        "quote": p.quoted_text,
        "quote_sha256": p.quote_sha256 or quote_sha256(p.quoted_text),
        "authority_tier": p.authority_tier,
    }
    if p.restates:
        source["restates"] = list(p.restates)
    if p.extraction:
        source["extraction"] = dict(p.extraction)
    source["review"] = dict(p.review) if p.review else {"state": "unreviewed"}

    doc: dict[str, Any] = {
        "id": rule.rule_id,
        "version": rule.version,
        "status": rule.status,
        "school": rule.school,
        "assertion": rule.assertion.value,
    }
    if rule.namespace:
        doc["namespace"] = rule.namespace
    if q.modality is not Modality.ASSERT:
        doc["modality"] = _MODALITY_OUT[q.modality]
    if q.targets_rule:
        doc["targets"] = q.targets_rule
    if q.factor is not None:
        doc["factor"] = q.factor
    if q.binding.value != "literal":
        doc["binding"] = q.binding.value
    if q.restriction.value != "open":
        doc["restriction"] = q.restriction.value
    if rule.domains:
        doc["domains"] = dict(rule.domains)

    doc["source"] = source

    observables = list(rule.antecedent.observables_required)
    if observables != ["chart"]:
        doc["observables"] = observables

    if rule.antecedent.expr is not None:
        doc["when"] = emit_expr(rule.antecedent.expr)

    doc.update(_emit_consequent(rule))

    timing: dict[str, Any] = {}
    if q.requires_activation:
        timing["requires_activation"] = True
    if q.timing:
        timing["activated_by"] = [dict(t) for t in q.timing]
    if timing:
        doc["timing"] = timing

    if q.corroboration_n:
        doc["corroboration"] = {"minimum_independent_sources": q.corroboration_n}
    if q.confidence:
        doc["confidence"] = dict(q.confidence)

    deps = rule.dependencies
    derived_produces = (
        [rule.consequent.fact_predicate]
        if rule.assertion is AssertionKind.DERIVE_FACT
        else []
    )
    if deps.tier or deps.reads or list(deps.produces) != derived_produces:
        block: dict[str, Any] = {}
        if deps.tier:
            block["tier"] = deps.tier
        if deps.reads:
            block["reads"] = list(deps.reads)
        if list(deps.produces) != derived_produces:
            block["produces"] = list(deps.produces)
        doc["dependencies"] = block

    return doc


# ==========================================================================
# Files
# ==========================================================================


class _Dumper(yaml.SafeDumper):
    """Block style, no aliases, and long quotes folded rather than escaped.

    `yaml.safe_dump` emits `&id001`/`*id001` anchors when the same string object
    appears twice - which happens constantly, because two rules from one verse
    share a quote. A reviewer should never have to resolve an anchor by hand.
    """

    def ignore_aliases(self, data: Any) -> bool:
        return True


def _str_representer(dumper: yaml.Dumper, data: str):
    style = ">" if len(data) > 90 and "\n" not in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _str_representer)


def dump_rules(rules: Iterable[Rule], *, header: str = "") -> str:
    docs = [emit_doc(r) for r in rules]
    body = yaml.dump(
        docs, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=88,
        default_flow_style=False,
    )
    if not header:
        return body
    return "".join(f"# {line}\n" if line else "#\n"
                   for line in header.strip().splitlines()) + "\n" + body


def write_rules(
    rules: Iterable[Rule],
    path: Path | str,
    *,
    header: str = "",
) -> Path:
    """Write a rule file. Overwrites - these files are generated artefacts.

    A generated file that appends would grow duplicates on every re-run, and the
    duplicate would compile, index and fire twice, which reads as two
    independent sources agreeing.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_rules(rules, header=header), encoding="utf-8")
    return path


def group_by_domain(rules: Iterable[Rule], *, default: str = "general") -> dict[str, list[Rule]]:
    """Rules bucketed into the file each belongs in.

    By heaviest domain, because that is how a reviewer looks for a rule - "show
    me the marriage rules" - not by book or by chapter. A rule with no domain
    tag lands in `general`, which is also where it will be noticed.
    """
    out: dict[str, list[Rule]] = {}
    for rule in rules:
        if rule.domains:
            top = max(rule.domains.items(), key=lambda kv: (kv[1], kv[0]))[0]
            name = top.removeprefix("domain.")
        else:
            name = default
        out.setdefault(name, []).append(rule)
    for bucket in out.values():
        bucket.sort(key=lambda r: r.rule_id)
    return out


def write_grouped(
    rules: Iterable[Rule],
    directory: Path | str,
    *,
    header: str = "",
) -> list[Path]:
    directory = Path(directory)
    written: list[Path] = []
    for name, bucket in sorted(group_by_domain(rules).items()):
        written.append(write_rules(bucket, directory / f"{name}.yaml", header=header))
    return written


def round_trips(rule: Rule, registry) -> tuple[bool, Optional[str]]:
    """Does this rule survive emit -> parse unchanged?

    Exposed rather than kept in the tests because the pipeline runs it on every
    emitted rule before writing. A rule that cannot be read back is a rule the
    reviewer would approve and the engine would never load.
    """
    from rishivan.koonji.compiler import parse_rule

    try:
        again = parse_rule(emit_doc(rule), registry)
    except Exception as exc:  # noqa: BLE001 - the reason is the payload
        return False, f"{type(exc).__name__}: {exc}"
    if again.content_hash() != rule.content_hash():
        return False, "content hash changed across the round trip"
    return True, None
