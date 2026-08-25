# Phase 2 — Chart State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a structured `ChartState` diagnosis — planet-level and house-level — before any prose prediction, as one node between the chart and grounding.

**Architecture:** A new `rishivan/chartstate/` package, pure functions over an existing `Chart`. It sits *beside* `koonji/facts.py`, not inside it: facts are flat interned atoms for retrieval, chart state is a navigable diagnosis for reasoning. Both derive from the same `Chart`, and a test asserts they never disagree.

**Tech Stack:** Python dataclasses (frozen, slots) · existing `rishivan.chart.relations` dignity tables · existing `rishivan.astro.constants`.

**Spec:** `docs/superpowers/specs/2026-08-25-chart-understanding-council-architecture.md` §5 (blueprint §6)

## Global Constraints

- **Pure and deterministic.** No model calls, no I/O, no wall-clock reads except a `when` passed in. The same `Chart` must produce a byte-identical `ChartState`.
- **Reuse, don't re-derive.** `relations.py` already owns the dignity tables (`EXALTATION`, `DEBILITATION`, `OWN_SIGNS`, `MOOLATRIKONA`) and Parashari drishti (`SPECIAL_ASPECTS`). `Chart.house_lords` already holds lordships. A second copy of any of these is a second thing to drift.
- **No fabricated doctrine.** Where a rule would need a citation we do not have, it is computed diagnosis with the gap documented — never a rule with an invented locator.
- **Frozen dataclasses.** `ChartState` is computed once and read by every Rishi (spec C1). A Rishi that can mutate it can make its colleagues disagree about a fact.
- Test runner: `./.venv/bin/python -m pytest`.

## Stated assumptions (flagged, not blocking)

1. **Lagna framework: Parashari standard** — kendra (1,4,7,10) and trikona (1,5,9) lordship, malefic-for-kendra-lordship for natural benefics, the 3/6/11 lords as functional malefics, and the yogakaraka rule for a planet owning both a kendra and a trikona. Namespaced as `"parashari"` so another lineage is additive.
2. **Strength: estimated, band only.** Full six-fold Shadbala is not implemented; `StrengthReading` carries `system`, `is_estimated=True`, and `components`. The scalar is withheld from any user-visible claim while `is_estimated` is true. A wrong strength number is worse than none, because everything downstream weights by it.

## Deliberately out of scope

- **Yogas.** In this system a yoga *is* a fired rule, and the engine already produces those — `ChartState.yogas` would need the engine, which runs after this node. It belongs with the evidence layer in Phase 4.
- **Emitting `functional_nature` into the Koonji fact set.** That predicate is declared `derived=True`, meaning a sourced `DERIVE_FACT` rule owns it. See Task 3's note.

---

### Task 1: The value types

**Files:**
- Create: `rishivan/chartstate/__init__.py`, `rishivan/chartstate/types.py`
- Test: `tests/chartstate/test_types.py`

**Interfaces:**
- Produces: `StrengthReading`, `PlanetDiagnosis`, `HouseDiagnosis`, `ChartState`, `Band`

- [ ] **Step 1: Write the failing test** — see `tests/chartstate/test_types.py` in the repo.
- [ ] **Step 2:** `./.venv/bin/python -m pytest tests/chartstate/test_types.py -q` → FAIL, no module.
- [ ] **Step 3:** implement `types.py`.
- [ ] **Step 4:** rerun → pass.
- [ ] **Step 5:** `git commit -m "feat(chartstate): the diagnosis value types"`

### Task 2: Dispositor and nakshatra-lord chains

**Files:** Create `rishivan/chartstate/dispositor.py` · Test `tests/chartstate/test_dispositor.py`

**Interfaces:** `dispositor_of(chart, graha) -> str`, `dispositor_chain(chart, graha) -> Chain`, `nakshatra_lord_chain(chart, graha) -> Chain`

The load-bearing detail: **cycle detection**. Sun in Cancer with Moon in Leo is a 2-cycle, and a chain-walker without a visited set hangs the request. `Chain` carries `path`, `terminus`, and `cycle: bool`.

### Task 3: Functional nature

**Files:** Create `rishivan/chartstate/functional.py` · Test `tests/chartstate/test_functional.py`

**Interfaces:** `functional_natures(chart, framework="parashari") -> dict[str, FunctionalVerdict]`

**Note on why this is code and not a rule.** The spec argued functional nature is doctrine and should therefore be sourced `DERIVE_FACT` rules. It is — but the ingested corpus holds only *lagna-specific* commentary (Bhavartha Ratnakara ch1 on Mesha lagna's 10th/11th lord), not a general statement of the kendra/trikona doctrine. Generalising those verses into a universal rule is precisely the scope inflation `validate.check_scope_inflation` exists to catch. So: computed here, framework named and namespaced, and the Koonji `functional_nature` predicate stays `derived=True` and unsatisfied until a general doctrine verse is acquired. That is a corpus gap, not an engineering one, and it is recorded in the gap map.

### Task 4: Strength

**Files:** Create `rishivan/chartstate/strength.py` · Test `tests/chartstate/test_strength.py`

**Interfaces:** `strength_of(chart, graha) -> StrengthReading`

Sthana (dignity) + Dig (directional) + a retrograde/combustion adjustment, normalised to 0..1 and banded. `is_estimated=True` throughout, `system="parashari.partial.v1"`.

### Task 5: Assembly and digest

**Files:** Create `rishivan/chartstate/build.py` · Test `tests/chartstate/test_build.py`

**Interfaces:** `build_chart_state(chart, when=None) -> ChartState`, `chart_digest(chart) -> str`

A digest mismatch on recomputation is the highest-severity alarm in the system: it means readings are silently changing under a stable question.

### Task 6: The graph node

**Files:** Create `rishivan/graph/nodes/diagnosis.py` · Modify `rishivan/graph/build.py`, `rishivan/graph/edges.py` · Test `tests/graph/test_nodes_diagnosis.py`

`chart_state_node` sits between each chart node and `ground`. Writes `chart_state` and `chart_digest` (both already declared in `RishivanState` — `chart_digest` is added).

### Task 7: Documentation

`rishivan/chartstate/README.md` + gap-map update.

---

## Self-review

**Spec coverage (§5 / blueprint §6).** Planet-level: natural nature ✓, functional nature ✓ (Task 3), dignity ✓ (reused), dispositor ✓ (Task 2), house placement and lordship ✓, conjunctions and aspects ✓, combustion/retrogression ✓, strength ✓ (Task 4, estimated), varga dignity ✓, nakshatra lord and chain ✓ (Task 2), yogas ✗ (deferred, reasoned above). House-level: lord/occupants/aspects/karakas ✓, lord and dispositor strength ✓, benefic-malefic influence ✓, varga confirmation ✓, dasha activation ✓, transit activation ✗ (needs Phase 3's transit windows; the field exists and stays empty).

**Two fields ship empty on purpose:** `PlanetDiagnosis.yogas` and `HouseDiagnosis.transit_active`. Declared so Phases 3 and 4 fill them rather than migrating the type.
