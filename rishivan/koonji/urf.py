"""koonji.urf — the Universal Rule Frame.

Replaces the T0..T22 enum as a SCHEMA. The T-codes survive as a derived view
(see `project_tcode`), useful for talking to astrologers and for corpus stats,
but nothing in the engine depends on them.

    CLOSED  (fixed by logic)          OPEN (registries, additive-only)
    -------------------------         -------------------------------
    7 assertion kinds                 predicates
    the frame itself                  entities
    modality algebra                  observables
    extension protocol                claims
                                      units
                                      school namespaces

Adding Lal Kitab's `khana`, a BaZi Ten God, or Prasna's breath observation is a
registry INSERT. None of them touch this file.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

FRAME_VERSION = "3.0.0"


# ==========================================================================
# CLOSED CORE 1/3 - the seven assertion kinds
#
# Closure argument: a rule maps observed state -> output. The output can only
# target one of seven things. See UNIVERSAL_FRAME.md Part 1.
# ==========================================================================


class AssertionKind(str, Enum):
    DERIVE_FACT = "derive_fact"
    """Writes a new fact to the observed state, INTERPRETIVELY.
    School-dependent and contested -> must be sourced and versioned.
    e.g. temporary friendship, functional malefic status, Arudha, Chara karakas."""

    COMPUTE_VALUE = "compute_value"
    """Writes to the observed state DETERMINISTICALLY. Uncontested between
    schools -> belongs in the chart engine, not the rule store.
    e.g. planetary longitude, Vimshottari boundaries, D9 construction.

    The boundary with DERIVE_FACT is exactly: can two respected authorities
    disagree? If yes, it is a derivation."""

    ASSERT_CLAIM = "assert_claim"
    """Says something about the subject's life. The point of the system."""

    DEFINE_ATTRIBUTE = "define_attribute"
    """Says something about the VOCABULARY, not about any subject.
    e.g. 'the Sun is the soul'; the 11th house's thirty significations;
    the natural friendship matrix."""

    DIRECT_SUBJECT = "direct_subject"
    """Instructs the subject to act or refrain. Remedies, prohibitions."""

    DIRECT_INTERPRETER = "direct_interpreter"
    """Instructs the reasoner. Method guidance, precedence advice."""

    RECORD_APPLICATION = "record_application"
    """A worked example: a chart plus an authority's reading of it.
    Routes to the benchmark corpus, never to the rule store."""


#: Kinds that are retrievable when answering a user question.
SERVING_KINDS = {AssertionKind.DERIVE_FACT, AssertionKind.ASSERT_CLAIM}

#: Kinds that populate the ontology at bundle-compile time.
ONTOLOGY_KINDS = {AssertionKind.DEFINE_ATTRIBUTE}

#: Kinds that reach the user, but never through the claim path. A remedy is
#: presented as traditional practice on its own surface; routing it through
#: ASSERT_CLAIM would let it be phrased as a prediction, which is exactly what
#: every planning document forbids.
REMEDY_KINDS = {AssertionKind.DIRECT_SUBJECT}

#: Kinds that never reach the serving path at all.
NON_SERVING_KINDS = {
    AssertionKind.COMPUTE_VALUE,
    AssertionKind.DIRECT_INTERPRETER,
    AssertionKind.RECORD_APPLICATION,
}

#: Every kind has exactly one destination. A kind that belongs to no set is a
#: leak: it would be extracted, stored, and then reached by whichever code path
#: happened not to filter it out.
assert (
    SERVING_KINDS | ONTOLOGY_KINDS | REMEDY_KINDS | NON_SERVING_KINDS
) == set(AssertionKind)


# ==========================================================================
# CLOSED CORE 2/3 - the qualifier algebra
#
# Everything the old taxonomy split into T9/T10/T11/T12/T19/T21 is four
# ORTHOGONAL axes here. Orthogonality is the point: a cancelled + transferred +
# restricted claim is expressible without inventing a new code for it.
# ==========================================================================


