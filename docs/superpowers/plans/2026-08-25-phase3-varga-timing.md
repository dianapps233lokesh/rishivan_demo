# Phase 3 — Varga Policy and the Timing Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make divisional charts *policy-governed* rather than incidental, and turn Vimshottari periods into the blueprint's five-stage event windows.

**Architecture:** Two new packages — `rishivan/varga/` (which vargas may speak, and when they must be withheld) and `rishivan/timing/` (promise → activation → trigger → peak → fading). Two sibling graph nodes reading `chart_state`, running concurrently, both feeding grounding.

**Tech Stack:** existing `chart/vendor/varga` (all 16 vargas computable) · existing `chart/dasha.py` (five levels, exact start/end) · `chart/transit.py`.

**Spec:** `docs/superpowers/specs/2026-08-25-chart-understanding-council-architecture.md` §6–§7 (blueprint §7, §8)

## Global Constraints

- **Pure and deterministic.** A `when` is always passed, never read from the clock inside a computation.
- **Reuse.** `chart/dasha.py` already computes exact period boundaries at five levels; `vendor/varga` already computes all 16 divisions. Neither is reimplemented. A second copy of a boundary calculation is a second thing to drift.
- **Never present false precision** (spec C5). A varga the birth time cannot support is *withheld with a stated reason*, not quietly downweighted.
- **A promise is not an event.** No window is emitted for an event the chart does not promise.
- **Systems are not blended.** When a second dasha system arrives it is a second opinion, reported separately.
- Test runner: `./.venv/bin/python -m pytest`.

## What exists, measured

| Capability | State |
|---|---|
| All 16 vargas computable | `vendor/varga.VARGA_REGISTRY`, `varga_longitude(code, lon)` |
| Vimshottari, 5 levels, exact bounds | `chart/dasha.py` — `Period(lord, start, end, level)`, `current_periods`, `mahadasha_timeline` |
| Transit chart for any moment | `chart/transit.chart_for_moment(when, …)` |
| Chart diagnosis | `chartstate.ChartState` (Phase 2) |
| Vargas reaching the fact set | **only 6** — `facts.EMITTED_VARGAS = D2 D7 D9 D10 D12 D30` |
| Per-varga purpose / method / evidence tier | **absent** |
| Birth-time precision | **absent** — `BirthData` has no precision field |
| Five-stage windows | **absent** |
| Period → what it activates | **absent** |

## The design problem this phase has to solve

`BirthData` records `hour`/`minute`/`second` and says nothing about how much of
that is *known*. D60's arc is **0.5°**; at hour-level uncertainty the ascendant
moves roughly **7.5°**, so a D60 reading on a time recorded as "12:00" is fifteen
signs of noise wearing a decimal point. The gate is arithmetic, not taste — but
it needs an input that does not exist.

**Resolution:** infer a default from how *round* the recorded time is, and let
the caller override. A time given as `4:37:00` was read off something; `12:00:00`
and `4:30:00` were almost certainly rounded. The inference is a heuristic and is
labelled one; the override is authoritative and is what a rectified chart uses.

---

### Task 1: Birth-time confidence

**Files:** Create `rishivan/varga/__init__.py`, `rishivan/varga/confidence.py` · Test `tests/varga/test_confidence.py`

**Interfaces:** `BirthConfidence(IntEnum)`, `infer_confidence(birth) -> BirthConfidence`, `arc_uncertainty_degrees(confidence) -> float`

```python
class BirthConfidence(IntEnum):
    UNKNOWN  = 0   # no time given; noon assumed
    HOUR     = 1   # on the hour, or ±30 min
    QUARTER  = 2   # on a quarter hour, or ±15 min
    MINUTE   = 3   # to the minute, or rectified
    EXACT    = 4   # to the second
```

Inference: `second != 0` → EXACT · `minute % 15 != 0` → MINUTE · `minute % 60 == 0` → HOUR · else QUARTER. Midnight-exactly is treated as UNKNOWN, because `00:00` is what a form defaults to when nobody entered anything.

`arc_uncertainty_degrees` converts a confidence to how far the ascendant could be wrong: the ascendant moves ~15°/hour, so HOUR ≈ 7.5°, QUARTER ≈ 3.75°, MINUTE ≈ 0.25°.

### Task 2: The varga policy registry

**Files:** Create `rishivan/varga/policy.py` · Test `tests/varga/test_policy.py`

All 16 entries, seeded verbatim from the blueprint table: purpose, primary domain, method, `usage`, `evidence_tier`, and `min_birth_confidence` derived from each varga's arc rather than asserted.

The arc derivation is the point: `min_confidence_for(divisor)` returns the coarsest confidence whose ascendant uncertainty stays inside one varga division. D1 (30° divisions) tolerates UNKNOWN; D9 (3°20′) needs QUARTER; D60 (0.5°) needs MINUTE. Written as arithmetic so adding D81 needs no judgement call.

A test asserts every code in `VARGA_REGISTRY` has a policy, and that no policy names a method without a source.

### Task 3: Varga selection

**Files:** Create `rishivan/varga/select.py` · Test `tests/varga/test_select.py`

