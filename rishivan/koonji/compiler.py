"""koonji.compiler - rule sources in, a signed bundle out.

The Koonji is not a database of rules. It is a compiler, a virtual machine, a
test framework and a release system, and it should be treated exactly the way a
programming language implementation is treated, because that is what it is.

Rules are authored as YAML in Git, reviewed as pull requests, and compiled here.
Not edited in a web form against a live database - a knowledge base you cannot
diff, blame, revert and test is one you cannot defend when an astrologer asks
why a rule fired.

Eleven passes. The last two are the ones the source blueprint added after
reading real books, and they are the ones nobody builds:

     1 PARSE          YAML -> AST, with line numbers on syntax errors
     2 RESOLVE        aliases -> canonical ids. Unresolvable = hard error.
     3 TYPE CHECK     argument kinds, and cross-school leakage
     4 CLOSURE        every symbol published in the registry
     5 DNF            disjunctions -> conjunctive variants, explosion guarded
     6 CORE           the indexable atom set per variant. Empty = error.
     7 CONTRADICTION  internally unsatisfiable conditions
     8 REALIZABILITY  configurations that cannot physically occur
     9 STRATIFY       derivation tiers, acyclic
    10 TARGETS        cancellations that point at a rule which exists
    11 EMIT           bytecode-equivalent + index + lineage -> bundle

Pass 8 is worth its own note. A meaningful fraction of rules in secondary and
popularised astrology literature describe configurations that have never
occurred and never will - Mercury five houses from the Sun, a retrograde Rahu.
Ingest thirty thousand rules from mixed sources without this check and some
percentage of the corpus is dead weight that will never fire and that nobody
will ever notice, because a rule's absence is invisible.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

import yaml

from rishivan.koonji.index import EmptyCore, RuleIndex, dnf_variants, extract_core
from rishivan.koonji.registry import (
    HOUSE_GROUPS,
    Registry,
    UnresolvedSymbol,
    resolve_symbol,
)
from rishivan.koonji.urf import (
    Antecedent,
    AssertionKind,
    AttributeConsequent,
    BoolExpr,
    ClaimConsequent,
    ConsequentBinding,
    Corroboration,
    Dependencies,
    DirectiveConsequent,
    ExampleConsequent,
    FactConsequent,
    GuidanceConsequent,
    Modality,
    PredicateCall,
    ProcedureConsequent,
    Provenance,
    Qualifiers,
    Restriction,
    Rule,
    iter_leaves,
    iter_leaves_signed,
    validate_registry_closure,
    validate_stratification,
    validate_targets,
)
from rishivan.koonji.vm import is_var

Severity = Literal["error", "warning"]

#: Structural keys in a `when:` mapping. Anything else is read as a predicate.
_OPERATORS = {"all", "any", "not", "count", "compare"}


@dataclass(frozen=True, slots=True)
class Diagnostic:
    severity: Severity
    pass_name: str
    rule_id: str
    message: str
    where: str = ""

    def __str__(self) -> str:
        loc = f" [{self.where}]" if self.where else ""
        return f"{self.severity.upper()} {self.pass_name}: {self.rule_id}{loc}: {self.message}"


class CompileError(Exception):
    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics = diagnostics
        super().__init__("\n".join(str(d) for d in diagnostics))


@dataclass(slots=True)
class CompileResult:
    rules: list[Rule] = field(default_factory=list)
    index: Optional[RuleIndex] = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> "CompileResult":
        if self.errors:
            raise CompileError(self.errors)
        return self


# ==========================================================================
# Pass 1-2 - parse and resolve
# ==========================================================================


def _resolve_args(args: dict[str, Any], predicate: str, rule_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in args.items():
        # Operators and thresholds are literals, not symbols.
        if key in ("op", "n", "value", "count_n"):
            out[key] = value
            continue
        if isinstance(value, str):
            out[key] = resolve_symbol(value)
        elif isinstance(value, int):
            out[key] = resolve_symbol(str(value))
        else:
            out[key] = value
    return out


def _parse_expr(node: Any, rule_id: str) -> BoolExpr:
    """The authoring surface. A reviewer has to be able to write this by hand in
    ten minutes, so single-key mappings read as predicate calls and the operators
    are ordinary words."""
    if isinstance(node, list):
        return BoolExpr(op="all", operands=[_parse_expr(n, rule_id) for n in node])

    if not isinstance(node, dict) or len(node) != 1:
        raise ValueError(
            f"{rule_id}: each condition must be a single-key mapping, got {node!r}"
        )

    key, body = next(iter(node.items()))

    if key in ("all", "any"):
        if not isinstance(body, list):
            raise ValueError(f"{rule_id}: `{key}` takes a list")
        return BoolExpr(op=key, operands=[_parse_expr(n, rule_id) for n in body])

    if key == "not":
        return BoolExpr(op="not", operands=[_parse_expr(body, rule_id)])

    if key == "count":
        of = body.get("of")
        if of is None:
            raise ValueError(f"{rule_id}: `count` needs `of`")
        operands = (
            [_parse_expr(n, rule_id) for n in of]
            if isinstance(of, list)
            else [_parse_expr(of, rule_id)]
        )
        return BoolExpr(
            op="count", operands=operands,
            count_op=body.get("op", "gte"), count_n=int(body["n"]),
        )

    # A predicate call.
    args = dict(body or {})
    negated = bool(args.pop("negated", False))
    return BoolExpr(
        op="leaf",
        leaf=PredicateCall(
            predicate=key,
            args=_resolve_args(args, key, rule_id),
            negated=negated,
        ),
    )


_MODALITY_KEYS = {
    "cancel": Modality.CANCEL,
    "except": Modality.EXCEPT,
    "strengthen": Modality.STRENGTHEN,
    "weaken": Modality.WEAKEN,
    "activate": Modality.ACTIVATE,
    "assert": Modality.ASSERT,
}


CONSEQUENT_BLOCK: dict[AssertionKind, str] = {
    AssertionKind.ASSERT_CLAIM: "indicates",
    AssertionKind.DERIVE_FACT: "derives",
    AssertionKind.DEFINE_ATTRIBUTE: "defines",
    AssertionKind.DIRECT_SUBJECT: "remedy",
    AssertionKind.COMPUTE_VALUE: "computes",
    AssertionKind.DIRECT_INTERPRETER: "guidance",
    AssertionKind.RECORD_APPLICATION: "example",
}
"""Assertion kind -> the block its consequent must arrive in.