class Modality(str, Enum):
    ASSERT = "assert"           # states a result outright
    STRENGTHEN = "strengthen"   # amplifies a result stated elsewhere    (was T9)
    WEAKEN = "weaken"           #                                        (was T9)
    CANCEL = "cancel"           # negates it - bhanga                    (was T10)
    EXCEPT = "except"           # replaces it under conditions           (was T11)
    ACTIVATE = "activate"       # says WHEN it manifests                 (was T12)


#: Modalities that operate on another rule and therefore require `targets_rule`.
DEPENDENT_MODALITIES = {
    Modality.CANCEL,
    Modality.EXCEPT,
    Modality.STRENGTHEN,
    Modality.WEAKEN,
}


class ConsequentBinding(str, Enum):
    LITERAL = "literal"          # a fixed claim                       (was T3-T8)
    TRANSFERRED = "transferred"  # "spouse acquires Venus's qualities"  (was T19)
    QUANTIFIED = "quantified"    # "the child lives 4 years"            (was T21)
    PATTERNED = "patterned"      # a template over an entity set


class Restriction(str, Enum):
    OPEN = "open"
    RESTRICTED = "restricted"                # extra guardrails at serve time
    NEVER_USER_FACING = "never_user_facing"  # in corpus, unreachable from serving


class Corroboration(str, Enum):
    STANDALONE = "standalone"
    REQUIRES_N = "requires_n"
    REQUIRES_NAMED = "requires_named"


# ==========================================================================
# OPEN REGISTRIES - designed to grow. Additive only, ever.
# ==========================================================================


class RegistryKind(str, Enum):
    PREDICATE = "predicate"    # occupies, aspects, touches, transforms_into
    ENTITY = "entity"          # graha.mars, lalkitab.khana.05, ziwei.star.tanlang
    OBSERVABLE = "observable"  # chart, breath, palm_line, name, hexagram
    CLAIM = "claim"            # wealth.gain, spouse.temperament
    UNIT = "unit"              # years, count, multiple
    NAMESPACE = "namespace"    # school.lalkitab


class RegistryEntry(BaseModel):
    """One row. Immutable once published; superseded, never edited."""

    registry: RegistryKind
    entry_id: str
    namespace: str = ""
    signature: dict[str, Any] = Field(default_factory=dict)
    label: str = ""
    introduced_in: str = Field(description="Registry version that added it.")
    introduced_by: str = Field(description="Extension proposal ID or 'seed'.")
    superseded_by: Optional[str] = None
    note: str = ""


class ExtensionProposal(BaseModel):
    """Emitted when the extractor meets something it cannot express.

    This is the mechanism that makes the frame universal in the only achievable
    sense: the corpus tells you what the vocabulary is missing, with evidence
    and frequency, and NOTHING is silently approximated in the meantime.

    Three things are forbidden when the extractor hits a gap:
      - approximating into the nearest existing predicate
      - dropping the content
      - inventing a predicate ad hoc
    One thing is required: emit this.
    """

    proposal_id: str
    registry: RegistryKind
    proposed_id: str
    namespace: str = ""
    signature: dict[str, Any] = Field(default_factory=dict)

    evidence_passages: list[str] = Field(
        min_length=1, description="Passage IDs that motivated it."
    )
    occurrences: int = Field(
        default=1,
        description="Corpus frequency. Proposed once -> probably an extraction "
        "error. Proposed 47 times -> a real gap. Drives the review "
        "threshold so reviewers work on signal.",
    )
    nearest_existing: Optional[str] = Field(
        default=None, description="Closest current entry, if any."
    )
    why_insufficient: str = Field(
        description="Why the nearest existing entry cannot express this. "
        "Required - it is what a reviewer actually reads."
    )
    proposed_by: str
    status: Literal[
        "pending", "clustered", "approved", "rejected", "duplicate"
    ] = "pending"
    resolved_to: Optional[str] = None


REVIEW_THRESHOLD = 3
"""Occurrences before a proposal reaches a human. Below this it is usually an
extraction artefact; the passage is parked and re-run if the count rises."""


# ==========================================================================
# CLOSED CORE 3/3 - the frame
# ==========================================================================