**Interfaces:** `select_vargas(domain, confidence, *, always=("D1",)) -> VargaSelection`

```python
@dataclass(frozen=True, slots=True)
class WithheldVarga:
    code: str
    required: BirthConfidence
    actual: BirthConfidence
    reason: str          # user-facing, names the shortfall

@dataclass(frozen=True, slots=True)
class VargaSelection:
    selected: tuple[str, ...]
    withheld: tuple[WithheldVarga, ...]
    confidence: BirthConfidence
    reason: str
```

`withheld` is a first-class output, not a filter side effect. *"D60 needs a birth time to the minute; yours is recorded to the hour, so I have not used it"* is the product, and it cannot be said by a pipeline that silently drops the varga.

D9 and D10 are mandatory cross-checks where applicable — if either is withheld for confidence, that fact travels with the answer rather than leaving a gap nobody can see.

### Task 4: Per-request varga emission

**Files:** Modify `rishivan/koonji/facts.py` · Test `tests/varga/test_emission.py`

`compile_facts(chart, *, vargas=EMITTED_VARGAS)` — the six become a default, not a constant. 16 vargas × 9 grahas is 144 extra atoms per chart, most never matched, so the selection runs *before* fact compilation and the fact set is built once with the right divisions in it.

The existing 6-varga default must produce a byte-identical fact set, so nothing already tested changes.

### Task 5: Dasha activation mapping

**Files:** Create `rishivan/timing/__init__.py`, `rishivan/timing/activation.py` · Test `tests/timing/test_activation.py`

**Interfaces:** `activates(chart_state, lord) -> Activation`

What a period lord touches: houses it owns, occupies and aspects; natural karakas it carries; grahas whose nakshatra it lords. This is what makes a period *relevant to a domain*, and it is what the Kala Rishi reasons over in Phase 4.

Reads `ChartState` rather than the chart, so it inherits Phase 2's functional verdicts instead of recomputing lordship.

### Task 6: The five windows

**Files:** Create `rishivan/timing/windows.py` · Test `tests/timing/test_windows.py`

```python
@dataclass(frozen=True, slots=True)
class EventWindow:
    promise: bool
    promise_basis: tuple[str, ...]
    activation: DateRange | None
    trigger: DateRange | None
    peak: DateRange | None
    fading: DateRange | None
    confidence: float
    reasons: tuple[str, ...]
```

**`promise=False` short-circuits everything.** A timing question about an event the chart does not promise has no answer worth computing, and producing a window anyway is the most common way an astrology product invents a prediction. Hard gate, not a low score — the tests assert `activation is None` whenever `promise` is False.

Mapping: the mahadasha whose lord activates the domain is the **activation** window; the antardasha within it that also activates is the **trigger**; pratyantar plus transit corroboration is the **peak**; the tail of the activation window after the trigger closes is **fading**.

### Task 7: Arbitrary date-time queries

**Files:** Create `rishivan/timing/query.py` · Test `tests/timing/test_query.py`

`periods_at(chart, when, levels=3)` and `windows_between(chart, state, domain, start, end)`. Both pure; both cached on `(chart_digest, when)`. Exact boundaries come from `chart/dasha.py` and are never re-derived here.

`TimingReport.by_system: dict[str, EventWindow]` — Chara Dasha, when it arrives, is a second opinion under its own key. Averaging two dasha systems produces a number no tradition endorses and no reviewer can check.

### Task 8: Two graph nodes

**Files:** Create `rishivan/graph/nodes/varga.py`, `rishivan/graph/nodes/timing.py` · Modify `rishivan/graph/build.py`, `state.py` · Test `tests/graph/test_nodes_varga_timing.py`

`varga_select` and `dasha_windows` are siblings reading `chart_state`; neither reads the other. Both feed `ground`.

Declare `vargas` and `timing` in `RishivanState` — **both are already placeholders there, and every key a node returns must be declared or LangGraph discards it silently.** That bug shipped once in Phase 1; `test_integration.py`'s schema walk will catch a repeat.

### Task 9: Documentation

`rishivan/varga/README.md`, `rishivan/timing/README.md`, gap-map update.

---

## Self-review

**Spec coverage.** §6/blueprint §7: policy per varga ✓ (T2), documented purpose and method ✓ (T2), birth-confidence gate ✓ (T1, T3), withheld-with-reason ✓ (T3), per-request emission ✓ (T4). §7/blueprint §8: five windows ✓ (T6), exact bounds reused ✓, arbitrary queries ✓ (T7), activation mapping ✓ (T5), multiple systems unblended ✓ (T7), sub-levels ✓ (already five deep).

**Deliberately out of scope:** RETE-style incremental re-matching over a 36-month horizon. The spec names it as the right tool for day-by-day scanning, but the window model here resolves to period boundaries — a few dozen per chart — not 1,100 daily fact sets. Revisit when transit-level granularity is actually needed.

**`HouseDiagnosis.transit_active`** is filled by Task 5, closing the field Phase 2 left declared and empty.

**Risk.** Task 4 touches `koonji/facts.py`, which 519 Koonji tests depend on. The default must produce a byte-identical fact set; that is the first test in Task 4, not the last.
