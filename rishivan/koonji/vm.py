"""koonji.vm - antecedent evaluation and derivation execution.

Two properties here carry most of the engine's honesty.

**Evaluation is tri-valued.** TRUE, FALSE, and UNKNOWN are three different
answers, and the third one is not a bug. A rule resting on Shadbala, which this
stack does not compute, evaluates to UNKNOWN and its firing is INDETERMINATE.
Collapsing that into NOT_APPLICABLE would let the engine report "the classical
indications do not apply here" when what it actually means is "I could not
tell" - a difference the user has no way to detect, which makes it the worst
kind of error this system can make.

**Variables unify against the fact set.** Classical derivations are stated over
pairs: *"if a planet is in the 2nd, 4th, 10th or 12th from another, they are
temporary friends."* A rule language with no way to say "another" forces either
seventy-two hand-written rules or an approximation, and the extension protocol
forbids the second. So a leaf argument beginning with `?` is a variable, bound
by matching against the atoms present, and joined across conjuncts.

Ground rules - the overwhelming majority - never touch the unifier. They are
pure set membership against a frozenset of interned integers, which is the fast
path the whole fact-compiler design exists to produce.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Iterable, Optional

from rishivan.koonji.facts import FactSet, atom_name
from rishivan.koonji.registry import CAPTURABLE_OBSERVABLES, Registry
from rishivan.koonji.urf import (
    AssertionKind,
    BoolExpr,
    ClaimConsequent,
    FactConsequent,
    Modality,
    PredicateCall,
    Restriction,
    Rule,
)

Binding = dict[str, str]

#: The empty binding: a ground success with nothing bound.
GROUND: Binding = {}


def is_var(token: object) -> bool:
    return isinstance(token, str) and token.startswith("?")


class Outcome(str, Enum):
    FIRED = "fired"
    CANCELLED = "cancelled"
    NOT_APPLICABLE = "not_applicable"
    INDETERMINATE = "indeterminate"
    """The antecedent could not be decided - a predicate this chart cannot
    answer. Distinct from NOT_APPLICABLE, deliberately and importantly."""
    WITHHELD = "withheld"
    """The rule needs an observable the product cannot capture, or is marked
    never-user-facing. It is in the corpus and structurally unreachable."""


@dataclass(frozen=True, slots=True)
class Solutions:
    """The result of evaluating an expression: which variable bindings satisfy
    it, and whether any branch could not be decided."""

    bindings: tuple[Binding, ...] = ()
    unknown: bool = False
    undecided: frozenset[str] = frozenset()
    """Predicate ids that returned UNKNOWN, for the firing's reason string."""

    def truthy(self) -> bool:
        return bool(self.bindings)


FALSE = Solutions()
TRUE = Solutions(bindings=(GROUND,))


def _unknown(predicate: str) -> Solutions:
    return Solutions(bindings=(), unknown=True, undecided=frozenset({predicate}))


@dataclass(slots=True)
class Firing:
    rule_id: str
    version: str
    outcome: Outcome
    strength: float = 1.0
    claim_id: Optional[str] = None
    bindings: tuple[Binding, ...] = ()
    modifiers: list[str] = field(default_factory=list)
    cancelled_by: list[str] = field(default_factory=list)
    reason: str = ""

    @property
    def counts(self) -> bool:
        """Whether this firing may contribute evidence to an answer."""
        return self.outcome is Outcome.FIRED


# ==========================================================================
# Pattern matching over the fact set
# ==========================================================================


class _AtomIndex:
    """predicate -> the argument tuples present, for variable matching.

    Built once per fact set and only when a rule actually contains a variable;
    ground rules never pay for it.
    """

    __slots__ = ("_by_predicate",)

    def __init__(self, facts: FactSet) -> None:
        by_predicate: dict[str, list[tuple[str, ...]]] = defaultdict(list)
        for name in facts.atom_names():
            predicate, _, rest = name.partition("(")
            by_predicate[predicate].append(tuple(rest.rstrip(")").split(",")))
        self._by_predicate = dict(by_predicate)

    def match(self, predicate: str, pattern: tuple[str, ...]) -> list[Binding]:
        out: list[Binding] = []
        for args in self._by_predicate.get(predicate, ()):
            if len(args) != len(pattern):
                continue
            binding: Binding = {}
            for slot, value in zip(pattern, args):
                if is_var(slot):
                    existing = binding.get(slot)
                    if existing is not None and existing != value:
                        break
                    binding[slot] = value
                elif slot != value:
                    break
            else:
                out.append(binding)
        return out