class PredicateCall(BaseModel):
    """A node in the antecedent tree. The predicate is a REGISTRY LOOKUP, not
    an enum member - which is precisely why the grammar can grow without a
    schema change."""

    predicate: str = Field(
        description="Registry entry_id, e.g. 'occupies_bhava' or 'prashna.touches'."
    )
    args: dict[str, Any] = Field(default_factory=dict)
    negated: bool = False


class BoolExpr(BaseModel):
    op: Literal["all", "any", "not", "count", "compare", "leaf"]
    leaf: Optional[PredicateCall] = None
    operands: list["BoolExpr"] = Field(default_factory=list)
    count_op: Optional[Literal["gte", "lte", "eq"]] = None
    count_n: Optional[int] = None

    @model_validator(mode="after")
    def _shape(self) -> "BoolExpr":
        if self.op == "leaf":
            if self.leaf is None:
                raise ValueError("a leaf node requires `leaf`")
        elif self.leaf is not None:
            raise ValueError(f"`leaf` is only valid on op='leaf', not {self.op!r}")
        if self.op == "not" and len(self.operands) != 1:
            raise ValueError("`not` takes exactly one operand")
        if self.op in ("all", "any", "count", "compare") and not self.operands:
            raise ValueError(f"op={self.op!r} requires at least one operand")
        if self.op == "count" and (self.count_op is None or self.count_n is None):
            raise ValueError("`count` requires count_op and count_n")
        return self


BoolExpr.model_rebuild()


class Antecedent(BaseModel):
    expr: Optional[BoolExpr] = Field(
        default=None,
        description="None only for unconditional DEFINE_ATTRIBUTE / DIRECT_INTERPRETER.",
    )
    observables_required: list[str] = Field(
        default_factory=lambda: ["chart"],
        description="Registry IDs. ['chart'] for natal; ['breath','touch'] for "
        "Prasna; ['palm_image'] for Samudrika. Rules requiring an "
        "observable the product cannot capture are never served - "
        "and an LLM must never improvise the observation.",
    )


# ---- Consequents, one per assertion kind ----
#
# `kind` is a discriminator. The frame document leaves the union open, but an
# undiscriminated 7-way union resolves by trial and would silently coerce a
# malformed claim into some other shape. A wrong consequent type is exactly the
# error that must never pass quietly, so it is tagged.


class FactConsequent(BaseModel):
    """DERIVE_FACT: writes an atom back into the observed state."""

    kind: Literal["fact"] = "fact"
    fact_predicate: str
    subject_expr: str
    object_expr: Optional[str] = None
    value: str


class ClaimConsequent(BaseModel):
    """ASSERT_CLAIM: the only kind that reaches the user as a prediction."""

    kind: Literal["claim"] = "claim"
    claim_id: str = Field(description="Registry entry, e.g. 'wealth.accumulation'.")
    polarity: Literal["positive", "negative", "mixed", "neutral"]
    magnitude: Literal["slight", "moderate", "strong", "extreme"]
    literal_text: str = Field(description="As the source states it, untranslated in force.")

    # binding == TRANSFERRED
    transfer_source: Optional[str] = None
    transfer_target: Optional[str] = None
    transfer_cap: int = Field(
        default=8,
        description="Max significations to expand. Uncapped, one transfer rule "
        "over a 30-item signification table floods the evidence graph.",
    )

    # binding == QUANTIFIED
    quantity: Optional[float] = None
    quantity_max: Optional[float] = None
    unit: Optional[str] = None
    bound: Optional[
        Literal["exact", "minimum", "maximum", "range", "approximate"]
    ] = None


class AttributeConsequent(BaseModel):
    """DEFINE_ATTRIBUTE: single attributes, relation tables, AND signification
    sets. One shape covers all three because they differ only in arity."""

    kind: Literal["attribute"] = "attribute"
    entity_expr: str
    attribute: str
    values: list[str] = Field(min_length=1)
    relation_to: Optional[str] = Field(
        default=None, description="Set for binary relations (friendship matrices)."
    )
    ordered: bool = Field(
        default=False,
        description="True when list position carries weight - a signification "
        "enumeration's first items are primary.",
    )
    exhaustive: bool = False


