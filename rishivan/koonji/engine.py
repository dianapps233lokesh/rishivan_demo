"""koonji.engine - the whole path, wired.

    question -> spec -> plan -> gates
                                  |
    chart -> facts -> derivations -> retrieve -> execute -> evidence -> citations

Six steps, none of which involves a language model. That is the design, not an
economy: retrieval has an exact answer, applicability has an exact answer, and
an approximation at either point produces a wrong reading that nothing
downstream can detect. What a model is genuinely good at - turning approved
claims into prose a person wants to read - happens after all of this, somewhere
else, from the `AnswerPlan` that a `Reading` becomes.

The order matters in one non-obvious place. Derivations run **before**
retrieval, not after. A derived fact - functional nature, composite friendship,
an Arudha - is what a predictive rule matches against, so retrieving first would
query an incomplete fact set and silently miss every rule that depends on the
derivation layer.

The stage above the line is the question layer (`question.py`, `router.py`). It
decides which slice of the corpus the read may reach, and - more often than is
comfortable - that there is nothing to read at all: a greeting, a drilldown into
a stored trace, a compatibility question with one chart. `read()` remains the
unfiltered primitive and answers whatever it is asked; `answer()` is the gated
path that runs the whole thing from raw text.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from rishivan.chart.ephemeris import Chart
from rishivan.koonji.bundle import Bundle
from rishivan.koonji.compiler import compile_path
from rishivan.koonji.evidence import Claim, EvidenceGraph, Support, build_evidence
from rishivan.koonji.facts import FactSet
from rishivan.koonji.question import (
    CLARIFY_BELOW,
    SERVABLE_MODES,
    Mode,
    QuestionSpec,
    TurnType,
)
from rishivan.koonji.registry import Registry, seed_registry
from rishivan.koonji.router import InputKind, RetrievalPlan, parse, retrieval_plan
from rishivan.koonji.urf import Rule
from rishivan.koonji.vm import Firing, Outcome, execute, run_derivations


def _english_list(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " or " + items[-1]

DEFAULT_RULES_DIR = Path(__file__).parent / "rules"

#: Only reviewed rules are served by default. Callers who want the seed corpus
#: have to say so, in as many words.
PRODUCTION_ONLY = frozenset({"production"})

_REFUSAL_TEXT: dict[str, str] = {
    "safety.distress": (
        "I'm not the right thing to talk to about this, and I don't want to "
        "give you a chart reading instead of an answer. Please reach someone "
        "who can help properly - a friend, a doctor, or a helpline."
    ),
    "safety.mortality": (
        "I won't put a date on a death, mine or anyone's. The classical texts "
        "do compute an ayurdaya and I can talk about what the longevity "
        "material says in general, but not as a prediction about you."
    ),
    "safety.medical": (
        "I can read what the texts say about the sixth house and health "
        "generally, but not about a diagnosis or a treatment. That needs a "
        "doctor, and an astrological answer here would be actively harmful."
    ),
}
"""Said plainly, once, without an apology tour. A refusal that hedges reads as
an invitation to rephrase, which is the opposite of what it is."""

_NON_ANALYTIC_TEXT: dict[TurnType, str] = {
    TurnType.SOCIAL: "",
    TurnType.META: "",
    # Answered from the stored trace of the turn being drilled into, not by
    # firing the corpus again. Recomputing could cite a different bundle than
    # the one that produced the claim the user is pointing at.
    TurnType.DRILLDOWN: "",
}
"""Empty on purpose. These turns have answers - a greeting gets a greeting, a
drilldown gets the stored trace - but none of those answers is the engine's to
write. The outcome tag tells the caller which one to produce; putting words
here would be this module inventing product copy it has no business owning.

