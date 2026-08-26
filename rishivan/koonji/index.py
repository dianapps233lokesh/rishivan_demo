"""koonji.index - exhaustive rule retrieval by set containment.

Rule retrieval is not a search problem. "Which rules have preconditions this
chart satisfies" has an exact, computable answer, and treating it as a ranking
problem introduces a failure that can never be measured: the rule sits in the
corpus, the embedding does not match, it never fires, and nobody finds out,
because you cannot compute recall against a denominator you do not know.

So retrieval here is a threshold set-containment query over an inverted index:

    atom -> the rule variants that require it
    variant -> how many atoms its core requires

A single pass over the chart's atoms accumulates a hit count per variant, and a
variant is a candidate exactly when its count reaches its core size. Exhaustive
by construction.

The invariant everything else rests on: **no false negatives.** Whatever cannot
be decided by set membership is left out of the core, which can only ever widen
the candidate set. Four things are excluded, and each exclusion is the reason
the invariant holds rather than a shortcut around it:

    negated leaves       a negative is not a fact the chart set contains
    numeric comparisons  the index saw a bucketed band, not the value
    variable leaves      the subject is not known until the VM unifies
    undecidable          nothing can be asserted about it either way

False positives are free - the VM prunes them with exact arithmetic. A false
negative is invisible forever.

Roaring bitmaps are what a production build would use for the postings. At the
corpus sizes this engine is planned for (single-digit thousands of rules) a
Python set is within noise of them, and the interface below is the same either
way, so the swap is local when it is worth making.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from rishivan.koonji.facts import AtomTable, FactSet, atom_name
from rishivan.koonji.registry import Registry
from rishivan.koonji.urf import (
    NON_SERVING_KINDS,
    ONTOLOGY_KINDS,
    AssertionKind,
    BoolExpr,
    PredicateCall,
    Rule,
)

#: Kinds that retrieval can return. Derivations execute exhaustively in tier
#: order and are never retrieved; ontology, procedure, guidance and worked
#: examples are consumed at compile time or by the benchmark harness, and none of
#: them answers a user's question.
RETRIEVABLE = {AssertionKind.ASSERT_CLAIM, AssertionKind.DIRECT_SUBJECT}
from rishivan.koonji.vm import is_var

#: DNF explosion guard. A rule normalising past this should be rewritten by its
#: author, not silently compiled into a bloated index.
VARIANT_LIMIT = 32


class MismatchedAtomTable(RuntimeError):
    """Facts and index interned against different tables.

    Caught loudly because the failure is otherwise invisible: integer ids would
    still compare, they would just mean different atoms, and retrieval would
    return a confident, wrong answer.
    """


class EmptyCore(ValueError):
    """A rule with no required conditions at all.

    This is not a permissive rule, it is a mis-authored one: it would fire on
    every chart ever cast, and a rule that fires on all of humanity is not
    diagnostic of anything.
    """


# ==========================================================================
# DNF normalisation
# ==========================================================================


def dnf_variants(expr: Optional[BoolExpr], limit: int = VARIANT_LIMIT) -> list[BoolExpr]:
    """Normalise to a list of conjunctive variants.

    All variants of one rule keep the rule's identity. That matters downstream:
    three variants of a single verse are one piece of evidence, and treating
    them as three would inflate confidence for a purely syntactic reason.
    """
    if expr is None:
        return []
    variants = _dnf(expr, limit)
    if len(variants) > limit:
        raise ValueError(
            f"rule normalises to {len(variants)} variants (limit {limit}); "
            f"rewrite it rather than indexing it"
        )
    return variants


def _conj(operands: list[BoolExpr]) -> BoolExpr:
    if len(operands) == 1 and operands[0].op == "all":
        return operands[0]
    return BoolExpr(op="all", operands=operands)


def _dnf(expr: BoolExpr, limit: int) -> list[BoolExpr]:
    if expr.op == "leaf":
        return [_conj([expr])]

    if expr.op == "any":
        out: list[BoolExpr] = []
        for operand in expr.operands:
            out.extend(_dnf(operand, limit))
            if len(out) > limit:
                raise ValueError(
                    f"rule normalises to more than {limit} variants; rewrite it"
                )
        return out

    if expr.op == "all":
        # Cartesian product across the operands' variant lists.
        combos: list[list[BoolExpr]] = [[]]
        for operand in expr.operands:
            operand_variants = _dnf(operand, limit)
            grown: list[list[BoolExpr]] = []
            for prefix in combos:
                for variant in operand_variants:
                    parts = variant.operands if variant.op == "all" else [variant]
                    grown.append(prefix + list(parts))
            combos = grown
            if len(combos) > limit:
                raise ValueError(
                    f"rule normalises to more than {limit} variants; rewrite it"
                )
        return [_conj(parts) for parts in combos]

    # `not`, `count` and `compare` are opaque to normalisation. Pushing De
    # Morgan through a negation would produce negated conjuncts, none of which
    # are indexable anyway; keeping the node whole and deferring it to the VM is
    # simpler and preserves the superset either way.
    return [_conj([expr])]


# ==========================================================================
# Core extraction
# ==========================================================================


def _indexable(call: PredicateCall, registry: Registry) -> bool:
    if call.negated:
        return False
    spec = registry.predicate(call.predicate)
    if spec is None or not spec.indexable:
        return False
    if any(is_var(v) for v in call.args.values()):
        return False
    return all(a.name in call.args for a in spec.args if not a.optional)


def _atom_for(call: PredicateCall, registry: Registry) -> str:
    spec = registry.predicate(call.predicate)
    assert spec is not None
    args = [str(call.args[a.name]) for a in spec.args if a.name in call.args]
    return atom_name(call.predicate, *args)


def extract_core(variant: BoolExpr, registry: Registry) -> tuple[set[str], bool]:
    """The ground positive atoms a variant requires, and whether it must be
    treated as an unconditional candidate.

    `always=True` means the variant has real conditions but none of them are
    ground - a threshold rule over `?x`, for instance. It joins every candidate
    set and the VM decides. That is a widening, so the invariant survives.
    """
    core: set[str] = set()
    has_conditions = False

    def walk(node: BoolExpr) -> None:
        nonlocal has_conditions
        if node.op == "leaf":
            assert node.leaf is not None
            has_conditions = True
            if _indexable(node.leaf, registry):
                core.add(_atom_for(node.leaf, registry))
            return
        if node.op == "all":
            for operand in node.operands:
                walk(operand)
            return
        # not / count / compare - the VM's job. Their presence still counts as a
        # condition, so the rule is not treated as unconditional.
        has_conditions = True

    walk(variant)
    if not has_conditions:
        raise EmptyCore("variant has no conditions at all")
    return core, not core


# ==========================================================================
# The index
# ==========================================================================


@dataclass(slots=True)
class Variant:
    variant_id: int
    rule_id: str
    core: frozenset[int]
    always: bool
    domains: dict[str, float]
    """domain id -> weight, as the rule declared them.

    The weights were being discarded here and the set of keys kept. That made
    `domain.wealth: 0.95, domain.career: 0.35` indistinguishable from a rule
    equally about both, so a career reading could be led by a wealth rule's
    incidental tag. See `in_scope`.
    """

    school: str
    status: str

    @property
    def core_size(self) -> int:
        return len(self.core)

    def in_scope(
        self,
        domains: Optional[set[str]],
        schools: Optional[set[str]],
        statuses: frozenset[str],
        min_domain_weight: float,
    ) -> bool:
        if self.status not in statuses:
            return False
        if schools is not None and self.school not in schools:
            return False
        if domains is None:
            return True
        if not self.domains:
            # An untagged rule makes no claim about which part of a life it
            # speaks to, so no domain filter can exclude it. Treating "no tags"
            # as "matches nothing" is the silent-recall failure this whole
            # retrieval design exists to avoid: the rule sits in the bundle,
            # never fires, and nobody can see the absence.
            return True
        # Present AND weighted at least the threshold. `.get(d, 0.0) >= 0.0`
        # would be true for every domain the rule does not carry at all.
        return any(
            d in self.domains and self.domains[d] >= min_domain_weight
            for d in domains
        )


@dataclass(slots=True)
class RuleIndex:
    """Built once at bundle-compile time, read-only thereafter."""

    table: AtomTable
    variants: list[Variant] = field(default_factory=list)
    postings: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    always: set[int] = field(default_factory=set)

    @classmethod
    def build(
        cls,
        rules: Iterable[Rule],
        registry: Registry,
        *,
        table: Optional[AtomTable] = None,
    ) -> "RuleIndex":
        index = cls(table=table if table is not None else AtomTable())
        index.postings = defaultdict(set)

        for rule in rules:
            if rule.assertion not in RETRIEVABLE:
                continue

            variants = dnf_variants(rule.antecedent.expr)
            if not variants:
                raise EmptyCore(
                    f"{rule.rule_id}: no antecedent - it would fire on every "
                    f"chart ever cast"
                )

            for variant in variants:
                names, always = extract_core(variant, registry)
                atom_ids = frozenset(index.table.intern(n) for n in names)
                v = Variant(
                    variant_id=len(index.variants),
                    rule_id=rule.rule_id,
                    core=atom_ids,
                    always=always,
                    domains=dict(rule.domains),
                    school=rule.school,
                    status=rule.status,
                )
                index.variants.append(v)
                if always:
                    index.always.add(v.variant_id)
                for atom_id in atom_ids:
                    index.postings[atom_id].add(v.variant_id)

            # Every atom the rule mentions is interned even when it is not part
            # of a core - the VM looks atoms up through this same table, and an
            # un-interned negated atom would silently read as absent.
            for variant in variants:
                _intern_all(variant, registry, index.table)

        return index

    def facts_for(self, chart, **kw) -> FactSet:
        """Compile a chart's facts against THIS index's atom table.

        The blessed way to get a fact set for querying. Interning against a
        different table would give the same atom two different integers, and
        retrieval would then be comparing numbers that mean nothing to each
        other - silently, and with plausible-looking output.
        """
        from rishivan.koonji.facts import compile_facts

        return compile_facts(chart, table=self.table, **kw)

    def query(
        self,
        facts: FactSet,
        *,
        domains: Optional[set[str]] = None,
        schools: Optional[set[str]] = None,
        statuses: frozenset[str] = frozenset({"production"}),
        min_domain_weight: float = 0.0,
    ) -> set[str]:
        """Rule ids whose preconditions this chart may satisfy.

        A superset of what will actually fire, by design.

        `domains=None` means unfiltered, and is not the same as an empty set.
        An empty set is "no domain is in scope", which retrieves nothing - a
        distinction that matters because a router that matched no phrase must
        widen the read, never narrow it to nothing.
        """
        if facts.table is not self.table:
            raise MismatchedAtomTable(
                "fact set was interned against a different atom table; the same "
                "atom would carry two different integers and every containment "
                "test would be meaningless. Build facts with `index.facts_for()`."
            )
        scope = [
            v
            for v in self.variants
            if v.in_scope(domains, schools, statuses, min_domain_weight)
        ]
        if not scope:
            return set()

        in_scope = {v.variant_id for v in scope}
        hits: dict[int, int] = defaultdict(int)
        for atom_id in facts.atoms:
            for variant_id in self.postings.get(atom_id, ()):
                if variant_id in in_scope:
                    hits[variant_id] += 1

        out: set[str] = set()
        for v in scope:
            if v.always:
                out.add(v.rule_id)
            elif hits.get(v.variant_id, 0) == v.core_size:
                out.add(v.rule_id)
        return out

    def domain_coverage(self) -> dict[str, int]:
        """domain id -> how many rules in this bundle carry the tag, at any
        weight and any status.

        Coverage is a property of the corpus, not of a chart or a filter, so it
        answers the question the other counters cannot: is this a domain we hold
        nothing about? A routed domain with zero coverage is a gap in the books
        we have ingested, and the honest response is to name it - not to widen
        the filter and answer a travel question with whatever fired.
        """
        counts: dict[str, int] = defaultdict(int)
        for rule_id, domains in {
            v.rule_id: v.domains for v in self.variants
        }.items():
            for domain in domains:
                counts[domain] += 1
        return dict(counts)

    def scope_size(
        self,
        *,
        domains: Optional[set[str]] = None,
        schools: Optional[set[str]] = None,
        statuses: frozenset[str] = frozenset({"production"}),
        min_domain_weight: float = 0.0,
    ) -> int:
        """How many variants the filter admits, before any chart is involved.

        This separates the two ways a query comes back empty, which look
        identical in the result and mean opposite things:

            scope_size == 0   the filter excluded the entire corpus. Nothing was
                              ever evaluated. A routing problem.
            scope_size  > 0   rules were evaluated against this chart and none
                              matched. The material is silent here. An answer.

        Conflating them is how a system ends up answering a marriage question
        with wealth rules because the marriage rules happened not to fire.
        """
        return sum(
            1
            for v in self.variants
            if v.in_scope(domains, schools, statuses, min_domain_weight)
        )

    def stats(self) -> dict[str, int]:
        return {
            "rules": len({v.rule_id for v in self.variants}),
            "variants": len(self.variants),
            "postings": len(self.postings),
            "atoms": len(self.table),
            "always_candidates": len(self.always),
        }


def _intern_all(node: BoolExpr, registry: Registry, table: AtomTable) -> None:
    if node.op == "leaf" and node.leaf is not None:
        call = node.leaf
        spec = registry.predicate(call.predicate)
        if spec is None:
            return
        if any(is_var(v) for v in call.args.values()):
            return
        if not all(a.name in call.args for a in spec.args if not a.optional):
            return
        table.intern(_atom_for(call, registry))
        return
    for operand in node.operands:
        _intern_all(operand, registry, table)