class DirectiveConsequent(BaseModel):
    """DIRECT_SUBJECT: remedies and prohibitions."""

    kind: Literal["directive"] = "directive"
    injunction: Literal["prescription", "prohibition", "substitution"]
    acts_on: Literal["native", "relative", "object", "property"] = "native"
    acts_on_relation: Optional[str] = None
    action_text: str
    materials: list[str] = Field(default_factory=list)
    duration_days: Optional[int] = None
    weekday: Optional[str] = None
    presented_as: Literal["traditional_practice"] = "traditional_practice"


class ProcedureConsequent(BaseModel):
    """COMPUTE_VALUE: a spec for the chart engine, not executable Koonji."""

    kind: Literal["procedure"] = "procedure"
    computes: str
    method_note: str
    test_vectors: list[dict[str, Any]] = Field(default_factory=list)


class GuidanceConsequent(BaseModel):
    kind: Literal["guidance"] = "guidance"
    guidance_text: str
    applies_to: Literal["method", "precedence", "ethics", "procedure"]


class ExampleConsequent(BaseModel):
    """RECORD_APPLICATION: a chart plus an authority's reading. These are
    pre-labelled benchmark cases written by classical commentators - the
    closest thing to ground truth this domain has."""

    kind: Literal["example"] = "example"
    chart_data: dict[str, Any]
    subject_note: Optional[str] = None
    authority_reading: str
    cited_factors: list[str] = Field(default_factory=list)
    outcome_known: bool = False


Consequent = Annotated[
    Union[
        FactConsequent,
        ClaimConsequent,
        AttributeConsequent,
        DirectiveConsequent,
        ProcedureConsequent,
        GuidanceConsequent,
        ExampleConsequent,
    ],
    Field(discriminator="kind"),
]

#: Which consequent each assertion kind must carry. The pairing is not a
#: convention - a DERIVE_FACT rule carrying a ClaimConsequent produces no atom
#: and silently starves every rule downstream of it.
CONSEQUENT_FOR: dict[AssertionKind, type[BaseModel]] = {
    AssertionKind.DERIVE_FACT: FactConsequent,
    AssertionKind.COMPUTE_VALUE: ProcedureConsequent,
    AssertionKind.ASSERT_CLAIM: ClaimConsequent,
    AssertionKind.DEFINE_ATTRIBUTE: AttributeConsequent,
    AssertionKind.DIRECT_SUBJECT: DirectiveConsequent,
    AssertionKind.DIRECT_INTERPRETER: GuidanceConsequent,
    AssertionKind.RECORD_APPLICATION: ExampleConsequent,
}


class Qualifiers(BaseModel):
    modality: Modality = Modality.ASSERT
    binding: ConsequentBinding = ConsequentBinding.LITERAL
    restriction: Restriction = Restriction.OPEN
    corroboration: Corroboration = Corroboration.STANDALONE
    corroboration_n: Optional[int] = None
    targets_rule: Optional[str] = Field(
        default=None, description="Required for CANCEL / EXCEPT / STRENGTHEN / WEAKEN."
    )
    factor: Optional[float] = Field(
        default=None,
        description="Multiplier for STRENGTHEN / WEAKEN, e.g. 1.25 or 0.6.",
    )
    timing: list[dict[str, Any]] = Field(default_factory=list)
    requires_activation: bool = Field(
        default=False,
        description="A promise is not an event. When true the claim is held "
        "until a timing condition fires.",
    )
    confidence: dict[str, str] = Field(default_factory=dict)


class Dependencies(BaseModel):
    """DERIVE_FACT stratification. A rule may only read facts produced at a
    strictly lower tier. Composite friendship depends on temporal friendship
    depends on placement - get the order wrong and dignity is computed from
    stale facts."""

    tier: int = Field(default=0, ge=0, le=8)
    reads: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)


class Provenance(BaseModel):
    book_id: str
    edition_id: str
    locator: str
    quoted_text: str
    quote_sha256: str = ""
    authority_tier: str = "S0"
    restates: list[str] = Field(
        default_factory=list,
        description="Rules this restates. Drives the independence factor: three "
        "paraphrases of one verse are ONE piece of evidence.",
    )
    extraction: dict[str, Any] = Field(default_factory=dict)
    review: dict[str, Any] = Field(default_factory=dict)