@dataclass(slots=True)
class Context:
    facts: FactSet
    registry: Registry
    _index: Optional[_AtomIndex] = None

    def index(self) -> _AtomIndex:
        if self._index is None:
            self._index = _AtomIndex(self.facts)
        return self._index


# ==========================================================================
# Leaf evaluation
# ==========================================================================


def _positional(call: PredicateCall, registry: Registry) -> Optional[tuple[str, ...]]:
    """Map the call's keyword args into the predicate's declared arg order.

    Returns None when the predicate is unregistered - which the compiler should
    already have rejected, but the VM must not guess an order if it slips
    through, because guessing produces a rule that fires on the wrong charts.
    """
    spec = registry.predicate(call.predicate)
    if spec is None:
        return None
    out: list[str] = []
    for arg in spec.args:
        if arg.name not in call.args:
            if arg.optional:
                continue
            return None
        out.append(str(call.args[arg.name]))
    return tuple(out)


_COMPARE = {
    "gte": lambda a, b: a >= b,
    "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
}


def _eval_numeric(call: PredicateCall, ctx: Context) -> Solutions:
    """Exact comparison against the side table.

    The index only ever saw a bucketed band for these; this is where the
    superset it produced gets pruned with real arithmetic.
    """
    spec = ctx.registry.predicate(call.predicate)
    if spec is None:
        return _unknown(call.predicate)

    subject_arg = spec.args[0].name
    subject = str(call.args.get(subject_arg, ""))
    if is_var(subject):
        # A numeric comparison over an unbound subject would have to enumerate
        # the side table; no seed rule needs it, and silently returning FALSE
        # would be a false negative.
        return _unknown(call.predicate)

    key = f"{call.predicate}({subject})"
    value = ctx.facts.exact.get(key)
    if value is None:
        return _unknown(call.predicate)

    op = str(call.args.get("op", "eq"))
    threshold = call.args.get("n", call.args.get("value"))
    compare = _COMPARE.get(op)
    if compare is None or threshold is None:
        return _unknown(call.predicate)
    return TRUE if compare(value, float(threshold)) else FALSE


def _eval_comparative(call: PredicateCall, ctx: Context) -> Solutions:
    """`stronger_than` - needs an exact value for both sides."""
    a = str(call.args.get("subject", ""))
    b = str(call.args.get("other", ""))
    if is_var(a) or is_var(b):
        return _unknown(call.predicate)
    left = ctx.facts.exact.get(f"strength({a})")
    right = ctx.facts.exact.get(f"strength({b})")
    if left is None or right is None:
        return _unknown(call.predicate)
    return TRUE if left > right else FALSE


def _eval_leaf(call: PredicateCall, ctx: Context) -> Solutions:
    predicate = call.predicate

    if predicate in ctx.facts.undecidable:
        return _unknown(predicate)

    spec = ctx.registry.predicate(predicate)
    if spec is None:
        # Unregistered. The compiler's closure pass is the place this is
        # supposed to die; if it reaches here, refuse to guess.
        return _unknown(predicate)

    if predicate == "stronger_than":
        result = _eval_comparative(call, ctx)
    elif spec.evaluation in ("numeric", "count"):
        result = _eval_numeric(call, ctx)
    else:
        args = _positional(call, ctx.registry)
        if args is None:
            return _unknown(predicate)
        if any(is_var(a) for a in args):
            bindings = ctx.index().match(predicate, args)
            result = Solutions(bindings=tuple(bindings))
        else:
            result = TRUE if ctx.facts.has(predicate, *args) else FALSE

    if call.negated:
        result = _negate(result)
    return result


def _negate(inner: Solutions) -> Solutions:
    """Negation as failure. UNKNOWN stays UNKNOWN - the one case where
    three-valued logic is doing visible work."""
    if inner.unknown:
        return inner
    return FALSE if inner.truthy() else TRUE


# ==========================================================================
# Expression evaluation
# ==========================================================================


def _join(left: Iterable[Binding], right: Iterable[Binding]) -> tuple[Binding, ...]:
    """Natural join on shared variables."""
    right = list(right)
    out: list[Binding] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for a in left:
        for b in right:
            merged = dict(a)
            for k, v in b.items():
                if k in merged and merged[k] != v:
                    break
                merged[k] = v
            else:
                key = tuple(sorted(merged.items()))
                if key not in seen:
                    seen.add(key)
                    out.append(merged)
    return tuple(out)