The refusals above are different, and the asymmetry is deliberate: what to say
when declining is a safety decision, and safety decisions do not get delegated
to whatever layer happens to be calling."""

_UNSUPPORTED_TEXT: dict[Mode, str] = {
    Mode.COMPATIBILITY: (
        "Matching two charts needs a synastry corpus, and the rules loaded here "
        "are natal Parashari only. I'd rather say so than read one chart and "
        "call it a match."
    ),
    Mode.PRASHNA: (
        "A prashna reading is cast from the moment of the question and answered "
        "from the horary texts. Those aren't in this bundle."
    ),
    Mode.MUHURTA: (
        "Choosing an auspicious time is muhurta, a separate body of rules from "
        "the natal ones loaded here."
    ),
    Mode.KNOWLEDGE: (
        "That's a question about the texts rather than about a chart - it's "
        "answered from the corpus directly, not by firing rules."
    ),
    Mode.MODALITY: (
        "Numerology and palmistry are separate modalities. They never override "
        "a natal reading, and they aren't part of this engine."
    ),
    Mode.RECTIFICATION: (
        "Rectifying a birth time needs dated life events to test candidate "
        "times against. That's a different procedure from a reading."
    ),
}


@dataclass(slots=True)
class Reading:
    """One question's worth of deterministic output.

    Everything a narrative layer is allowed to say has to come from here, and
    every element of it carries the rule and the verse it came from.
    """

    bundle_id: str
    chart: Chart
    facts: FactSet
    firings: list[Firing]
    evidence: EvidenceGraph
    when: datetime
    elapsed_ms: float

    considered: int = 0
    """How many rules the index proposed. Retrieval is a superset by design, so
    this is always at least the number that fired."""

    derived_atoms: int = 0

    scoped: int = 0
    """How many rule variants the domain/school/status filter admitted, before
    the chart was consulted. Zero means the filter emptied the corpus; see
    `RuleIndex.scope_size`."""

    spec: Optional["QuestionSpec"] = None
    """The parsed question, when the reading came through `answer()`. None for a
    direct `read()`, which is the unfiltered primitive and has no question."""

    plan: Optional["RetrievalPlan"] = None

    rule_domains: dict[str, dict[str, float]] = field(default_factory=dict)
    """rule_id -> its domain tags, for every rule that was evaluated.

    Carried on the reading rather than looked up from the bundle, because
    `promises()` is asked about a domain and has to answer from what this
    reading actually considered. Reaching back into the bundle would answer
    from the whole corpus, and a domain nothing in this reading touched would
    read as promised."""

    widened: bool = False
    """True when the domain filter was dropped after producing no firings. Worth
    surfacing: it means the router and the corpus disagreed about what this
    question is, and that is a routing table to fix, not a one-off."""

    @property
    def claims(self) -> list[Claim]:
        return self.evidence.ranked()

    @property
    def insufficient(self) -> bool:
        return self.evidence.insufficient()

    def citations(self) -> list[str]:
        seen: list[str] = []
        for claim in self.claims:
            for citation in claim.citations():
                if citation not in seen:
                    seen.append(citation)
        return seen

    # -- the promise gate --------------------------------------------------

    def rule_domains_seen(self) -> list[str]:
        """Every domain any evaluated rule was tagged with."""
        seen: set[str] = set()
        for domains in self.rule_domains.values():
            seen.update(domains)
        return sorted(seen)

    def promises(self, domain: str) -> bool:
        """Does this chart carry a natal promise for this domain?

        The gate `timing/windows.py` runs on, and the reason that module can
        say "the chart does not indicate this" rather than manufacturing a
        date. A promise is three conditions at once - a rule that **fired**,
        whose claim sits **above the evidence floor**, and whose own tagging
        **includes this domain** - and dropping any one of them turns the dasha
        arithmetic back into a prediction generator.
        """
        return bool(self._promise_supports(domain))

    def promise_basis(self, domain: str) -> tuple[str, ...]:
        """The citations behind the promise, in confidence order.

        Goes into `EventWindow.promise_basis`, so a window can name the verse
        that entitled it to exist. A date with no basis is the thing this whole
        gate is built to prevent, and one with an unciteable basis is the same
        thing wearing a number.
        """
        seen: list[str] = []
        for support in self._promise_supports(domain):
            citation = support.citation
            if citation and citation not in seen:
                seen.append(citation)
        return tuple(seen)

    def _promise_supports(self, domain: str) -> list[Support]:
        from rishivan.koonji.evidence import INSUFFICIENT_BELOW

        found: dict[str, Support] = {}
        for claim in self.claims:
            if claim.confidence < INSUFFICIENT_BELOW:
                continue
            for support in claim.support:
                tags = self.rule_domains.get(support.rule_id)
                if tags and domain in tags:
                    found.setdefault(support.rule_id, support)
        return list(found.values())


@dataclass(slots=True)
class Response:
    """What `answer()` returns: a reading, or an honest account of why not.

    A single return type for both outcomes, rather than a reading plus
    exceptions. "I need their birth details", "that is not something I answer"
    and "the classical material is silent here" are all legitimate answers to a
    question, and modelling two of the three as errors pushes callers into
    treating them as bugs to be swallowed.
    """

    spec: QuestionSpec
    reading: Optional[Reading] = None
    plan: Optional[RetrievalPlan] = None

    outcome: str = "served"
    """served · needs_input · clarify · refused · not_analytic · unsupported ·
    no_coverage"""

    message: str = ""
    """Plain text for the user. Never a stack trace, never an error code."""

    @property
    def served(self) -> bool:
        return self.reading is not None

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome,
            "message": self.message,
            "turn_type": self.spec.turn_type.value,
            "mode": self.spec.mode.value,
            "routing": self.spec.routing.model_dump(),
            "flags": [f.flag_id for f in self.spec.flags],
            "parse_confidence": self.spec.parse_confidence,
            "plan": None if self.plan is None else {
                "domains": sorted(self.plan.domains) if self.plan.domains else None,
                "schools": sorted(self.plan.schools) if self.plan.schools else None,
                "statuses": sorted(self.plan.statuses),
                "min_domain_weight": self.plan.min_domain_weight,
                "notes": list(self.plan.notes),
            },
        }


class Engine:
    """Loads a bundle once and answers against it."""

    def __init__(self, bundle: Bundle) -> None:
        self.bundle = bundle
        self.registry = bundle.registry
        self._by_id = bundle.by_id()
        self._derivations = bundle.derivations()

    # -- construction ------------------------------------------------------

    @classmethod
    def from_rules(
        cls,
        path: Path | str = DEFAULT_RULES_DIR,
        registry: Optional[Registry] = None,
    ) -> "Engine":
        """Compile a rule directory and load the result.

        Fine for development and for the CLI. Production loads a prebuilt,
        content-addressed bundle instead, so that the artifact serving traffic is
        the exact one CI tested.
        """
        registry = registry or seed_registry()
        result = compile_path(path, registry).raise_for_errors()
        return cls(Bundle.build(result.rules, registry, result.index))

    @classmethod
    def from_bundle(
        cls, path: Path | str, registry: Optional[Registry] = None
    ) -> "Engine":
        return cls(Bundle.load(path, registry or seed_registry()))

    # -- the path ----------------------------------------------------------

    def read(
        self,
        chart: Chart,
        *,
        when: Optional[datetime] = None,
        domains: Optional[set[str]] = None,
        schools: Optional[set[str]] = None,
        statuses: frozenset[str] = PRODUCTION_ONLY,
        min_domain_weight: float = 0.0,
        vargas: Optional[Iterable[str]] = None,
        tier_weights: Optional[dict[str, float]] = None,
        min_independent: Optional[int] = None,
    ) -> Reading:
        """`vargas`, `tier_weights` and `min_independent` come from the
        question's `EvidenceHierarchy` (blueprint §12) and all default to None,
        which reproduces this method's behaviour before Phase 4 exactly.

        `vargas` matters more than it looks. The fact set is compiled once, so
        a division not named here can never be matched by any rule however the
        varga policy scoped it - selecting D9 for a marriage question and then
        compiling facts without it buys nothing at all.
        """
        started = time.perf_counter()
        when = when or datetime.now()

        # 1. The chart becomes a flat set of interned ground atoms.
        facts = self.bundle.index.facts_for(
            chart, when=when,
            **({"vargas": tuple(vargas)} if vargas is not None else {}),
        )
        base_atoms = len(facts.atoms)

        # 2. Derivations run in stratified tier order, writing new atoms back.
        #    Before retrieval, always: a rule that matches on a derived fact
        #    cannot be found in a fact set that does not have it yet.
        facts = run_derivations(self._derivations, facts, self.registry)

        # 3. Retrieval: exact set containment, a superset of what will fire.
        scoped = self.bundle.index.scope_size(
            domains=domains,
            schools=schools,
            statuses=statuses,
            min_domain_weight=min_domain_weight,
        )
        candidate_ids = self.bundle.index.query(
            facts,
            domains=domains,
            schools=schools,
            statuses=statuses,
            min_domain_weight=min_domain_weight,
        )
        candidate_ids -= self.bundle.denied

        # A cancellation has to be evaluated whenever its target is, even if the
        # cancelling condition is not itself in the candidate set. Otherwise a
        # yoga survives simply because nothing looked for the clause that breaks
        # it, which is the most damaging thing this engine could get wrong.
        for rule in self.bundle.rules:
            target = rule.qualifiers.targets_rule
            if target and target in candidate_ids and rule.rule_id not in self.bundle.denied:
                candidate_ids.add(rule.rule_id)

        candidates: list[Rule] = [
            self._by_id[rid] for rid in sorted(candidate_ids) if rid in self._by_id
        ]

        # 4. Exact evaluation, then modality settlement.
        firings = execute(candidates, facts, self.registry)

        # 5. Firings become claims, with restatements discounted.
        evidence = build_evidence(
            firings, candidates, lineage=self.bundle.lineage,
            tier_weights=tier_weights, min_independent=min_independent,
        )

        return Reading(
            bundle_id=self.bundle.manifest.bundle_id,
            chart=chart,
            facts=facts,
            firings=firings,
            evidence=evidence,
            when=when,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            considered=len(candidates),
            derived_atoms=len(facts.atoms) - base_atoms,
            scoped=scoped,
            rule_domains={r.rule_id: dict(r.domains) for r in candidates},
        )

    # -- the gated path ----------------------------------------------------

    def answer(
        self,
        question: str | QuestionSpec,
        chart: Optional[Chart] = None,
        *,
        when: Optional[datetime] = None,
        available: Optional[set[InputKind]] = None,
        statuses: frozenset[str] = PRODUCTION_ONLY,
        widen_if_empty: bool = True,
    ) -> Response:
        """Raw question -> spec -> plan -> gates -> reading.

        The gates run in a fixed order, and the order is the point. Each one is
        cheaper than the one after it, and each one can end the turn on its own:

          1. refusing flag   - distress, mortality. Costs one regex.
          2. not analytic    - greeting, meta, drilldown. No chart needed.
          3. unsupported     - the mode has no corpus behind it.
          4. missing input   - a required chart is absent. Ask, do not guess.
          5. low confidence  - the parse is a guess. Ask, do not guess.
          6. read            - and only now is an ephemeris touched.

        A chart is computed for exactly the turns that need one, which is fewer
        than it looks - roughly a third of live traffic never reaches step 6.
        """
        spec = (
            question
            if isinstance(question, QuestionSpec)
            else parse(question, now=when, available=available)
        )

        refused = spec.refused()
        if refused:
            return Response(
                spec=spec, outcome="refused",
                message=_REFUSAL_TEXT.get(refused, "This is not something I answer."),
            )

        if spec.turn_type in (TurnType.SOCIAL, TurnType.META, TurnType.DRILLDOWN):
            return Response(
                spec=spec, outcome="not_analytic",
                message=_NON_ANALYTIC_TEXT[spec.turn_type],
            )

        if spec.mode not in SERVABLE_MODES:
            return Response(
                spec=spec, outcome="unsupported",
                message=_UNSUPPORTED_TEXT.get(
                    spec.mode,
                    "I can't answer that from the material this engine holds.",
                ),
            )

        if spec.is_blocked():
            return Response(
                spec=spec, outcome="needs_input",
                message=" ".join(m.prompt for m in spec.missing_inputs if m.blocking),
            )

        if spec.parse_confidence < CLARIFY_BELOW:
            return Response(
                spec=spec, outcome="clarify",
                message="I want to make sure I answer the question you asked - "
                        "which part of your life is this about?",
            )

        if chart is None:
            # Reached only when the caller said the birth profile was available
            # and then did not pass the chart. That is a wiring bug, and a
            # cheerful "insufficient evidence" would hide it.
            raise ValueError(
                f"{spec.mode.value} needs a chart; `available` said the birth "
                f"profile was present but none was passed"
            )

        uncovered = self._uncovered(spec.routing.domains)
        if uncovered and len(uncovered) == len(spec.routing.domains):
            # Every domain this question routed to is absent from the bundle.
            # Not a routing miss and not a silent chart - a gap in the books we
            # hold. Widening here would answer the question with rules from
            # domains the user did not ask about, which reads as an answer and
            # is not one.
            return Response(
                spec=spec, outcome="no_coverage",
                message=(
                    "The books compiled into this bundle don't cover "
                    + _english_list([d.removeprefix("domain.") for d in uncovered])
                    + ". I'd rather say that than answer from material about "
                    "something else."
                ),
            )

        plan = retrieval_plan(spec, statuses=statuses, when=when)
        reading = self._read_plan(chart, plan, spec)

        if widen_if_empty and plan.widen_if_empty and reading.scoped == 0:
            # The domain filter emptied the corpus before a single rule was
            # evaluated. That is a routing question, not a result, so retry over
            # everything and record that we did.
            #
            # The test is `scoped == 0`, not "nothing fired" and not
            # "nothing was considered", and the difference is the whole point.
            # If the marriage rules were in scope and none of them matched this
            # chart, the classical material is silent on this marriage, and
            # saying so is the answer. Widening there would answer a marriage
            # question with whatever wealth rules happened to fire - exactly the
            # padding this engine exists in order not to do.
            plan = plan.unfiltered()
            reading = self._read_plan(chart, plan, spec, widened=True)

        return Response(spec=spec, reading=reading, plan=plan, outcome="served")

    def _uncovered(self, domains: list[str]) -> list[str]:
        coverage = self.bundle.index.domain_coverage()
        return [d for d in domains if not coverage.get(d)]

    def _read_plan(
        self,
        chart: Chart,
        plan: RetrievalPlan,
        spec: QuestionSpec,
        *,
        widened: bool = False,
        vargas: Optional[Iterable[str]] = None,
        tier_weights: Optional[dict[str, float]] = None,
        min_independent: Optional[int] = None,
    ) -> Reading:
        reading = self.read(
            chart,
            when=plan.when,
            domains=set(plan.domains) if plan.domains else None,
            schools=set(plan.schools) if plan.schools else None,
            statuses=plan.statuses,
            min_domain_weight=plan.min_domain_weight,
            vargas=vargas,
            tier_weights=tier_weights,
            min_independent=min_independent,
        )
        reading.spec = spec
        reading.plan = plan
        reading.widened = widened
        return reading

    # -- the trace ---------------------------------------------------------

    def trace(self, reading: Reading) -> dict:
        """The full audit chain for one reading.

        This is the artifact the whole architecture exists to be able to
        produce. Anyone can wire a model to an ephemeris in a month; nobody else
        can say which rules were considered, which fired, which were cancelled by
        what, which could not be decided and why, and which verse each of them
        came from.
        """
        rules = self._by_id
        return {
            "bundle_id": reading.bundle_id,
            "registry": self.registry.fingerprint(),
            "evaluated_at": reading.when.isoformat(),
            "elapsed_ms": round(reading.elapsed_ms, 2),
            "facts": {
                "atoms": len(reading.facts.atoms),
                "derived": reading.derived_atoms,
                "undecidable_predicates": sorted(reading.facts.undecidable),
                "observables": sorted(reading.facts.observables),
            },
            "retrieval": {
                "scoped": reading.scoped,
                "considered": reading.considered,
                "corpus": self.bundle.manifest.rule_count,
                "widened": reading.widened,
                "filter": None if reading.plan is None else {
                    "domains": sorted(reading.plan.domains) if reading.plan.domains else None,
                    "schools": sorted(reading.plan.schools) if reading.plan.schools else None,
                    "statuses": sorted(reading.plan.statuses),
                    "min_domain_weight": reading.plan.min_domain_weight,
                    "notes": list(reading.plan.notes),
                },
            },
            "question": None if reading.spec is None else {
                "raw": reading.spec.raw,
                "turn_type": reading.spec.turn_type.value,
                "mode": reading.spec.mode.value,
                "routing": reading.spec.routing.model_dump(),
                "flags": [f.flag_id for f in reading.spec.flags],
                "parse_confidence": reading.spec.parse_confidence,
            },
            "firings": [
                {
                    "rule": f.rule_id,
                    "version": f.version,
                    "outcome": f.outcome.value,
                    "strength": round(f.strength, 3),
                    "cancelled_by": f.cancelled_by,
                    "modifiers": f.modifiers,
                    "reason": f.reason,
                    "locator": (
                        f"{rules[f.rule_id].provenance.book_id} "
                        f"{rules[f.rule_id].provenance.locator}"
                    ).strip()
                    if f.rule_id in rules
                    else "",
                }
                for f in reading.firings
            ],
            "claims": [
                {
                    "claim": c.claim_id,
                    "confidence": c.confidence,
                    "band": c.band,
                    "phrasing": c.phrasing,
                    "independent_sources": c.independent_sources,
                    "corroboration_met": c.corroboration_met,
                    "requires_activation": c.requires_activation,
                    "support": [
                        {
                            "rule": s.rule_id,
                            "weight": round(s.effective_weight, 4),
                            "independent": s.independent,
                            "cluster": s.cluster,
                            "citation": s.citation,
                            "quote": s.quote,
                        }
                        for s in c.support
                    ],
                    "against": [
                        {
                            "rule": s.rule_id,
                            "weight": round(s.effective_weight, 4),
                            "citation": s.citation,
                            "quote": s.quote,
                        }
                        for s in c.against
                    ],
                }
                for c in reading.claims
            ],
            "insufficient_evidence": reading.insufficient,
        }