Exported so `prompts.py` can name them to the model rather than say "the
consequent block matching the assertion kind" and hope. A model that picked
`direct_interpreter` had no way to learn the block is called `guidance`, and the
result was `KeyError: 'guidance'` -- a Python error where a content error was
meant, reported against a rule the extractor had otherwise built correctly.
"""


REQUIRED_FIELDS: dict[AssertionKind, tuple[str, ...]] = {
    AssertionKind.ASSERT_CLAIM: ("claim",),
    AssertionKind.DERIVE_FACT: ("fact", "subject", "value"),
    AssertionKind.DEFINE_ATTRIBUTE: ("entity", "attribute", "values"),
    AssertionKind.DIRECT_SUBJECT: ("action",),
    AssertionKind.COMPUTE_VALUE: ("name",),
    AssertionKind.DIRECT_INTERPRETER: ("text",),
    AssertionKind.RECORD_APPLICATION: ("reading",),
}
"""What each consequent block must carry, checked before it is read.

Same failure as the missing block itself, one level down: the model emitted a
`defines` block without an `entity` and the compiler raised
`KeyError: 'entity'`, which names a dict key and not the rule, the kind, or what
the block should have contained. Five Phaladeepika rules were lost to that
message in a sixteen-passage run.
"""


def _block(doc: dict[str, Any], assertion: AssertionKind, rule_id: str) -> dict:
    """The consequent block for this assertion kind, or a usable complaint.

    `doc["guidance"]` raising `KeyError: 'guidance'` tells a reader which dict
    key was absent and nothing about which rule, which kind, or what was
    expected instead. Every kind below went through a bare subscript; only
    `derive_fact` had been given a message, presumably after someone hit it.
    """
    name = CONSEQUENT_BLOCK[assertion]
    block = doc.get(name)
    if not block:
        raise ValueError(
            f"{rule_id}: assertion `{assertion.value}` needs a `{name}` block "
            f"and the document has {sorted(doc) or 'no keys'}"
        )
    missing = [f for f in REQUIRED_FIELDS.get(assertion, ()) if block.get(f) is None]
    if missing:
        raise ValueError(
            f"{rule_id}: `{name}` block is missing {', '.join(missing)} "
            f"(it has {sorted(block) or 'no keys'})"
        )
    return block


def _build_consequent(doc: dict[str, Any], assertion: AssertionKind, rule_id: str):
    if assertion is AssertionKind.ASSERT_CLAIM:
        block = _block(doc, assertion, rule_id)
        return ClaimConsequent(
            claim_id=block["claim"],
            polarity=block.get("polarity", "positive"),
            magnitude=block.get("magnitude", "moderate"),
            literal_text=block.get("text", ""),
            transfer_source=block.get("transfer_source"),
            transfer_target=block.get("transfer_target"),
            transfer_cap=block.get("transfer_cap", 8),
            quantity=block.get("quantity"),
            quantity_max=block.get("quantity_max"),
            unit=block.get("unit"),
            bound=block.get("bound"),
        )
    if assertion is AssertionKind.DERIVE_FACT:
        block = _block(doc, assertion, rule_id)
        return FactConsequent(
            fact_predicate=block["fact"],
            subject_expr=_maybe_resolve(block["subject"]),
            object_expr=_maybe_resolve(block.get("object")),
            value=_maybe_resolve(block["value"]),
        )
    if assertion is AssertionKind.DEFINE_ATTRIBUTE:
        block = _block(doc, assertion, rule_id)
        return AttributeConsequent(
            entity_expr=_maybe_resolve(block["entity"]),
            attribute=block["attribute"],
            values=list(block["values"]),
            relation_to=block.get("relation_to"),
            ordered=block.get("ordered", False),
            exhaustive=block.get("exhaustive", False),
        )
    if assertion is AssertionKind.DIRECT_SUBJECT:
        block = _block(doc, assertion, rule_id)
        return DirectiveConsequent(
            injunction=block.get("injunction", "prescription"),
            acts_on=block.get("acts_on", "native"),
            acts_on_relation=block.get("acts_on_relation"),
            action_text=block["action"],
            materials=list(block.get("materials", [])),
            duration_days=block.get("duration_days"),
            weekday=block.get("weekday"),
        )
    if assertion is AssertionKind.COMPUTE_VALUE:
        block = _block(doc, assertion, rule_id)
        return ProcedureConsequent(
            computes=block["name"],
            method_note=block.get("note", ""),
            test_vectors=list(block.get("test_vectors", [])),
        )
    if assertion is AssertionKind.DIRECT_INTERPRETER:
        block = _block(doc, assertion, rule_id)
        return GuidanceConsequent(
            guidance_text=block["text"], applies_to=block.get("applies_to", "method")
        )
    block = _block(doc, AssertionKind.RECORD_APPLICATION, rule_id)
    return ExampleConsequent(
        chart_data=block.get("chart", {}),
        subject_note=block.get("subject"),
        authority_reading=block["reading"],
        cited_factors=list(block.get("cited_factors", [])),
        outcome_known=block.get("outcome_known", False),
    )


def _maybe_resolve(token: Optional[str]) -> Optional[str]:
    if token is None:
        return None
    try:
        return resolve_symbol(token)
    except UnresolvedSymbol:
        # Fact predicates and claim ids are registry entries in their own right
        # and are checked by the closure pass, not the alias table.
        return token


def parse_rule(doc: dict[str, Any], registry: Registry) -> Rule:
    """Passes 1 and 2: a YAML document becomes a resolved `Rule`."""
    rule_id = doc.get("id", "<unnamed>")
    assertion = AssertionKind(doc.get("assertion", "assert_claim"))

    when = doc.get("when")
    expr = _parse_expr(when, rule_id) if when is not None else None

    source = doc.get("source", {})
    provenance = Provenance(
        book_id=source.get("book", ""),
        edition_id=source.get("edition", ""),
        locator=source.get("locator", ""),
        quoted_text=source.get("quote", ""),
        quote_sha256=source.get("quote_sha256", ""),
        authority_tier=source.get("authority_tier", "S0"),
        restates=list(source.get("restates", [])),
        extraction=source.get("extraction", {}),
        review=source.get("review", {}),
    )

    modality = _MODALITY_KEYS[doc.get("modality", "assert")]
    timing = doc.get("timing", {}) or {}
    corroboration_block = doc.get("corroboration", {}) or {}
    minimum = corroboration_block.get("minimum_independent_sources")

    qualifiers = Qualifiers(
        modality=modality,
        binding=ConsequentBinding(doc.get("binding", "literal")),
        restriction=Restriction(doc.get("restriction", "open")),
        corroboration=(
            Corroboration.REQUIRES_N if minimum else Corroboration.STANDALONE
        ),
        corroboration_n=minimum,
        targets_rule=doc.get("targets"),
        factor=doc.get("factor"),
        timing=list(timing.get("activated_by", [])),
        requires_activation=bool(timing.get("requires_activation", False)),
        confidence=doc.get("confidence", {}) or {},
    )

    dependencies_block = doc.get("dependencies", {}) or {}
    derives = doc.get("derives") or {}
    dependencies = Dependencies(
        tier=dependencies_block.get("tier", 0),
        reads=list(dependencies_block.get("reads", [])),
        produces=list(
            dependencies_block.get(
                "produces", [derives["fact"]] if derives else []
            )
        ),
    )

    return Rule(
        rule_id=rule_id,
        version=str(doc.get("version", "1.0.0")),
        registry_version=registry.version,
        school=doc.get("school", "school.parashari"),
        namespace=doc.get("namespace", ""),
        domains={k: float(v) for k, v in (doc.get("domains") or {}).items()},
        status=doc.get("status", "draft"),
        antecedent=Antecedent(
            expr=expr,
            observables_required=list(doc.get("observables", ["chart"])),
        ),
        assertion=assertion,
        consequent=_build_consequent(doc, assertion, rule_id),
        qualifiers=qualifiers,
        dependencies=dependencies,
        provenance=provenance,
    )


# ==========================================================================
# Pass 3 - type check and cross-school leakage
# ==========================================================================


def check_types(rule: Rule, registry: Registry) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    for call in iter_leaves(rule.antecedent.expr):
        spec = registry.predicate(call.predicate)
        if spec is None:
            continue  # the closure pass owns this
        if spec.schools and rule.school not in spec.schools:
            out.append(Diagnostic(
                "error", "typecheck", rule.rule_id,
                f"{rule.school} rule uses {call.predicate!r}, which belongs to "
                f"{', '.join(spec.schools)} - cross-school leakage",
            ))
        declared = {a.name for a in spec.args}
        for name in call.args:
            if name not in declared:
                out.append(Diagnostic(
                    "error", "typecheck", rule.rule_id,
                    f"{call.predicate!r} has no argument {name!r} "
                    f"(expected {sorted(declared)})",
                ))
        for arg in spec.args:
            if arg.optional or arg.name not in call.args:
                if not arg.optional and arg.name not in call.args:
                    out.append(Diagnostic(
                        "error", "typecheck", rule.rule_id,
                        f"{call.predicate!r} is missing required argument {arg.name!r}",
                    ))
                continue
            value = call.args[arg.name]
            problem = _kind_mismatch(str(value), arg.kinds, registry)
            if problem:
                out.append(Diagnostic(
                    "error", "typecheck", rule.rule_id,
                    f"{call.predicate}.{arg.name} = {value!r}: {problem}",
                ))
    return out


_KIND_PREFIX = {
    "bhava": "bhava.", "rashi": "rashi.", "nakshatra": "nakshatra.",
    "dignity": "dignity.", "band": "band.", "varga": "varga.",
    "dasha_system": "dasha_system.", "dasha_level": "level.",
    "nature": "nature.", "friendship": "friendship.", "distance": "dist.",
    "reference": "ref.",
}


def _kind_mismatch(value: str, kinds: tuple[str, ...], registry: Registry) -> Optional[str]:
    if is_var(value):
        return None
    if "number" in kinds or "operator" in kinds:
        return None
    for kind in kinds:
        if kind == "graha_ref":
            if value.startswith(("graha.", "lord.bhava.", "karaka.", "chara.")):
                return None
        prefix = _KIND_PREFIX.get(kind)
        if prefix and value.startswith(prefix):
            return None
    return f"expected {' or '.join(kinds)}"


# ==========================================================================
# Pass 7 - contradiction
# ==========================================================================


def check_contradiction(rule: Rule, registry: Registry) -> list[Diagnostic]:
    """Conditions that cannot hold together.

    Not a general SMT check - a targeted one over the two structures that
    actually produce unsatisfiable rules in this domain: functional predicates
    given two values for one subject, and disjoint house groups.
    """
    out: list[Diagnostic] = []
    try:
        variants = dnf_variants(rule.antecedent.expr)
    except ValueError:
        return out

    for n, variant in enumerate(variants):
        assigned: dict[tuple[str, tuple[str, ...]], set[str]] = {}
        groups: dict[str, list[str]] = {}
        positives: set[tuple[str, tuple[str, ...]]] = set()
        negatives: set[tuple[str, tuple[str, ...]]] = set()

        for call, negated in iter_leaves_signed(variant):
            spec = registry.predicate(call.predicate)
            if spec is None:
                continue
            values = tuple(str(call.args.get(a.name, "")) for a in spec.args)
            key = (call.predicate, values)
            (negatives if negated else positives).add(key)

            if negated:
                continue

            if spec.functional and len(spec.args) >= 2:
                lead = tuple(values[:-1])
                if any(is_var(v) for v in values):
                    continue
                assigned.setdefault((call.predicate, lead), set()).add(values[-1])

            if call.predicate in HOUSE_GROUPS:
                subject = str(call.args.get("subject", ""))
                if not is_var(subject):
                    groups.setdefault(subject, []).append(call.predicate)

        for (predicate, lead), values in assigned.items():
            if len(values) > 1:
                out.append(Diagnostic(
                    "error", "contradiction", rule.rule_id,
                    f"variant {n}: {predicate}({', '.join(lead)}) is required to be "
                    f"both {' and '.join(sorted(values))} - unsatisfiable",
                ))

        for subject, names in groups.items():
            if len(names) < 2:
                continue
            houses = frozenset(range(1, 13))
            for name in names:
                houses &= HOUSE_GROUPS[name]
            if not houses:
                out.append(Diagnostic(
                    "error", "contradiction", rule.rule_id,
                    f"variant {n}: {subject} must be in {' and '.join(sorted(names))} "
                    f"at once, and those house sets are disjoint",
                ))

        both = positives & negatives
        for predicate, values in sorted(both):
            out.append(Diagnostic(
                "error", "contradiction", rule.rule_id,
                f"variant {n}: {predicate}({', '.join(values)}) is both required "
                f"and forbidden",
            ))
    return out


# ==========================================================================
# Pass 8 - astronomical realizability
# ==========================================================================

#: Maximum whole-sign separation from the Sun. Mercury never exceeds ~28 degrees
#: of elongation and Venus ~48, which caps them at one and two signs
#: respectively. A rule placing Mercury five houses from the Sun describes
#: something that has never happened and never will.
MAX_SIGN_SEPARATION_FROM_SUN = {"graha.mercury": 1, "graha.venus": 2}


def _house_of(variant: BoolExpr, subject: str) -> Optional[int]:
    for call, negated in iter_leaves_signed(variant):
        if negated or call.predicate != "occupies_bhava":
            continue
        if str(call.args.get("subject")) != subject:
            continue
        bhava = str(call.args.get("bhava", ""))
        if bhava.startswith("bhava."):
            return int(bhava.split(".")[1])
    return None


def check_realizability(rule: Rule, registry: Registry) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    try:
        variants = dnf_variants(rule.antecedent.expr)
    except ValueError:
        return out

    for n, variant in enumerate(variants):
        leaves = list(iter_leaves_signed(variant))

        sun_house = _house_of(variant, "graha.sun")
        if sun_house is not None:
            for graha, limit in MAX_SIGN_SEPARATION_FROM_SUN.items():
                house = _house_of(variant, graha)
                if house is None:
                    continue
                gap = min((house - sun_house) % 12, (sun_house - house) % 12)
                if gap > limit:
                    out.append(Diagnostic(
                        "error", "realizability", rule.rule_id,
                        f"variant {n}: {graha} placed {gap} signs from the Sun; its "
                        f"maximum elongation allows at most {limit}",
                    ))

        for call, negated in leaves:
            subject = str(call.args.get("subject", ""))

            # The nodes are always retrograde in the mean-node model, so
            # requiring direct motion describes nothing that occurs.
            if call.predicate == "retrograde" and subject in ("graha.rahu", "graha.ketu"):
                if negated:
                    out.append(Diagnostic(
                        "error", "realizability", rule.rule_id,
                        f"variant {n}: {subject} is required to be direct; the nodes "
                        f"are always retrograde in the mean-node model",
                    ))
            if call.predicate == "retrograde" and subject in ("graha.sun", "graha.moon"):
                if not negated:
                    out.append(Diagnostic(
                        "error", "realizability", rule.rule_id,
                        f"variant {n}: {subject} is never retrograde",
                    ))
            if call.predicate == "combust" and not negated and subject == "graha.sun":
                out.append(Diagnostic(
                    "error", "realizability", rule.rule_id,
                    f"variant {n}: the Sun cannot be combust itself",
                ))
            # Rahu and Ketu are exactly opposed, so they are never together.
            if call.predicate in ("conjunct", "same_bhava") and not negated:
                pair = {subject, str(call.args.get("other", ""))}
                if pair == {"graha.rahu", "graha.ketu"}:
                    out.append(Diagnostic(
                        "error", "realizability", rule.rule_id,
                        f"variant {n}: Rahu and Ketu are exactly 180 degrees apart "
                        f"and are never conjunct",
                    ))
    return out


# ==========================================================================
# Provenance gate - what `production` is allowed to mean
# ==========================================================================


def check_provenance(rule: Rule) -> list[Diagnostic]:
    """A production rule must be source-linked and reviewer-approved.

    Every plan for this system says the same thing and says it emphatically:
    reviewer throughput, not model quality, is the real bottleneck, and the
    pressure to let extraction auto-publish in order to hit a date will be
    considerable. A dirty knowledge base makes a sophisticated model worse, not
    better, so the gate is a compile error rather than a convention.

    Candidate and draft rules carry no such requirement. They just cannot be
    served.
    """
    if rule.status != "production":
        return []

    out: list[Diagnostic] = []
    if not rule.provenance.quoted_text:
        out.append(Diagnostic(
            "error", "provenance", rule.rule_id,
            "production rule has no quoted source text - a claim nobody can "
            "check against the verse is not defensible",
        ))
    if not rule.provenance.locator:
        out.append(Diagnostic(
            "error", "provenance", rule.rule_id,
            "production rule has no verse locator",
        ))
    if not rule.provenance.review.get("reviewer"):
        out.append(Diagnostic(
            "error", "provenance", rule.rule_id,
            "production rule has no reviewer - a rule that fires on four hundred "
            "thousand charts and is wrong is a systemic defect, not a bad reading",
        ))
    return out


# ==========================================================================
# The driver
# ==========================================================================


def load_yaml_dir(path: Path | str) -> list[dict[str, Any]]:
    """Every rule document under a directory, in a stable order."""
    root = Path(path)
    docs: list[dict[str, Any]] = []
    for file in sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml")):
        loaded = yaml.safe_load(file.read_text())
        if loaded is None:
            continue
        for doc in loaded if isinstance(loaded, list) else [loaded]:
            doc.setdefault("_source_file", str(file))
            docs.append(doc)
    return docs


def compile_rules(
    docs: Iterable[dict[str, Any]], registry: Registry
) -> CompileResult:
    """Run every pass. Errors accumulate rather than aborting, so one broken
    rule does not hide the other nine."""
    result = CompileResult()
    rules: list[Rule] = []

    for doc in docs:
        rule_id = doc.get("id", "<unnamed>")
        where = doc.get("_source_file", "")
        try:
            rule = parse_rule({k: v for k, v in doc.items() if k != "_source_file"}, registry)
        except UnresolvedSymbol as exc:
            result.diagnostics.append(
                Diagnostic("error", "resolve", rule_id, str(exc), where)
            )
            continue
        except Exception as exc:  # noqa: BLE001 - parse errors are reported, not raised
            result.diagnostics.append(
                Diagnostic("error", "parse", rule_id, str(exc), where)
            )
            continue

        diagnostics = (
            check_types(rule, registry)
            + check_provenance(rule)
            + [
                Diagnostic("error", "closure", rule.rule_id, message, where)
                for message in validate_registry_closure(rule, registry.as_closure())
            ]
            + check_contradiction(rule, registry)
            + check_realizability(rule, registry)
        )
        result.diagnostics.extend(
            Diagnostic(d.severity, d.pass_name, d.rule_id, d.message, where)
            for d in diagnostics
        )
        rules.append(rule)

    # Corpus-wide passes.
    for message in _check_duplicate_ids(rules):
        result.diagnostics.append(
            Diagnostic("error", "duplicate", "<corpus>", message)
        )
    for message in _check_claim_polarity(rules):
        result.diagnostics.append(
            Diagnostic("warning", "polarity", "<corpus>", message)
        )
    for message in validate_stratification(rules):
        result.diagnostics.append(Diagnostic("error", "stratify", "<corpus>", message))
    for message in validate_targets(rules):
        result.diagnostics.append(Diagnostic("error", "targets", "<corpus>", message))

    result.rules = rules

    # Only build the index over rules that survived, and only when nothing is
    # broken - an index over a corpus with a known error is a trap.
    if result.ok:
        try:
            result.index = RuleIndex.build(rules, registry)
        except (EmptyCore, ValueError) as exc:
            result.diagnostics.append(
                Diagnostic("error", "core", "<corpus>", str(exc))
            )
    return result


def _check_duplicate_ids(rules: list[Rule]) -> list[str]:
    """Two rules sharing an id.

    Nothing downstream treats this as an error, which is exactly the problem: a
    duplicated rule compiles twice, gets two index variants, fires twice, and
    lands in the evidence graph as two supports. The independence accounting
    then reads it as two sources agreeing and raises confidence for it. A
    corpus assembled from more than one directory - hand-authored plus generated
    - can produce this without anybody doing anything wrong.

    An error rather than a warning. There is no reading of a duplicate id under
    which the corpus is correct.
    """
    from collections import Counter

    counts = Counter(rule.rule_id for rule in rules)
    return [
        f"rule id {rule_id!r} appears {n} times - it would fire {n} times and "
        f"count as {n} independent sources"
        for rule_id, n in sorted(counts.items()) if n > 1
    ]


def _check_claim_polarity(rules: list[Rule]) -> list[str]:
    """A claim that is only ever denied and never asserted.

    Almost always a mis-authored polarity. `polarity` is the rule's stance
    toward the claim, not the valence of the outcome, and the trap is that a
    verse describing something unwelcome reads as "negative" to an author. The
    result is a claim with counter-evidence and nothing to counter, which the
    evidence graph then drops - silently, unless something says this.
    """
    asserted: set[str] = set()
    denied: set[str] = set()
    for rule in rules:
        if not isinstance(rule.consequent, ClaimConsequent):
            continue
        target = denied if rule.consequent.polarity == "negative" else asserted
        target.add(rule.consequent.claim_id)
    return [
        f"claim {claim!r} is denied by some rule and asserted by none - check "
        f"whether `polarity: negative` was meant as a stance or as a valence"
        for claim in sorted(denied - asserted)
    ]


def compile_path(path: Path | str, registry: Registry) -> CompileResult:
    return compile_rules(load_yaml_dir(path), registry)