def _dedupe(bindings: Iterable[Binding]) -> tuple[Binding, ...]:
    out: list[Binding] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for b in bindings:
        key = tuple(sorted(b.items()))
        if key not in seen:
            seen.add(key)
            out.append(b)
    return tuple(out)


def evaluate(expr: Optional[BoolExpr], facts: FactSet, registry: Registry) -> Solutions:
    """Evaluate an antecedent. `None` means unconditional, which is TRUE."""
    if expr is None:
        return TRUE
    return _eval(expr, Context(facts=facts, registry=registry))


def _eval(expr: BoolExpr, ctx: Context) -> Solutions:
    if expr.op == "leaf":
        assert expr.leaf is not None
        return _eval_leaf(expr.leaf, ctx)

    if expr.op == "not":
        return _negate(_eval(expr.operands[0], ctx))

    if expr.op == "all":
        # A definite FALSE short-circuits: if one conjunct cannot hold, the rule
        # cannot fire and the undecidable rest does not matter.
        current: tuple[Binding, ...] = (GROUND,)
        unknown = False
        undecided: set[str] = set()
        for operand in expr.operands:
            result = _eval(operand, ctx)
            if result.unknown:
                unknown = True
                undecided |= result.undecided
                continue
            if not result.truthy():
                return FALSE
            current = _join(current, result.bindings)
            if not current:
                return FALSE
        if unknown:
            return Solutions(bindings=(), unknown=True, undecided=frozenset(undecided))
        return Solutions(bindings=current)

    if expr.op in ("any", "compare"):
        # A definite TRUE short-circuits for the same reason, mirrored.
        collected: list[Binding] = []
        unknown = False
        undecided: set[str] = set()
        for operand in expr.operands:
            result = _eval(operand, ctx)
            if result.unknown:
                unknown = True
                undecided |= result.undecided
                continue
            collected.extend(result.bindings)
        if collected:
            return Solutions(bindings=_dedupe(collected))
        if unknown:
            return Solutions(bindings=(), unknown=True, undecided=frozenset(undecided))
        return FALSE

    if expr.op == "count":
        assert expr.count_op is not None and expr.count_n is not None
        compare = _COMPARE[expr.count_op]
        if len(expr.operands) == 1:
            # Count distinct solutions - "three or more planets in kendras".
            result = _eval(expr.operands[0], ctx)
            if result.unknown and not result.bindings:
                return result
            return TRUE if compare(len(result.bindings), expr.count_n) else FALSE
        # Several operands: count how many hold.
        hits = 0
        unknown = False
        undecided: set[str] = set()
        for operand in expr.operands:
            result = _eval(operand, ctx)
            if result.unknown:
                unknown = True
                undecided |= result.undecided
            elif result.truthy():
                hits += 1
        if unknown and not compare(hits, expr.count_n):
            # An undecided operand could still tip the count, so we do not know.
            return Solutions(bindings=(), unknown=True, undecided=frozenset(undecided))
        return TRUE if compare(hits, expr.count_n) else FALSE

    raise ValueError(f"unknown operator {expr.op!r}")


# ==========================================================================
# Rule execution
# ==========================================================================


def _servable(rule: Rule, facts: FactSet) -> Optional[str]:
    """Why this rule must not be served, or None."""
    if rule.qualifiers.restriction is Restriction.NEVER_USER_FACING:
        return "marked never_user_facing at extraction"
    missing = [
        o
        for o in rule.antecedent.observables_required
        if o not in facts.observables or o not in CAPTURABLE_OBSERVABLES
    ]
    if missing:
        return f"requires observables this product cannot capture: {', '.join(sorted(missing))}"
    return None


