# Phase 4 — Evidence Hierarchies and the Council

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every life domain its own evidence hierarchy, wire the Koonji
engine into the graph so a reading actually exists, and turn the eight Rishis
from prose voices into reasoning roles that return structured, disconfirmable
reports.

**Architecture:** One new module (`council/hierarchy.py`), one new package
(`council/rishis/`), a reordering of the deterministic prefix so the reading is
computed before the things that depend on it, and a `Send` fan-out with an
adversarial auditor and a bounded re-examination.

**Tech Stack:** existing `koonji/engine.py` (1,117 compiled rules, 12 domains
covered) · `koonji/evidence.py` · `koonji/router.py` · `chartstate/`
(Phase 2) · `varga/` + `timing/` (Phase 3) · LangGraph `Send`.

**Spec:** `docs/superpowers/specs/2026-08-25-chart-understanding-council-architecture.md` §8 (blueprint §12), §9 (blueprint §11)

## Global Constraints

- **The deterministic prefix stays deterministic.** Everything up to
  `fan_out_rishis` must be reproducible from
  `(chart_digest, bundle_id, registry_fingerprint, spec)`. No model call before
  the fan-out.
- **Every key a node returns must be declared in `RishivanState`.** LangGraph
  discards writes to undeclared channels silently — no error, no warning. That
  bug shipped once; `tests/graph/test_integration.py::test_every_node_return_key_is_declared_in_the_state`
  walks node returns against the annotations and will catch a repeat.
- **`store`, `config`, `writer`, `runtime` are LangGraph-injected parameter
  names.** A node parameter called `store` gets the framework's memory store,
  silently overriding whatever `functools.partial` bound. Name injected
  dependencies anything else.
- **Concurrent writers need a reducer.** Only `reports` has one
  (`Annotated[list, operator.add]`). Two fanned-out nodes writing any other key
  is a `InvalidUpdateError` at runtime.
- **`weakening` is required.** A `RishiReport` with supporting evidence and an
  empty `weakening` list is rejected unless `abstained` is set.
- **Every model node has a deterministic fallback.** A Rishi that times out or
  returns unparseable JSON returns `abstained="..."`; synthesis proceeds with
  fewer reports and says so.
- **Bounded loops only.** Re-examination runs at most once.
- Test runner: `./.venv/bin/python -m pytest`. The untracked root `tests.py`
  shadows the `tests/` package — move it aside for full-suite runs.

---

## What exists, measured

| Capability | State |
|---|---|
| Koonji engine, compiled | `Engine.from_rules()` → **1,117 rules** |
| Domain coverage in the bundle | all 12: wealth 261 · relationship 136 · temperament 124 · status 102 · health 99 · career 65 · progeny 61 · spiritual 45 · education 39 · longevity 33 · property 28 · travel 14 |
| Evidence graph, restatement clustering, noisy-OR | `koonji/evidence.py` |
| Question → `QuestionSpec` → `RetrievalPlan` | `koonji/router.py` |
| `ChartState` diagnosis | `chartstate/` (Phase 2) |
| Varga selection + withholding | `varga/select.py` (Phase 3) |
| Five-stage windows | `timing/windows.py` (Phase 3) |
| **Koonji reaching the graph** | **ABSENT — zero references.** `grep -rn koonji rishivan/graph` returns two reads of a key nobody writes |
| `state["reading"]` | declared, never written |
| `routing["koonji_domains"]` | read by `varga.py:30` and `timing.py:39`, **written by nothing** |
| `Reading.promises(domain)` | called by `timing.py:45`, **does not exist** |
| Per-domain evidence weighting | ABSENT — `_raw_weight` is one formula for every question |
| `RishiReport` | ABSENT — one prose generation, no structure |
| Cross-Rishi comparison, synthesis, audit | ABSENT |

## The three design problems this phase has to solve

**1. The reading does not exist.** This is the headline. `varga_select` reads a
routed Koonji domain that nothing sets, so it always falls back to
`domain.temperament`; `dasha_windows` reads a promise from a reading that is
always `None`, so it always returns a promise-less window. Both nodes are
correct and both are inert. Phase 4 is where they start working, and the way
they start working is a `koonji_read` node.

**2. The order is wrong, and circularly so.** Today:

```
chart_state → varga_select → dasha_windows → ground → council_routing → retrieve
```

But varga selection needs the routed domain, the fact set needs the selected
vargas, the reading needs the fact set, and the timing promise needs the
reading. The dependency chain is real and it is linear — it just is not the
order the graph runs in. Phase 4 straightens it:

```
chart_state → hierarchy → varga_select → koonji_read → dasha_windows
            → ground → council_routing → retrieve
            → fan_out_rishis ⇉ (rishi nodes) → sakshi → [re_examine] → synthesis → answer
```

`hierarchy` parses the question once, deterministically, and settles the domain
everything downstream keys off.