class Rule(BaseModel):
    """The universal frame. Every rule in every tradition is an instance."""

    rule_id: str
    version: str = "1.0.0"
    frame_version: str = FRAME_VERSION
    registry_version: str

    school: str
    namespace: str = ""
    domains: dict[str, float] = Field(
        default_factory=dict,
        description="domain id -> weight. Drives the retrieval prefilter.",
    )
    status: Literal["draft", "candidate", "production", "retired"] = "draft"

    antecedent: Antecedent
    assertion: AssertionKind
    consequent: Consequent
    qualifiers: Qualifiers = Field(default_factory=Qualifiers)
    dependencies: Dependencies = Field(default_factory=Dependencies)
    provenance: Provenance

    @model_validator(mode="after")
    def _consequent_matches_assertion(self) -> "Rule":
        expected = CONSEQUENT_FOR[self.assertion]
        if not isinstance(self.consequent, expected):
            raise ValueError(
                f"{self.rule_id}: assertion {self.assertion.value!r} requires "
                f"{expected.__name__}, got {type(self.consequent).__name__}"
            )
        if self.assertion is AssertionKind.DERIVE_FACT:
            produced = self.consequent.fact_predicate
            if produced not in self.dependencies.produces:
                raise ValueError(
                    f"{self.rule_id}: derives {produced!r} but does not declare it "
                    f"in dependencies.produces - the stratifier cannot order it"
                )
        return self

    def content_hash(self) -> str:
        payload = self.model_dump(
            exclude={"rule_id", "version", "provenance", "frame_version", "registry_version"},
            exclude_none=True,
        )
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:24]


# ==========================================================================
# T-CODE PROJECTION - a derived view, not a schema field
#
# The T-codes remain useful for talking to astrologers and for corpus
# statistics. Nothing in the engine depends on them, so they can be renamed or
# reorganised without a data migration.
# ==========================================================================


def project_tcode(rule: Rule) -> str:
    a, q = rule.assertion, rule.qualifiers

    if a is AssertionKind.RECORD_APPLICATION:
        return "T22_worked_example"
    if a is AssertionKind.COMPUTE_VALUE:
        return "T2_computation"
    if a is AssertionKind.DIRECT_SUBJECT:
        return "T15_remedial"
    if a is AssertionKind.DIRECT_INTERPRETER:
        return "T16_guidance"
    if a is AssertionKind.DERIVE_FACT:
        return "T17_derivation"

    if a is AssertionKind.DEFINE_ATTRIBUTE:
        c = rule.consequent
        if isinstance(c, AttributeConsequent):
            if c.relation_to:
                return "T1b_relation_table"
            if len(c.values) > 5:
                return "T18_signification_set"
        return "T1_definition"

    # ASSERT_CLAIM - qualifiers first, then antecedent shape
    if q.modality is Modality.CANCEL:
        return "T10_cancellation"
    if q.modality is Modality.EXCEPT:
        return "T11_exception"
    if q.modality in (Modality.STRENGTHEN, Modality.WEAKEN):
        return "T9_modifier"
    if q.modality is Modality.ACTIVATE:
        return "T12_activation"
    if q.binding is ConsequentBinding.TRANSFERRED:
        return "T19_attribute_transfer"
    if q.binding is ConsequentBinding.QUANTIFIED:
        return "T21_quantified_outcome"
    if rule.antecedent.observables_required != ["chart"]:
        return "T20_observational"

    expr = rule.antecedent.expr
    if expr is None:
        return "T3_placement"
    if expr.op == "count":
        return "T7_threshold"
    if expr.op == "compare":
        return "T8_comparative"
    if expr.op == "any":
        return "T6_disjunctive"
    if expr.op == "all":
        return "T5_conjunctive"
    if expr.op == "leaf" and expr.leaf:
        subj = expr.leaf.args.get("subject", "")
        if isinstance(subj, str) and subj.startswith("lord."):
            return "T4_lordship"
        if isinstance(subj, dict) and subj.get("kind") == "lord_of":
            return "T4_lordship"
        return "T3_placement"
    return "T5_conjunctive"