def _evaluate_rule(rule: Rule, facts: FactSet, registry: Registry) -> Firing:
    claim_id = (
        rule.consequent.claim_id if isinstance(rule.consequent, ClaimConsequent) else None
    )
    withheld = _servable(rule, facts)
    if withheld:
        return Firing(
            rule_id=rule.rule_id, version=rule.version,
            outcome=Outcome.WITHHELD, claim_id=claim_id, reason=withheld,
        )

    result = evaluate(rule.antecedent.expr, facts, registry)
    if result.unknown and not result.truthy():
        return Firing(
            rule_id=rule.rule_id, version=rule.version,
            outcome=Outcome.INDETERMINATE, claim_id=claim_id,
            reason="undecidable: " + ", ".join(sorted(result.undecided)),
        )
    if not result.truthy():
        return Firing(
            rule_id=rule.rule_id, version=rule.version,
            outcome=Outcome.NOT_APPLICABLE, claim_id=claim_id,
        )
    return Firing(
        rule_id=rule.rule_id, version=rule.version,
        outcome=Outcome.FIRED, claim_id=claim_id, bindings=result.bindings,
    )


def execute(rules: Iterable[Rule], facts: FactSet, registry: Registry) -> list[Firing]:
    """Evaluate a candidate set, then settle modality between the survivors.

    Order matters and is fixed: everything is evaluated against the same fact
    set first, and only then do cancellations and modifiers apply. Evaluating
    and settling in one pass would make the result depend on rule order.
    """
    rules = list(rules)
    firings = {r.rule_id: _evaluate_rule(r, facts, registry) for r in rules}

    for rule in rules:
        q = rule.qualifiers
        target = q.targets_rule
        if not target or target not in firings:
            continue
        if firings[rule.rule_id].outcome is not Outcome.FIRED:
            continue
        victim = firings[target]
        if q.modality is Modality.CANCEL:
            victim.cancelled_by.append(rule.rule_id)
        elif q.modality in (Modality.STRENGTHEN, Modality.WEAKEN):
            victim.strength *= q.factor or 1.0
            victim.modifiers.append(rule.rule_id)

    # Cancellation is absolute. A cancelled yoga is cancelled however well
    # supported it was, so this runs after every modifier has been applied.
    for firing in firings.values():
        if firing.cancelled_by and firing.outcome is Outcome.FIRED:
            firing.outcome = Outcome.CANCELLED
            firing.reason = "cancelled by " + ", ".join(firing.cancelled_by)

    # Modality rules are machinery, not evidence. They are reported for the
    # trace but never presented as findings in their own right.
    return [firings[r.rule_id] for r in rules]


# ==========================================================================
# Derivation - the tier that has to run before anything else
# ==========================================================================


def _resolve(token: str, binding: Binding) -> Optional[str]:
    if is_var(token):
        return binding.get(token)
    return token


def run_derivations(
    rules: Iterable[Rule], facts: FactSet, registry: Registry
) -> FactSet:
    """Execute DERIVE_FACT rules in stratified tier order.

    Each tier reads only what tiers below it produced. Rules inside one tier are
    invisible to each other by construction - that is what stratification means,
    and without it the answer would depend on which rule happened to run first.

    Returns a new FactSet. The input is never mutated: a derivation pass that
    edited its own input in place would make a chart's facts depend on how many
    times they had been read.
    """
    derivations = [
        r for r in rules if r.assertion is AssertionKind.DERIVE_FACT
    ]
    if not derivations:
        return facts

    by_tier: dict[int, list[Rule]] = defaultdict(list)
    for rule in derivations:
        by_tier[rule.dependencies.tier].append(rule)

    atoms = set(facts.atoms)
    table = facts.table
    current = facts

    for tier in sorted(by_tier):
        produced: set[str] = set()
        for rule in by_tier[tier]:
            if _servable(rule, current):
                continue
            result = evaluate(rule.antecedent.expr, current, registry)
            if not result.truthy():
                continue
            consequent = rule.consequent
            assert isinstance(consequent, FactConsequent)
            spec = registry.predicate(consequent.fact_predicate)
            if spec is None:
                continue
            for binding in result.bindings:
                subject = _resolve(consequent.subject_expr, binding)
                value = _resolve(consequent.value, binding)
                if subject is None or value is None:
                    continue
                args = [subject]
                if consequent.object_expr is not None:
                    obj = _resolve(consequent.object_expr, binding)
                    if obj is None:
                        continue
                    if obj == subject:
                        # A body is not its own friend, enemy or anything else.
                        continue
                    args.append(obj)
                args.append(value)
                if len(args) != spec.arity():
                    continue
                produced.add(atom_name(consequent.fact_predicate, *args))

        # Applied as one batch, at the tier boundary - never mid-tier.
        for name in produced:
            atoms.add(table.intern(name))
        current = replace(current, atoms=frozenset(atoms))

    return current