**3. Two routing taxonomies, and they must not become three.** `koonji/router.py`
routes to `domain.*` symbols (the rule corpus's vocabulary);
`council/domains.py` routes to the client's eight life-domain keys
(atma/prema/…), which is what `rishi_affinity` annotations and the coverage gate
are written against. Both are tested and neither is wrong. Phase 4 adds a
**bridge table** between them rather than a third vocabulary, and a test asserts
no `domain.*` symbol is orphaned.

---

### Task 1: The evidence hierarchy table

**Files:** Create `rishivan/council/hierarchy.py` · Test `tests/council/test_hierarchy.py`

**Interfaces:**
- Produces: `EvidenceHierarchy` (frozen dataclass), `HIERARCHIES: dict[str, EvidenceHierarchy]`, `hierarchy_for(domain: str) -> EvidenceHierarchy`, `DEFAULT_DOMAIN = "domain.temperament"`, `TIERS: tuple[str, ...]`

Keyed by **Koonji `domain.*` symbols**, because those are what `index.query`
filters on, what `varga/policy.py` scopes vargas by, and what
`timing/activation.py` maps to houses. Keying by the client's life-domain names
would need a translation at all three call sites.

- [ ] **Step 1: Write the failing test**

```python
# tests/council/test_hierarchy.py
import pytest

from rishivan.council.hierarchy import (
    DEFAULT_DOMAIN, HIERARCHIES, TIERS, EvidenceHierarchy, hierarchy_for,
)
from rishivan.koonji.router import DOMAIN_KEYWORDS


def test_every_routable_domain_has_a_hierarchy():
    """A domain the router can produce and the table cannot answer for falls
    back to temperament, which reads as an answer about the wrong subject."""
    assert set(DOMAIN_KEYWORDS) <= set(HIERARCHIES)


def test_marriage_carries_the_blueprint_row():
    h = hierarchy_for("domain.relationship")
    assert h.houses[0] == 7
    assert 7 in h.lords
    assert "graha.venus" in h.karakas and "graha.jupiter" in h.karakas
    assert "D9" in h.vargas
    assert "upapada" in h.jaimini and "darakaraka" in h.jaimini


def test_career_names_d10_and_the_tenth():
    h = hierarchy_for("domain.career")
    assert h.houses[0] == 10
    assert "D10" in h.vargas
    assert "amatyakaraka" in h.jaimini


def test_tier_weights_are_declared_for_every_tier():
    for domain, h in HIERARCHIES.items():
        assert set(h.tier_weights) == set(TIERS), domain


def test_a_house_placement_always_outranks_a_varga_confirmation():
    """The blueprint's whole complaint about one generic formula."""
    for domain, h in HIERARCHIES.items():
        assert h.tier_weights["house"] > h.tier_weights["varga"], domain


def test_the_vargas_named_are_vargas_the_policy_registry_knows():
    from rishivan.varga.policy import POLICIES
    for domain, h in HIERARCHIES.items():
        assert set(h.vargas) <= set(POLICIES), domain


def test_an_unknown_domain_falls_back_rather_than_raising():
    assert hierarchy_for("domain.nonexistent") is HIERARCHIES[DEFAULT_DOMAIN]


def test_longevity_demands_more_corroboration_than_temperament():
    """A mortality claim on one verse is the single most damaging thing this
    system could emit."""
    assert (hierarchy_for("domain.longevity").min_independent_sources
            > hierarchy_for("domain.temperament").min_independent_sources)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `./.venv/bin/python -m pytest tests/council/test_hierarchy.py -q`
Expected: `ModuleNotFoundError: No module named 'rishivan.council.hierarchy'`

- [ ] **Step 3: Write the table**

```python
# rishivan/council/hierarchy.py
"""Blueprint §12: one evidence hierarchy per life domain.

The blueprint's complaint, verbatim: *"the same chart should not be analysed
with one generic scoring formula for every life question."* That is exactly
what happens today - `evidence._raw_weight` is magnitude x authority x strength
whatever was asked, so a D9 confirmation of a marriage reading counts the same
as the 7th-lord placement it is confirming, and a transit counts the same as
both.

This table is the fix, and it is declarative on purpose (spec C4). Three things
come out of one lookup:

    hierarchy.koonji_domains  -> the `domains` filter `index.query` already takes
    hierarchy.vargas          -> the divisions `varga_select` may reach for
    hierarchy.tier_weights    -> handed to `build_evidence`, so a D1 house
                                 placement outranks a D9 confirmation

**Keyed by Koonji `domain.*` symbols.** Those are what the rule corpus is
tagged with, what the varga policies scope by, and what the activation mapping
translates to houses. The client's eight life-domain keys (atma/prema/...) are
a different and equally real taxonomy; `LIFE_DOMAIN_OF` below bridges them
rather than replacing either.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TIERS: tuple[str, ...] = ("house", "varga", "dasha", "transit", "jaimini")
"""The kinds of evidence a firing can rest on, ordered by how directly they
bear on a D1 reading.

`transit` is declared and unreachable today: no registry predicate expresses a
transit, so no rule can fire on one. Declaring it now means the day a transit
predicate lands, the weight already exists and nothing has to be re-tiered.
"""

DEFAULT_DOMAIN = "domain.temperament"


@dataclass(frozen=True, slots=True)
class EvidenceHierarchy:
    domain: str
    houses: tuple[int, ...]
    """In priority order. The first is the bhava the question is *about*."""

    lords: tuple[int, ...]
    karakas: tuple[str, ...]
    vargas: tuple[str, ...]
    jaimini: tuple[str, ...]
    requires_dasha: bool
    """Whether a claim in this domain is about an *event*, and so needs a
    period before it may be dated. Temperament does not; marriage does."""

    requires_transit: bool
    min_independent_sources: int
    """The floor. `evidence.build_evidence` enforces it per claim, which is
    where the corroboration machinery already lives (spec open decision 3)."""

    tier_weights: dict[str, float] = field(default_factory=dict)


def _weights(**overrides: float) -> dict[str, float]:
    """Defaults, plus whatever this domain stresses.

    Written as a function rather than repeated per row: the invariant that
    matters (house outranks varga) is then true by construction for every row
    that does not deliberately override it, and the test that asserts it is
    checking the overrides rather than fifteen copies of the same dict.
    """
    base = {"house": 1.0, "varga": 0.55, "dasha": 0.45, "transit": 0.30,
            "jaimini": 0.50}
    base.update(overrides)
    return base


_ROWS: tuple[tuple, ...] = (
    # domain, houses, lords, karakas, vargas, jaimini,
    #   dasha?, transit?, min_sources, weight overrides
    ("domain.relationship", (7, 2, 8, 11), (7, 2),
     ("graha.venus", "graha.jupiter"), ("D9",), ("upapada", "darakaraka"),
     True, True, 2, {"varga": 0.75}),
    ("domain.career", (10, 6, 7, 11, 1), (10, 6),
     ("graha.sun", "graha.saturn", "graha.mercury"), ("D10",),
     ("amatyakaraka",), True, True, 2, {"varga": 0.75}),
    ("domain.wealth", (2, 11, 5, 9), (2, 11),
     ("graha.jupiter", "graha.venus"), ("D2",), (),
     True, False, 2, {}),
    ("domain.property", (4, 12), (4,),
     ("graha.mars", "graha.venus"), ("D4", "D16"), (),
     True, False, 1, {}),
    ("domain.education", (4, 5, 9, 2), (4, 5),
     ("graha.mercury", "graha.jupiter"), ("D24",), (),
     False, False, 1, {}),
    ("domain.progeny", (5, 9, 11), (5,),
     ("graha.jupiter",), ("D7",), ("putrakaraka",),
     True, False, 2, {"varga": 0.70}),
    ("domain.travel", (12, 9, 4, 3), (12, 9),
     ("graha.rahu", "graha.ketu"), ("D4",), (),
     True, False, 1, {}),
    ("domain.spiritual", (9, 12, 5), (9, 12),
     ("graha.jupiter", "graha.ketu"), ("D20",), ("atmakaraka",),
     False, False, 1, {"jaimini": 0.65}),
    ("domain.health", (1, 6, 8, 12), (1, 6),
     ("graha.sun", "graha.moon", "graha.saturn"), ("D30",), (),
     True, True, 2, {}),
    # Longevity is the one row where the corroboration floor is a safety
    # decision rather than a doctrinal one. Three independent sources, and the
    # answer layer still hedges - see REFUSING_FLAGS in koonji/question.py,
    # which stops most of these questions before they get here at all.
    ("domain.longevity", (8, 1, 3, 10), (8, 1),
     ("graha.saturn",), (), (), True, True, 3, {}),
    ("domain.status", (10, 1, 9, 11), (10, 9),
     ("graha.sun", "graha.jupiter"), ("D3", "D12"), (),
     True, False, 2, {}),
    ("domain.temperament", (1, 5, 9), (1,),
     ("graha.sun", "graha.moon"), ("D60",), ("atmakaraka",),
     False, False, 1, {}),
)

HIERARCHIES: dict[str, EvidenceHierarchy] = {
    row[0]: EvidenceHierarchy(
        domain=row[0], houses=row[1], lords=row[2], karakas=row[3],
        vargas=row[4], jaimini=row[5], requires_dasha=row[6],
        requires_transit=row[7], min_independent_sources=row[8],
        tier_weights=_weights(**row[9]),
    )
    for row in _ROWS
}


def hierarchy_for(domain: str) -> EvidenceHierarchy:
    """Falls back rather than raising.

    Deliberately unlike `varga.policy.policy_for`, which raises. That one
    guards a *computable* division nobody scoped - a real gap. This one is
    reached with whatever the router produced, and a router that grows a
    thirteenth domain should degrade to a broad reading rather than 500.
    """
    return HIERARCHIES.get(domain, HIERARCHIES[DEFAULT_DOMAIN])
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/council/test_hierarchy.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/hierarchy.py tests/council/test_hierarchy.py
git commit -m "feat(council): one evidence hierarchy per life domain"
```

---

### Task 2: The taxonomy bridge

**Files:** Modify `rishivan/council/hierarchy.py` · Test `tests/council/test_hierarchy.py`

**Interfaces:**
- Consumes: `HIERARCHIES` (Task 1), `council.domains.LIFE_DOMAIN_KEYS`
- Produces: `LIFE_DOMAIN_OF: dict[str, tuple[str, ...]]`, `koonji_domains_for_rishi(rishi: str) -> frozenset[str]`

Without this, deciding which persona may speak for `domain.progeny` needs a
third hand-written table. With it, the existing weighted `RISHI_LIFE_DOMAINS` —
already tested for no orphan domains — answers the question.

- [ ] **Step 1: Write the failing test**

```python
def test_no_koonji_domain_is_orphaned_from_the_client_taxonomy():
    from rishivan.council.domains import LIFE_DOMAIN_KEYS
    from rishivan.council.hierarchy import LIFE_DOMAIN_OF
    assert set(LIFE_DOMAIN_OF) == set(HIERARCHIES)
    for domain, keys in LIFE_DOMAIN_OF.items():
        assert keys, domain
        assert set(keys) <= set(LIFE_DOMAIN_KEYS), domain


def test_the_marriage_rishi_can_reach_marriage_rules():
    from rishivan.council.hierarchy import koonji_domains_for_rishi
    assert "domain.relationship" in koonji_domains_for_rishi("medhan")


def test_the_wealth_rishi_can_reach_wealth_and_career():
    from rishivan.council.hierarchy import koonji_domains_for_rishi
    reach = koonji_domains_for_rishi("dhruvan")
    assert {"domain.wealth", "domain.career"} <= reach


def test_a_service_rishi_reaches_everything():
    """vyom is the fallback voice and rates every life domain MEDIUM. A
    fallback that reaches nothing is not a fallback."""
    from rishivan.council.hierarchy import koonji_domains_for_rishi
    assert koonji_domains_for_rishi("vyom") == frozenset(HIERARCHIES)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `./.venv/bin/python -m pytest tests/council/test_hierarchy.py -q -k orphan`
Expected: `ImportError: cannot import name 'LIFE_DOMAIN_OF'`

- [ ] **Step 3: Add the bridge**

```python
# appended to rishivan/council/hierarchy.py

LIFE_DOMAIN_OF: dict[str, tuple[str, ...]] = {
    "domain.temperament":  ("atma",),
    "domain.spiritual":    ("dharma", "atma"),
    "domain.wealth":       ("artha",),
    "domain.career":       ("karma",),
    "domain.status":       ("karma", "vansh"),
    "domain.property":     ("artha", "yatra"),
    "domain.travel":       ("yatra",),
    "domain.relationship": ("prema",),
    "domain.progeny":      ("vansh",),
    "domain.education":    ("vansh", "karma"),
    "domain.health":       ("aarogya",),
    "domain.longevity":    ("aarogya",),
}
"""Koonji rule domain -> the client's life-domain Rishi keys.

Two of these are judgement calls and are marked as such rather than left to
look self-evident:

  * **education -> vansh, karma.** ER §8 gives VANSH houses 2/3/4/5/9, which is
    where education actually sits; KARMA is second because a degree is usually
    asked about in service of a career.
  * **status -> karma, vansh.** Reputation and rank are the 10th, which is
    KARMA. The father sense of `domain.status` is VANSH's 9th, hence the
    second key.

Every value is non-empty, and a test asserts it. An orphaned domain means a
question routes to a rule set no persona is allowed to read, and the symptom is
an empty answer nobody can trace.
"""


def koonji_domains_for_rishi(rishi: str) -> frozenset[str]:
    """Which rule domains this persona may argue from.

    Derived from `RISHI_LIFE_DOMAINS` rather than hand-written, so the weighted
    table that is already tested for no-orphan coverage stays the single source
    of truth. A persona rating a life domain at any weight above zero may reach
    the Koonji domains that map onto it.
    """
    from rishivan.council.domains import RISHI_LIFE_DOMAINS

    weights = RISHI_LIFE_DOMAINS.get(rishi.lower(), {})
    return frozenset(
        domain for domain, keys in LIFE_DOMAIN_OF.items()
        if any(weights.get(k, 0.0) > 0.0 for k in keys)
    )
```

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/council/test_hierarchy.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rishivan/council/hierarchy.py tests/council/test_hierarchy.py
git commit -m "feat(council): bridge Koonji rule domains to the client life-domain keys"
```

---

### Task 3: Tier-weighted evidence

**Files:** Modify `rishivan/koonji/evidence.py` · Test `tests/koonji/test_evidence_tiers.py`

**Interfaces:**
- Consumes: `TIERS` (Task 1)
- Produces: `tier_of(rule: Rule) -> str`, `build_evidence(..., tier_weights=None, min_independent=None)`

This is the load-bearing half of §12. The table from Task 1 is inert until a
firing's weight depends on it.

**Tier classification comes from the rule's own predicates**, since that is the
only place the information exists:

| predicate in the antecedent | tier |
|---|---|
| `varga_occupies`, `varga_dignity` | `varga` |
| `dasha_active` | `dasha` |
| `chara_karaka`, `rashi_aspects` | `jaimini` |
| anything else | `house` |

A rule spanning tiers takes the **weakest** one it touches: a claim resting
partly on a D9 placement is a D9-grade claim however many D1 conditions
accompany it.

- [ ] **Step 1: Write the failing test**

```python
# tests/koonji/test_evidence_tiers.py
import pytest

from rishivan.koonji.compiler import compile_text
from rishivan.koonji.evidence import build_evidence, tier_of
from rishivan.koonji.registry import seed_registry
from rishivan.koonji.vm import Firing, Outcome


def _rule(yaml_text):
    registry = seed_registry()
    return compile_text(yaml_text, registry).raise_for_errors().rules[0]


def test_a_plain_placement_rule_is_a_house_rule(house_rule):
    assert tier_of(house_rule) == "house"


def test_a_rule_naming_a_varga_is_a_varga_rule(varga_rule):
    assert tier_of(varga_rule) == "varga"


def test_a_rule_spanning_tiers_takes_the_weakest(mixed_rule):
    """A D1 condition does not upgrade a claim that also rests on a D9 one."""
    assert tier_of(mixed_rule) == "varga"


def test_tier_weights_lower_the_confidence_of_a_varga_claim(varga_rule):
    firing = Firing(rule_id=varga_rule.rule_id, version=varga_rule.version,
                    outcome=Outcome.FIRED, claim_id="c1")
    unweighted = build_evidence([firing], [varga_rule])
    weighted = build_evidence([firing], [varga_rule],
                              tier_weights={"varga": 0.5})
    assert weighted.claims[0].confidence < unweighted.claims[0].confidence


def test_an_absent_tier_weight_means_unchanged(house_rule):
    firing = Firing(rule_id=house_rule.rule_id, version=house_rule.version,
                    outcome=Outcome.FIRED, claim_id="c1")
    a = build_evidence([firing], [house_rule])
    b = build_evidence([firing], [house_rule], tier_weights={"varga": 0.1})
    assert a.claims[0].confidence == b.claims[0].confidence


def test_min_independent_raises_the_corroboration_floor(house_rule):
    firing = Firing(rule_id=house_rule.rule_id, version=house_rule.version,
                    outcome=Outcome.FIRED, claim_id="c1")
    graph = build_evidence([firing], [house_rule], min_independent=2)
    claim = graph.claims[0]
    assert claim.corroboration_required == 2
    assert not claim.corroboration_met


def test_min_independent_never_lowers_a_rules_own_requirement(corroborated_rule):
    """A rule that says it needs three sources still needs three."""
    firing = Firing(rule_id=corroborated_rule.rule_id,
                    version=corroborated_rule.version,
                    outcome=Outcome.FIRED, claim_id="c1")
    graph = build_evidence([firing], [corroborated_rule], min_independent=1)
    assert graph.claims[0].corroboration_required == 3


def test_the_support_edge_records_its_tier(varga_rule):
    firing = Firing(rule_id=varga_rule.rule_id, version=varga_rule.version,
                    outcome=Outcome.FIRED, claim_id="c1")
    graph = build_evidence([firing], [varga_rule])
    assert graph.claims[0].support[0].tier == "varga"
```

Fixtures build the four rules from real YAML through the real compiler — the
same discipline `tests/koonji/test_prompts.py` uses, so a rule dialect drift
fails here rather than in production. Put them in
`tests/koonji/conftest.py` alongside the existing fixtures.

- [ ] **Step 2: Run it and watch it fail**

Run: `./.venv/bin/python -m pytest tests/koonji/test_evidence_tiers.py -q`
Expected: `ImportError: cannot import name 'tier_of'`

- [ ] **Step 3: Implement**

```python
# rishivan/koonji/evidence.py — additions

TIER_PREDICATES: dict[str, str] = {
    "varga_occupies": "varga",
    "varga_dignity": "varga",
    "dasha_active": "dasha",
    "chara_karaka": "jaimini",
    "rashi_aspects": "jaimini",
}
"""Predicate -> evidence tier. Anything unlisted is a D1 statement about houses
and grahas, which is the overwhelming majority and the right default."""

_TIER_ORDER = ("house", "jaimini", "dasha", "varga", "transit")
"""Weakest last. `tier_of` returns the weakest tier a rule touches, so a claim
resting partly on a D9 placement is graded as a D9 claim however many D1
conditions sit beside it."""


def tier_of(rule: Rule) -> str:
    """Which kind of evidence this rule is.

    Read off the antecedent's predicates rather than stored on the rule,
    because the rule dialect has no tier field and adding one would require
    re-extracting 1,117 rules to set something derivable.
    """
    found = {"house"}
    for call in _predicate_calls(rule.antecedent):
        tier = TIER_PREDICATES.get(call.predicate)
        if tier:
            found.add(tier)
    return max(found, key=_TIER_ORDER.index)
```

`_predicate_calls` is a small recursive walk over `BoolExpr` yielding every
`PredicateCall`; `koonji/index.py:extract_core` already has the shape to copy —
copy the walk, not the interning.

Then in `build_evidence`, extend the signature and thread the weight through:

```python
def build_evidence(
    firings, rules, *, lineage=None, for_claims=None,
    tier_weights: Optional[dict[str, float]] = None,
    min_independent: Optional[int] = None,
) -> EvidenceGraph:
```

At the point each `Support` is constructed, multiply and record:

```python
        tier = tier_of(rule)
        raw = _raw_weight(rule, firing) * (tier_weights or {}).get(tier, 1.0)
```

and add `tier: str = "house"` to `Support`. Where `corroboration_required` is
settled, take the stricter of the rule's own requirement and the hierarchy's
floor:

```python
        required = max(
            [n for n in corroboration[claim_id] if n] + [min_independent or 1]
        )
```

**Note in the docstring** why the tier multiplier lives here and the *domain*
weights deliberately do not — the existing `_raw_weight` docstring already
argues that domain weight is relevance, not support, and that argument still
holds. Tier is a statement about how directly the evidence bears, which is
support.

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/koonji/ -q`
Expected: PASS, including the 519 existing Koonji tests — the new parameters
default to `None` and must change nothing when unset.

- [ ] **Step 5: Commit**

```bash
git add rishivan/koonji/evidence.py tests/koonji/test_evidence_tiers.py tests/koonji/conftest.py
git commit -m "feat(koonji): weight a firing by the kind of evidence it rests on"
```

---

### Task 4: `Reading.promises` and yoga extraction

**Files:** Modify `rishivan/koonji/engine.py` · Test `tests/koonji/test_reading_promises.py`

**Interfaces:**
- Produces: `Reading.promises(domain: str) -> bool`, `Reading.promise_basis(domain: str) -> tuple[str, ...]`, `Reading.yogas() -> dict[str, tuple[str, ...]]`

`timing/windows.py` already calls `reading.promises(domain)` behind a
`bool(reading and ...)` guard. The guard has been holding back an
`AttributeError` since Phase 3, because `reading` was always `None`. Wire the
reading in without this method and the first chart question raises.

- [ ] **Step 1: Write the failing test**

```python
# tests/koonji/test_reading_promises.py
def test_a_reading_with_a_confident_claim_promises_its_domain(reading):
    assert reading.promises("domain.wealth") is True


def test_a_domain_with_no_claims_is_not_promised(reading):
    assert reading.promises("domain.longevity") is False


def test_a_claim_below_the_evidence_floor_is_not_a_promise(thin_reading):
    """`INSUFFICIENT_BELOW` is the line. A 0.2-confidence claim is not a
    promise the timing engine may date."""
    assert thin_reading.promises("domain.wealth") is False


def test_the_promise_basis_cites_the_rules_that_made_it(reading):
    basis = reading.promise_basis("domain.wealth")
    assert basis
    assert all(isinstance(c, str) and c for c in basis)


def test_promises_is_false_for_a_domain_nobody_routed(reading):
    assert reading.promises("domain.nonexistent") is False


def test_yogas_are_grouped_by_the_graha_they_bind(reading):
    yogas = reading.yogas()
    assert all(isinstance(v, tuple) for v in yogas.values())
```

- [ ] **Step 2: Run it and watch it fail**

Run: `./.venv/bin/python -m pytest tests/koonji/test_reading_promises.py -q`
Expected: `AttributeError: 'Reading' object has no attribute 'promises'`

- [ ] **Step 3: Implement on `Reading`**

```python
    def promises(self, domain: str) -> bool:
        """Does the chart carry a natal promise for this domain?

        The gate `timing/windows.py` runs on, and the reason that module can
        say "the chart does not indicate this" instead of manufacturing a date.
        A promise here is a *fired rule above the evidence floor whose own
        domain tagging includes this domain* - three conditions, and dropping
        any one of them turns the dasha arithmetic back into a prediction
        generator.
        """
        return bool(self._promise_supports(domain))

    def promise_basis(self, domain: str) -> tuple[str, ...]:
        """The citations behind the promise, for `EventWindow.promise_basis`."""
        seen: list[str] = []
        for support in self._promise_supports(domain):
            if support.citation and support.citation not in seen:
                seen.append(support.citation)
        return tuple(seen)

    def _promise_supports(self, domain: str) -> list[Support]:
        by_id = {}
        for claim in self.claims:
            if claim.confidence < INSUFFICIENT_BELOW:
                continue
            for support in claim.support:
                rule = self._rule_domains.get(support.rule_id)
                if rule and domain in rule:
                    by_id[support.rule_id] = support
        return list(by_id.values())
```

`_rule_domains` is a `dict[str, dict[str, float]]` the `Engine` populates when
it builds the `Reading` — from `rule.qualifiers`/annotations, the same source
`Variant.domains` is built from in `index.py`. Do **not** re-parse the rules
here; pass the mapping in.

`yogas()` groups fired `ASSERT_CLAIM` rules whose consequent names a yoga by
the graha bound in the firing, so Task 7 can fill `PlanetDiagnosis.yogas`.

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/koonji/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rishivan/koonji/engine.py tests/koonji/test_reading_promises.py
git commit -m "feat(koonji): a reading can say whether the chart promises a domain"
```

---

### Task 5: The `hierarchy` node and the reordering

**Files:** Create `rishivan/graph/nodes/hierarchy.py` · Modify `rishivan/graph/state.py`, `rishivan/graph/build.py`, `rishivan/graph/nodes/varga.py`, `rishivan/graph/nodes/timing.py` · Test `tests/graph/test_nodes_hierarchy.py`, `tests/graph/test_build.py`

**Interfaces:**
- Consumes: `hierarchy_for` (Task 1), `koonji.router.parse`, `koonji.router.retrieval_plan`
- Produces: node `hierarchy_node(state) -> dict` writing `spec`, `hierarchy`, `koonji_domain`, `retrieval_plan`

This is where the dependency chain gets straightened. Declare the new state
keys **first** — an undeclared key here is discarded silently and every
downstream node reads a default.

- [ ] **Step 1: Write the failing test**

```python
# tests/graph/test_nodes_hierarchy.py
def test_a_marriage_question_routes_to_the_relationship_hierarchy():
    out = hierarchy_node(_state("when will I get married?"))
    assert out["koonji_domain"] == "domain.relationship"
    assert out["hierarchy"].houses[0] == 7


def test_an_unroutable_question_falls_back_to_temperament():
    out = hierarchy_node(_state("tell me about myself"))
    assert out["koonji_domain"] == "domain.temperament"


def test_the_node_is_deterministic():
    q = "will my business grow next year?"
    a, b = hierarchy_node(_state(q)), hierarchy_node(_state(q))
    assert a["koonji_domain"] == b["koonji_domain"]


def test_the_node_makes_no_model_call():
    """The deterministic prefix stays deterministic. The signature has no
    client parameter, which is the strongest way to say so."""
    import inspect
    assert "client" not in inspect.signature(hierarchy_node).parameters


# tests/graph/test_build.py — additions
def test_varga_selection_runs_after_the_hierarchy_that_names_its_domain():
    assert STATIC_EDGES["hierarchy"] == "varga_select"


def test_the_reading_is_computed_before_the_timing_that_needs_its_promise():
    assert STATIC_EDGES["varga_select"] == "koonji_read"
    assert STATIC_EDGES["koonji_read"] == "dasha_windows"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `./.venv/bin/python -m pytest tests/graph/test_nodes_hierarchy.py -q`
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Declare the state keys**

```python
    # -- §12 hierarchies and the reading (Phase 4) -------------------------
    spec: Any
    """The parsed `QuestionSpec`. Deterministic, from `koonji.router.parse`."""

    hierarchy: Any
    koonji_domain: str
    retrieval_plan: Any
    reading: Any
    contributor_reports: tuple
```

`hierarchy` and `reading` are already declared as Phase 4-5 placeholders —
keep them, add the rest. Extend `initial_state` with defaults for each
(`spec=None`, `koonji_domain=""`, `retrieval_plan=None`), because
`test_state.py::test_every_result_key_has_a_default` walks them.

- [ ] **Step 4: Write the node**

```python
# rishivan/graph/nodes/hierarchy.py
"""Blueprint §12: settle what kind of question this is, once, deterministically.

Everything downstream keys off this node's `koonji_domain`: which vargas may
speak, which rules the index admits, how a firing is weighted, and which Rishis
are invited. Running it once and writing the answer to state is what stops four
nodes each guessing separately and disagreeing.

**Before the fan-out, so no model is involved.** The domain comes from
`koonji/router.py`'s keyword table, which is a table a reviewer can read and
correct. A classifier call here would be one more thing to be non-reproducible
about, and the classifier already ran at intake for a different purpose.
"""


def hierarchy_node(state: RishivanState) -> dict:
    from rishivan.council.hierarchy import DEFAULT_DOMAIN, hierarchy_for
    from rishivan.koonji.router import parse, retrieval_plan

    when = state.get("query_time")
    spec = parse(state["question"], now=when)
    domains = spec.routing.domains
    domain = domains[0] if domains else DEFAULT_DOMAIN
    return {
        "spec": spec,
        "koonji_domain": domain,
        "hierarchy": hierarchy_for(domain),
        "retrieval_plan": retrieval_plan(spec, when=when),
    }
```

- [ ] **Step 5: Rewire `varga.py` and `timing.py`**

Both currently read `routing.get("koonji_domains")`, which nothing writes.
Replace with `state.get("koonji_domain") or DEFAULT_DOMAIN` in each, and delete
the dead lookup. `timing.py` additionally passes the hierarchy's
`requires_dasha` through so a temperament question does not get a window it
never asked for.

- [ ] **Step 6: Rewire the edges**

```python
STATIC_EDGES: dict[str, str] = {
    ...
    "chart_state": "hierarchy",
    "hierarchy": "varga_select",
    "varga_select": "koonji_read",
    "koonji_read": "dasha_windows",
    "dasha_windows": "ground",
    ...
}
```

and add `"hierarchy"` and `"koonji_read"` to `NODE_NAMES` plus `g.add_node`
calls. `koonji_read` is Task 6; add it as a stub returning `{"reading": None}`
in this task so the graph compiles and the edge test passes, then fill it.

- [ ] **Step 7: Run the tests**

Run: `./.venv/bin/python -m pytest tests/graph/ tests/varga/ tests/timing/ -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add rishivan/graph tests/graph
git commit -m "feat(graph): settle the domain before the nodes that depend on it"
```

---

### Task 6: The `koonji_read` node

**Files:** Modify `rishivan/graph/nodes/koonji.py` (created as a stub in Task 5 — move it to its own module) · Test `tests/graph/test_nodes_koonji.py`

**Interfaces:**
- Consumes: `hierarchy`, `retrieval_plan`, `vargas`, `chart`, `chart_state`
- Produces: `reading`, and a `chart_state` refreshed with yogas

**This is the task that connects 1,117 compiled rules to the product.** They are
currently unreachable from any user question.

- [ ] **Step 1: Write the failing test**

```python
def test_a_real_chart_produces_a_reading(chart):
    out = koonji_read_node(_state(chart, "domain.wealth"))
    assert out["reading"] is not None
    assert out["reading"].considered > 0


def test_the_selected_vargas_reach_the_fact_set(chart):
    """Phase 3 selects D9 for a marriage question; the fact set must contain
    D9 atoms or the selection bought nothing."""
    out = koonji_read_node(_state(chart, "domain.relationship", vargas=("D1", "D9")))
    atoms = out["reading"].facts.atoms
    assert any("d9" in a for a in _atom_strings(atoms))


def test_the_hierarchy_weights_reach_the_evidence_graph(chart, monkeypatch):
    seen = {}
    ...  # patch build_evidence, assert tier_weights == hierarchy.tier_weights


def test_no_chart_means_no_reading_and_no_exception():
    assert koonji_read_node(_state(None, "domain.wealth"))["reading"] is None


def test_a_bundle_failure_degrades_to_no_reading_not_to_a_crash(chart, monkeypatch):
    """A stale or missing bundle must cost the Koonji half of the answer, not
    the whole answer. Page retrieval still works."""
    monkeypatch.setattr(koonji, "_engine", _raising)
    assert koonji_read_node(_state(chart, "domain.wealth"))["reading"] is None


def test_yogas_land_on_the_chart_state(chart):
    out = koonji_read_node(_state(chart, "domain.wealth"))
    assert "chart_state" in out
```

- [ ] **Step 2: Run it and watch it fail**

Expected: FAIL — the stub returns `{"reading": None}` unconditionally.

- [ ] **Step 3: Implement**

```python
# rishivan/graph/nodes/koonji.py
"""Run the rule engine against this chart, under this question's hierarchy.

Three things this node does that the engine's own `answer()` does not, and why
it is a node rather than a call to `Engine.answer`:

  * **The fact set is compiled with the vargas Phase 3 selected**, not the
    six-varga default. Selecting D9 for a marriage question and then compiling
    facts without it buys nothing.
  * **The evidence graph is weighted by the hierarchy** (§12), so a D1 house
    placement outranks a D9 confirmation of it.
  * **The question gates already ran** at intake. `Engine.answer` re-parses and
    re-gates, which would make the graph's routing and the engine's routing two
    things that can disagree.

The engine is cached at module level: `from_rules()` compiles 1,117 rules, and
paying that per request would put ~2s on the critical path of every chart
question.
"""

_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        from rishivan.koonji.engine import Engine
        _ENGINE = Engine.from_rules()
    return _ENGINE


def koonji_read_node(state: RishivanState) -> dict:
    chart = state.get("chart")
    if chart is None:
        return {"reading": None}

    hierarchy = state.get("hierarchy")
    plan = state.get("retrieval_plan")
    selection = state.get("vargas")
    try:
        engine = _engine()
        reading = engine.read(
            chart,
            when=state.get("query_time"),
            domains=set(plan.domains) if plan and plan.domains else None,
            schools=set(plan.schools) if plan and plan.schools else None,
            vargas=selection.selected if selection else None,
            tier_weights=hierarchy.tier_weights if hierarchy else None,
            min_independent=(
                hierarchy.min_independent_sources if hierarchy else None
            ),
        )
    except Exception:  # noqa: BLE001
        # A stale bundle costs the rule half of the answer. Page retrieval is
        # untouched and still grounds a reply. Failing the whole turn here
        # would make a deployment problem look like a silent corpus.
        return {"reading": None}

    out: dict = {"reading": reading}
    chart_state = state.get("chart_state")
    if chart_state is not None:
        from rishivan.chartstate.build import with_yogas
        out["chart_state"] = with_yogas(chart_state, reading.yogas())
    return out
```

`Engine.read` gains `vargas`, `tier_weights` and `min_independent` parameters,
all defaulting to `None` so every existing caller is unchanged; they thread to
`index.facts_for(chart, when=..., vargas=...)` and `build_evidence`.

`with_yogas(state, yogas)` in `chartstate/build.py` returns a new frozen
`ChartState` with `PlanetDiagnosis.yogas` and `HouseDiagnosis.yogas` filled —
closing the field Phase 2 declared empty. `dataclasses.replace` throughout;
nothing is mutated.

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/graph/ tests/koonji/ tests/chartstate/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rishivan/graph/nodes/koonji.py rishivan/koonji/engine.py rishivan/chartstate/build.py tests/
git commit -m "feat(graph): the rule engine finally reads the chart"
```

---

### Task 7: The `RishiReport` contract

**Files:** Create `rishivan/council/rishis/__init__.py`, `rishivan/council/rishis/contract.py` · Test `tests/council/test_rishi_contract.py`

**Interfaces:**
- Produces: `EvidenceItem`, `RishiReport`, `REPORT_SCHEMA: dict`, `parse_report(text, *, rishi, domain) -> RishiReport`

- [ ] **Step 1: Write the failing test**

```python
def test_a_report_with_support_and_no_weakening_is_rejected():
    with pytest.raises(ValidationError):
        RishiReport(rishi="vyom", domain="domain.wealth",
                    supporting=[_item()], weakening=[],
                    score=0.5, confidence=0.6)


def test_an_abstention_may_have_neither():
    RishiReport(rishi="vyom", domain="domain.wealth", supporting=[],
                weakening=[], score=0.0, confidence=0.0,
                abstained="no rules fired in this domain")


def test_an_evidence_item_must_cite_a_rule():
    with pytest.raises(ValidationError):
        EvidenceItem(statement="Jupiter is strong", rule_ids=[],
                     chart_basis=["graha.jupiter"], weight=0.5, tier="house")


def test_a_tier_outside_the_declared_set_is_rejected():
    with pytest.raises(ValidationError):
        EvidenceItem(statement="x", rule_ids=["r1"], chart_basis=["y"],
                     weight=0.5, tier="vibes")


def test_score_is_bounded_both_ways():
    with pytest.raises(ValidationError):
        RishiReport(rishi="vyom", domain="d", supporting=[_item()],
                    weakening=[_item()], score=1.5, confidence=0.5)


def test_unparseable_output_becomes_an_abstention_not_an_exception():
    """A model that returns prose where JSON was asked for must cost one
    Rishi's opinion, not the turn."""
    report = parse_report("I think it's good!", rishi="vyom", domain="d")
    assert report.abstained


def test_a_report_citing_a_rule_that_did_not_fire_is_rejected(reading):
    """The strongest guard in the file. A model asked for evidence will
    invent a plausible rule id if nothing stops it."""
    with pytest.raises(ValidationError):
        ...
```

- [ ] **Step 2: Run it and watch it fail**

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Pydantic v2 models, matching the spec's §9.1 shapes exactly. Two validators
carry the weight:

```python
    @model_validator(mode="after")
    def _weakening_is_required(self) -> "RishiReport":
        """A report with supporting evidence and nothing against it is a
        sales pitch.

        Every product on the market suppresses disconfirming signal because it
        makes the answer messier. Including it is the entire credibility play,
        and a contract is the only place a discipline like this survives
        contact with a model that would rather be encouraging.
        """
        if self.supporting and not self.weakening and not self.abstained:
            raise ValueError(
                f"{self.rishi} gave {len(self.supporting)} supporting items and "
                f"nothing weakening. Either the chart genuinely says one thing "
                f"- in which case say so in `weakening` as 'no contrary "
                f"indication found, and here is what I looked for' - or "
                f"abstain."
            )
        return self
```

`parse_report` catches `JSONDecodeError` and `ValidationError` and returns an
abstaining report carrying the reason, so a bad generation costs one opinion.

`REPORT_SCHEMA` is the JSON schema handed to the model as
`response_json_schema`, generated from the pydantic model rather than
hand-written — a hand-written copy is a second thing to drift.

- [ ] **Step 4: Run the tests** · **Step 5: Commit**

```bash
git commit -m "feat(council): a Rishi report must say what argues against it"
```

---

### Task 8: The Rishi roster and the router

**Files:** Create `rishivan/council/rishis/roster.py` · Modify `rishivan/graph/edges.py` · Test `tests/council/test_roster.py`, `tests/graph/test_edges.py`

**Interfaces:**
- Consumes: `koonji_domains_for_rishi` (Task 2), `SERVICE_RISHIS`, `Reading`
- Produces: `ROLES: dict[str, RishiRole]`, `route_rishis(state) -> list[Send]`

**The existing eight personas keep their names** (`agam`, `vyom`, `ritam`,
`dhruvan`, `medhan`, `tattvan`, `pragnav`, `tejan`) — the spec says so
explicitly, and renaming would silently change what every `rishi_affinity`
annotation in the corpus means. What Phase 4 adds is a **role** per persona: an
analytical remit, a reads-list, and a condition under which it is invited.

Sakshi is a role with **no persona**, because it never speaks in a voice — it
audits. Adding a ninth persona would break `ALL_RISHI_NAMES` and the no-orphan
test for no gain.

- [ ] **Step 1: Write the failing test**

```python
def test_every_persona_has_a_role():
    from rishivan.council.personas import ALL_RISHI_NAMES
    assert set(ALL_RISHI_NAMES) <= set(ROLES)


def test_sakshi_is_a_role_without_a_persona():
    from rishivan.council.personas import ALL_RISHI_NAMES
    assert "sakshi" in ROLES
    assert "sakshi" not in ALL_RISHI_NAMES


def test_the_classical_voice_always_runs(state_with_reading):
    assert "vyom" in _targets(route_rishis(state_with_reading))


def test_the_domain_rishi_for_marriage_is_invited(state_with_reading):
    state_with_reading["koonji_domain"] = "domain.relationship"
    assert "medhan" in _targets(route_rishis(state_with_reading))


def test_the_timing_rishi_is_invited_only_for_a_timing_question(state_with_reading):
    assert "ritam" not in _targets(route_rishis(state_with_reading))
    state_with_reading["spec"] = _timing_spec()
    assert "ritam" in _targets(route_rishis(state_with_reading))


def test_a_rishi_with_no_fired_rules_is_not_invited(state_with_reading):
    """The router proposes; the evidence disposes. Inviting a Rishi whose
    subgraph is empty spends tokens to produce confident filler, because a
    model asked for an opinion supplies one."""
    state_with_reading["reading"] = _reading_with_no_firings()
    assert _targets(route_rishis(state_with_reading)) == ["vyom"]


def test_sakshi_is_not_in_the_fanout():
    """It runs after, on the reports. Fanning it out with its subjects means
    auditing an empty list."""
    assert "sakshi" not in _targets(route_rishis(_state()))


def test_the_fanout_is_capped(state_with_reading):
    assert len(route_rishis(state_with_reading)) <= MAX_RISHIS


def test_no_reading_means_the_classical_voice_alone(state_no_reading):
    assert _targets(route_rishis(state_no_reading)) == ["vyom"]
```

- [ ] **Step 2: Run it and watch it fail** · **Step 3: Implement**

```python
# rishivan/council/rishis/roster.py

MAX_RISHIS = 5
"""Four opinions plus the classical voice. §12's "invoke the minimum set"
is a cost statement and a quality one: the fifth marginal Rishi on a wealth
question is agreeing with the fourth, and agreement between two restatements
is the thing the evidence graph already discounts."""


@dataclass(frozen=True, slots=True)
class RishiRole:
    persona: str
    remit: str
    """One sentence, and it goes in the prompt. A role a reviewer cannot read
    is a role nobody can tell is being played wrong."""

    reads: tuple[str, ...]
    """State keys this role is given. `sakshi` reads `reports` too."""

    always: bool = False
    timing_only: bool = False
    requires_jaimini: bool = False
```

`route_rishis` returns `list[Send]`, each `Send("rishi", {...})` carrying the
persona name in the payload. Order: `vyom` first, then the domain Rishis by
descending life-domain weight, capped at `MAX_RISHIS`.

The evidence gate: a Rishi is invited only if
`koonji_domains_for_rishi(persona) & _domains_that_fired(reading)` is non-empty.

- [ ] **Step 4: Run the tests** · **Step 5: Commit**

---

### Task 9: The Rishi node

**Files:** Create `rishivan/council/rishis/prompt.py`, `rishivan/graph/nodes/rishi.py` · Modify `rishivan/graph/build.py` · Test `tests/graph/test_nodes_rishi.py`

**Interfaces:**
- Consumes: `RishiReport`, `REPORT_SCHEMA`, `ROLES`, `EvidenceHierarchy`
- Produces: node `rishi_node(state, *, client) -> dict` writing `{"reports": [report]}`

One node function, parameterised by the persona in the `Send` payload. Eight
near-identical node functions would be eight places for a prompt fix to be
applied seven times.

- [ ] **Step 1: Write the failing test**

```python
def test_the_report_lands_in_the_reduced_channel(recording_client):
    out = rishi_node(_state("medhan"), client=recording_client)
    assert isinstance(out["reports"], list) and len(out["reports"]) == 1


def test_the_prompt_contains_only_this_rishis_evidence(recording_client):
    rishi_node(_state("medhan"), client=recording_client)
    prompt = recording_client.prompts[0]
    assert "domain.relationship" in prompt
    assert "domain.longevity" not in prompt


def test_the_prompt_names_the_hierarchy_it_must_argue_from(recording_client):
    rishi_node(_state("medhan"), client=recording_client)
    assert "7th house" in recording_client.prompts[0]


def test_the_prompt_carries_the_cancelled_rules(recording_client):
    """A yoga the VM cancelled is the most important thing a Rishi can be
    told, and the one a model will never infer from the fired list."""
    rishi_node(_state("medhan"), client=recording_client)
    assert "CANCELLED" in recording_client.prompts[0]


def test_a_model_failure_becomes_an_abstention(failing_client):
    out = rishi_node(_state("medhan"), client=failing_client)
    assert out["reports"][0].abstained


def test_two_rishis_can_write_concurrently():
    """`reports` is the only reduced channel. A second key written from a
    fanned-out node is an InvalidUpdateError at runtime, on a branch a node
    test cannot reach."""
    out = rishi_node(_state("medhan"), client=_recording())
    assert set(out) == {"reports"}
```

That last test is the guard against the class of bug that shipped in Phase 1 —
except this time the failure is loud rather than silent, which is the one mercy
of concurrent writes.

- [ ] **Step 2: Run it and watch it fail** · **Step 3: Implement**

The prompt is assembled from structured evidence only:

```
YOUR REMIT          <role.remit>
THE QUESTION        <question>
EVIDENCE HIERARCHY  houses 7, 2, 8, 11 in priority order · lords 7, 2 ·
                    karakas Venus, Jupiter · D9 · Upapada, Darakaraka
                    This domain needs 2 independent sources for a claim.
CHART DIAGNOSIS     <the ChartState slice this role reads>
RULES THAT FIRED    <claim, confidence, citations, tier>
RULES THAT WERE CANCELLED  <rule, what cancelled it>
RULES INDETERMINATE <rule, which predicate could not be evaluated>
VARGAS WITHHELD     <code, why>
TIMING              <the EventWindow, or why there is none>
```

`generate_content` with `response_mime_type="application/json"` and
`response_json_schema=REPORT_SCHEMA`, wrapped so any exception becomes
`parse_report`'s abstention path. Register the node with
`g.add_node("rishi", partial(rishi.rishi_node, client=client))` — one node, many
`Send`s.

- [ ] **Step 4: Run the tests** · **Step 5: Commit**

---

### Task 10: Sakshi and the bounded re-examination

**Files:** Create `rishivan/council/rishis/sakshi.py`, `rishivan/graph/nodes/sakshi.py` · Modify `rishivan/graph/edges.py`, `build.py` · Test `tests/council/test_sakshi.py`, `tests/graph/test_edges.py`

**Interfaces:**
- Produces: `Audit` model, `audit_deterministic(reports, *, hierarchy, reading) -> list[Finding]`, node `sakshi_node`, router `route_after_sakshi(state) -> str`

**Half of Sakshi is deterministic and runs before any model call.** Six of the
seven things the spec asks it to hunt for are checkable in code:

| Check | Deterministic? |
|---|---|
| A hierarchy element no report mentions | yes |
| A cancellation the VM found that no report mentions | yes |
| Timing asserted with no dasha window | yes |
| A claim below `min_independent_sources` | yes |
| Two reports whose scores disagree in sign | yes |
| A cited rule that did not fire | yes — contract-enforced already |
| Alternative explanations | no — the model's job |

Doing the six in code means the audit still works when the model call fails,
and it means each has a test.

- [ ] **Step 1: Write the failing test**

```python
def test_a_cancelled_yoga_nobody_mentioned_is_a_finding(reports, reading):
    findings = audit_deterministic(reports, hierarchy=H, reading=reading)
    assert any(f.kind == "unmentioned_cancellation" for f in findings)


def test_a_claim_below_the_corroboration_floor_is_a_finding(...):
    ...


def test_two_reports_disagreeing_in_sign_is_a_finding(...):
    ...


def test_timing_asserted_without_a_window_is_a_finding(...):
    ...


def test_a_clean_set_of_reports_produces_no_findings(...):
    """The check that stops the auditor becoming decoration. An auditor that
    always finds something is an auditor nobody reads."""
    assert audit_deterministic(clean_reports, hierarchy=H, reading=r) == []


def test_re_examination_runs_at_most_once():
    assert route_after_sakshi({"audit": _with_findings(), "revisions": 0}) == "re_examine"
    assert route_after_sakshi({"audit": _with_findings(), "revisions": 1}) == "synthesis"


def test_a_clean_audit_forwards_immediately():
    assert route_after_sakshi({"audit": _clean(), "revisions": 0}) == "synthesis"
```

The `revisions >= 1` case is the one that matters. An unbounded critic loop is
how a graph hangs in production at 3 a.m., and it is a single `>=` away.

- [ ] **Step 2: Run it and watch it fail** · **Step 3: Implement**

`re_examine` re-runs `route_rishis` for **only the Rishis named in a finding**,
with the findings appended to their prompts, and increments `revisions`.
Because `reports` is additive, the re-run appends rather than replaces —
synthesis takes the latest report per Rishi and keeps the earlier one in the
trace, so the correction is visible rather than overwritten.

- [ ] **Step 4: Run the tests** · **Step 5: Commit**

---

### Task 11: Synthesis into the answer

**Files:** Create `rishivan/graph/nodes/synthesis.py` · Modify `rishivan/council/prompts.py`, `rishivan/graph/nodes/answer.py`, `build.py`, `state.py` · Test `tests/graph/test_nodes_synthesis.py`, `tests/graph/test_integration.py`

**Interfaces:**
- Produces: `synthesis_node(state) -> dict` writing `council_summary: str`, `convergence: dict`

Deterministic — it arranges what the Rishis said, it does not re-decide it. The
narrative voice stays in `answer_node`, which is where Phase 5's `AnswerPlan`
gate will sit.

- [ ] **Step 1: Write the failing test**

```python
def test_agreement_between_two_rishis_is_reported_not_averaged(reports):
    out = synthesis_node(_state(reports))
    assert out["convergence"]["agreeing"] == 2
    assert "score" not in out["convergence"]


def test_a_disagreement_survives_into_the_summary(conflicting_reports):
    out = synthesis_node(_state(conflicting_reports))
    assert "disagree" in out["council_summary"].lower()


def test_abstentions_are_named_not_dropped(reports_with_abstention):
    out = synthesis_node(_state(reports_with_abstention))
    assert "abstained" in out["council_summary"].lower()


def test_weakening_evidence_reaches_the_summary(reports):
    assert "against" in synthesis_node(_state(reports))["council_summary"].lower()


def test_the_audit_findings_reach_the_summary(reports, audit):
    ...


def test_no_reports_produces_an_honest_summary_not_an_empty_string():
    out = synthesis_node(_state([]))
    assert out["council_summary"]


# tests/graph/test_integration.py — the seam assertion, as in Phase 1
def test_the_council_summary_reaches_the_prompt(served):
    assert "COUNCIL" in served["prompt"]
```

That last one is the Phase 1 lesson applied: node-level tests cannot see the
node↔graph seam, and both shipping bugs lived there. Assert on the prompt
string.

- [ ] **Step 2: Run it and watch it fail** · **Step 3: Implement**

`build_rishi_prompt` gains a `council=` parameter rendering the summary block.
Declare `council_summary` and `convergence` in `RishivanState` with defaults —
`test_integration.py`'s AST walk will fail the build otherwise, which is
exactly what it is for.

Edges: `retrieve → fan_out_rishis` (conditional, `route_rishis`) → `rishi` →
`sakshi` → conditional (`route_after_sakshi`) → `re_examine` | `synthesis` →
`answer`. The existing `route_after_retrieval` insufficient path is unchanged
and still short-circuits to `insufficient`.

- [ ] **Step 4: Run the full suite**

```bash
mv tests.py /tmp/tests.py.bak
./.venv/bin/python -m pytest -q
mv /tmp/tests.py.bak tests.py
```

Expected: PASS, ~1,608 existing plus the new ones.

- [ ] **Step 5: Commit**

---

### Task 12: Documentation

**Files:** Create `rishivan/council/rishis/README.md` · Modify `rishivan/graph/README.md`, `docs/client-spec-gap-map.md`

- [ ] Update the graph README's topology diagram and **delete its "Phase 4 has a
      reordering to make" note**, which Task 5 discharges.
- [ ] Gap map: ER §1 rows "Rishi reasoning", "Cross-Rishi evidence comparison",
      "Master synthesis", "Uncertainty in the answer" move off `PARTIAL`/`ABSENT`.
      **`rule.confidence` is still uniformly 0.5** — the confidence a report
      carries now comes from the evidence graph, not the rule, so say that
      rather than implying the rule field was fixed.
- [ ] Record what Phase 4 does **not** close: `functional_nature` is still
      corpus-blocked, Shadbala is still partial, and `transit` is a declared
      tier no predicate can reach.
- [ ] Commit.

---

## Self-review

**Spec coverage.** §8/blueprint §12: hierarchy dataclass ✓ (T1), seeded rows ✓
(T1), domains filter ✓ (T5/T6), varga set ✓ (T5), `tier_weights` into
`build_evidence` ✓ (T3/T6), `min_independent_sources` set by hierarchy and
enforced in `evidence.py` ✓ (T3 — settles spec open decision 3 the way it
recommends). §9/blueprint §11: eight roles on the existing persona names ✓
(T8), `RishiReport` with required `weakening` ✓ (T7), `EvidenceItem` tracing to
rule ids ✓ (T7), `Send` fan-out ✓ (T8), evidence-gated invitation ✓ (T8),
Sakshi's six hunts ✓ (T10), bounded re-examination ✓ (T10), synthesis ✓ (T11),
deterministic fallback per model node ✓ (T7/T9).

**Spec decisions this plan makes, for a reviewer to overturn if wrong:**

1. **Rishis receive, they do not retrieve** (spec open decision 4). One
   `koonji_read` produces one evidence graph; each Rishi is handed its slice.
   Letting eight nodes each call `index.query` is more flexible and destroys the
   determinism guarantee the whole prefix is built on.
2. **Sakshi has no persona.** It audits; it never speaks in a voice.
3. **`tier_of` is derived from predicates, not stored on the rule.** The
   alternative is a tier field on the rule dialect and a re-extraction of 1,117
   rules to populate something computable.
4. **A mixed-tier rule takes its weakest tier.**

**Deliberately out of scope:** the `AnswerPlan`/`AllowedClaims` gate, the
streaming critic, trace persistence and the prediction ledger — all Phase 5,
which also unblocks checkpointing by getting the live generator out of state.

**Risk, and where it is concentrated.** Task 5 reorders the deterministic
prefix and Task 6 puts a 1,117-rule engine on the critical path of every chart
question. Both touch code that `tests/graph/test_parity.py` pins against the
old orchestrator's behaviour. Run the parity suite after each, not at the end.
The engine cache in Task 6 is the one place a first request pays ~2s; if that
shows up, the fix is a bundle (`Engine.from_bundle`) built in CI, not a lazier
cache.

**Second risk:** `min_independent_sources` of 2 on marriage, career, wealth,
progeny, health and status will make some claims that used to surface fall
below the corroboration bar. That is the intended behaviour and it will look
like a regression. Task 3's tests pin the mechanism; a golden-set comparison
before and after Task 6 is worth the twenty minutes.