# ==========================================================================
# VALIDATION - registry closure + derivation stratification
# ==========================================================================


def iter_leaves(expr: Optional[BoolExpr]):
    """Every PredicateCall in the tree, depth first, ignoring polarity."""
    if expr is None:
        return
    if expr.leaf is not None:
        yield expr.leaf
    for operand in expr.operands:
        yield from iter_leaves(operand)


def iter_leaves_signed(expr: Optional[BoolExpr], negated: bool = False):
    """Every PredicateCall with its effective polarity.

    `not: {combust: ...}` and `combust: {negated: true}` are two spellings of
    the same condition. Any pass that reasons about satisfiability has to see
    them as one, or a rule stating a thing and its opposite compiles cleanly and
    then never fires - which is invisible, because you cannot see the absence of
    a rule.
    """
    if expr is None:
        return
    if expr.leaf is not None:
        yield expr.leaf, negated != expr.leaf.negated
    flip = negated != (expr.op == "not")
    for operand in expr.operands:
        yield from iter_leaves_signed(operand, flip)


def validate_registry_closure(
    rule: Rule, registry: dict[RegistryKind, set[str]]
) -> list[str]:
    """Compiler pass: every symbol must resolve to a published registry entry.

    An unresolvable symbol is a HARD ERROR, never a warning - it means the
    extractor approximated instead of proposing, which is the one behaviour the
    protocol exists to prevent.
    """
    errors: list[str] = []
    preds = registry.get(RegistryKind.PREDICATE, set())
    claims = registry.get(RegistryKind.CLAIM, set())
    obs = registry.get(RegistryKind.OBSERVABLE, set())
    units = registry.get(RegistryKind.UNIT, set())

    for call in iter_leaves(rule.antecedent.expr):
        if call.predicate not in preds:
            errors.append(
                f"{rule.rule_id}: unregistered predicate {call.predicate!r} "
                f"- should have been an ExtensionProposal"
            )

    for o in rule.antecedent.observables_required:
        if o not in obs:
            errors.append(f"{rule.rule_id}: unregistered observable {o!r}")

    c = rule.consequent
    if isinstance(c, ClaimConsequent):
        if c.claim_id not in claims:
            errors.append(f"{rule.rule_id}: unregistered claim {c.claim_id!r}")
        if c.unit is not None and c.unit not in units:
            errors.append(f"{rule.rule_id}: unregistered unit {c.unit!r}")
    if isinstance(c, FactConsequent) and c.fact_predicate not in preds:
        errors.append(
            f"{rule.rule_id}: derives unregistered predicate {c.fact_predicate!r}"
        )

    entities = registry.get(RegistryKind.ENTITY, set())

    # Domains and school were not checked, and the gap is a silent one rather
    # than a loud one. A rule tagged `obstacle.general: 0.9` - a claim id in the
    # domain slot, which an extractor produces readily - compiles, indexes, and
    # is then unreachable by every domain filter forever. Nothing fires, nothing
    # errors, and the rule's absence from an answer is invisible.
    # The prefix check is unguarded: it needs no registry to know that a claim
    # id is not a domain, and it is the one that caught the real case.
    for domain in rule.domains:
        if not domain.startswith("domain."):
            errors.append(
                f"{rule.rule_id}: {domain!r} is not a domain - a rule tagged with "
                f"a non-domain is excluded by every domain filter and can never "
                f"be retrieved"
            )
        elif entities and domain not in entities:
            errors.append(f"{rule.rule_id}: unregistered domain {domain!r}")

    # Schools are namespaces, not entities. A typo here is silent in exactly
    # the same way a bad domain tag is: `school.parashri` is excluded by the
    # school filter forever and nothing says so.
    namespaces = registry.get(RegistryKind.NAMESPACE, set())
    if rule.school and namespaces and rule.school not in namespaces:
        errors.append(f"{rule.rule_id}: unregistered school {rule.school!r}")

    q = rule.qualifiers
    if q.modality in DEPENDENT_MODALITIES and not q.targets_rule:
        errors.append(
            f"{rule.rule_id}: modality {q.modality.value} requires targets_rule"
        )
    if q.modality in (Modality.STRENGTHEN, Modality.WEAKEN) and q.factor is None:
        errors.append(f"{rule.rule_id}: modality {q.modality.value} requires a factor")

    return errors


def validate_stratification(rules: list[Rule]) -> list[str]:
    """DERIVE_FACT rules must form an acyclic, tiered dependency graph."""
    errors: list[str] = []
    produced_at: dict[str, int] = {}

    for r in rules:
        if r.assertion is not AssertionKind.DERIVE_FACT:
            continue
        for f in r.dependencies.produces:
            if f in produced_at and produced_at[f] != r.dependencies.tier:
                errors.append(
                    f"{r.rule_id}: fact {f!r} produced at tiers "
                    f"{produced_at[f]} and {r.dependencies.tier}; a fact kind "
                    f"must have exactly one production tier"
                )
            produced_at[f] = r.dependencies.tier

    for r in rules:
        if r.assertion is not AssertionKind.DERIVE_FACT:
            continue
        for f in r.dependencies.reads:
            src = produced_at.get(f)
            if src is None:
                # Reading a base fact the chart compiler emits is fine; reading
                # a derived fact nobody produces is not. The compiler resolves
                # this against the base vocabulary, so only flag derived reads.
                continue
            if src >= r.dependencies.tier:
                errors.append(
                    f"{r.rule_id} (tier {r.dependencies.tier}) reads {f!r} "
                    f"produced at tier {src} - cycle or inversion"
                )
    return errors


def validate_targets(rules: list[Rule]) -> list[str]:
    """CANCEL/EXCEPT/STRENGTHEN/WEAKEN must point at a rule that exists.

    A cancellation clause aimed at a rule id that was renamed is dead code that
    looks like a working safety net, which is worse than no safety net.
    """
    known = {r.rule_id for r in rules}
    errors: list[str] = []
    for r in rules:
        target = r.qualifiers.targets_rule
        if target and target not in known:
            errors.append(
                f"{r.rule_id}: {r.qualifiers.modality.value} targets unknown rule "
                f"{target!r}"
            )
    return errors


# ==========================================================================
# COVERAGE MEASUREMENT - turns "is it universal?" into a metric
# ==========================================================================


class CoverageReport(BaseModel):
    source_id: str
    passages_sampled: int
    frame_fit_rate: float = Field(
        description="Share expressible in the 7 assertion kinds. "
        "MUST stay > 0.99 - a drop means the CLOSED core is wrong, "
        "which is a genuine architectural event."
    )
    registry_oov_rate: float = Field(
        description="Share needing a new registry entry. Expected to spike on a "
        "new tradition and decay. This is normal and informative."
    )
    novel_predicates: int
    novel_entities: int
    novel_observables: int
    approximation_rate: float = Field(
        description="Share where the extractor used nearest_existing instead of "
        "proposing. MUST be 0.0. Anything above zero means silent "
        "corpus corruption."
    )
    proposals: list[ExtensionProposal] = Field(default_factory=list)

    def verdict(self) -> str:
        if self.approximation_rate > 0:
            return "FAIL - extractor is approximating; corpus is being corrupted silently"
        if self.frame_fit_rate < 0.99:
            return "FRAME BREACH - the seven assertion kinds do not cover this tradition"
        if self.registry_oov_rate > 0.15:
            return "OK - large vocabulary gap; review the proposal batch before extracting"
        return "OK - frame and registry cover this source"


#: Run these BEFORE extracting 6,000 Jyotish rules. More Jyotish books will fit
#: comfortably and give false confidence; these are chosen to break the frame if
#: it is breakable. ~30 passages each.
FALSIFICATION_SUITE = [
    ("vettius_valens", "Hellenistic: sect, no dashas, different house logic"),
    ("bazi", "Four Pillars: no houses at all; elemental cycles; stem/branch"),
    ("ziwei_doushu", "100+ virtual stars, no real planets - stresses ENTITY registry"),
    (
        "iching",
        "No astronomy whatsoever; hexagram transformation - the real test of DERIVE_FACT",
    ),
    ("geomancy_ramal", "Random generation; figure arithmetic - observable registry"),
    ("samudrika", "Pure observation, no chart - observable registry"),
]
