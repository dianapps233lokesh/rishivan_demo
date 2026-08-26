# Chart Understanding → Council → Answer: LangGraph Architecture

**Status:** design spec · 2026-08-25
**Implements:** Blueprint §6 (chart understanding), §7 (varga), §8 (dasha/time),
§11 (eight-Rishi council), §12 (event-specific engines)
**Sits on:** the Koonji engine (`rishivan/koonji/`), already built

---

## 1. What already exists, measured

Grounding first, because the plan below only makes sense against it.

| Capability | State | Where |
|---|---|---|
| URF frame, 7 assertion kinds | **built** | `koonji/urf.py` |
| Registry, 34 predicates, additive | **built** | `koonji/registry.py` |
| Fact compiler → ~1,977 interned atoms | **built** | `koonji/facts.py` |
| Inverted index, domain/school/status/weight filter | **built** | `koonji/index.py` |
| Rule VM, cancellation, modality | **built** | `koonji/vm.py` |
| Evidence graph, restatement discounting | **built** | `koonji/evidence.py` |
| Bundle, content-addressed, registry-fingerprinted | **built** | `koonji/bundle.py` |
| QuestionSpec + router + RetrievalPlan | **built** | `koonji/question.py`, `router.py` |
| Extraction: convert (free) + extract (model) | **built** | `koonji/convert.py`, `pipeline.py` |
| Rule corpus | **1,117 rules**, all `candidate` | `koonji/rules/` |
| Ephemeris, sidereal, 9 grahas | **built** | `chart/ephemeris.py` |
| Vargas D1–D60 computable | **built** | `chart/local_varga.py`, `vendor/varga` |
| Vimshottari with sub-periods, exact start/end | **built** | `chart/dasha.py` (`Period`) |
| Transits | **built** | `chart/transit.py` |
| Ashtakavarga (SAV) | **built** | `chart/local_ashtakavarga.py` |
| Council orchestrator | **564-line procedural function** | `council/orchestrator.py` |

**Gaps this spec closes:**

1. **No chart state.** `FactSet` is a flat atom set — correct for retrieval,
   useless as a diagnosis. Nothing produces planet-level or house-level analysis.
2. **`functional_nature` is declared `derived` and nothing derives it.**
   `derivation_count: 0`. Every rule resting on functional benefic/malefic
   currently evaluates INDETERMINATE.
3. **`strength` / `strength_band` are declared and never emitted.** No Shadbala.
4. **Only 6 vargas reach the fact set** (`D2 D7 D9 D10 D12 D30`), with no
   per-varga purpose, method note, or birth-time-confidence gate.
5. **No timing windows.** Periods exist; promise/activation/trigger/peak/fading
   does not, nor does period → activated houses/yogas/significators.
6. **The eight personas are a different taxonomy** (`agam vyom dhruvan ritam
   tejan medhan tattvan pragnav`) from the eight Rishi *roles* the blueprint
   names, and they write prose, not structured evidence.
7. **No per-domain evidence hierarchy.** One retrieval path for every question.
8. **LangGraph is not installed.** Control flow is `if`/`elif` inside one
   function.

---

## 2. Design commitments

Five rules that decide every question below.

**C1 — The chart state is computed once, before any reasoning, and is
immutable.** Every Rishi sees the *same* canonical state. A Rishi that
recomputes is a Rishi that can disagree with its colleagues about a fact rather
than about an interpretation, and that argument is unresolvable.

**C2 — Conditionals live on edges, not in nodes.** A node transforms state. A
`route_*` function chooses the next node and does nothing else. This is the
whole reason to adopt LangGraph: the 564-line orchestrator's branching becomes
inspectable, individually testable, and visualisable.

**C3 — Rishis return structured evidence, never prose.** `RishiReport` is a
Pydantic model with the blueprint's nine protocol steps as fields. Prose happens
once, at the end, from an `AnswerPlan` the synthesis layer gates.

**C4 — The evidence hierarchy is data, not code.** Per-domain hierarchies are a
versioned table compiled and validated like rules, not a chain of `if domain ==`.
Adding "business" must not mean editing a scoring function.

**C5 — Never present false precision.** A D60 reading on a birth time known to
±30 minutes is noise wearing a decimal point. Varga confidence is computed and
carried, and low-confidence vargas are withheld with a stated reason rather than
quietly downweighted.

---

## 3. Graph topology

```
                          ┌──────────┐
                          │  intake  │  parse → QuestionSpec (koonji/router)
                          └────┬─────┘
                        route_after_intake
        ┌──────────┬───────────┼───────────┬──────────────┐
        ▼          ▼           ▼           ▼              ▼
     refuse    clarify    need_input   non_analytic    proceed
        │          │           │           │              │
        └──────────┴─────┬─────┴───────────┘              │
                         ▼                                ▼
                     ┌───────┐                   ┌─────────────────┐
                     │ reply │◄──────────────────│ chart_materialise│
                     └───────┘                   └────────┬────────┘
                                                          ▼
                                                 ┌─────────────────┐
                                                 │   chart_state   │  §6
                                                 └────────┬────────┘
                                              ┌───────────┴───────────┐
                                              ▼                       ▼
                                     ┌────────────────┐      ┌────────────────┐
                                     │  varga_select  │ §7   │ dasha_windows  │ §8
                                     └────────┬───────┘      └────────┬───────┘
                                              └───────────┬───────────┘
                                                          ▼
                                                 ┌─────────────────┐
                                                 │ evidence_plan   │  §12
                                                 └────────┬────────┘
                                                          ▼
                                                 ┌─────────────────┐
                                                 │ koonji_retrieve │  existing
                                                 └────────┬────────┘
                                                 route_after_retrieval
                                              ┌───────────┴───────────┐
                                              ▼                       ▼
                                        insufficient            fan_out_rishis
                                              │            (Send, N parallel)
                                              │        ┌────┬────┬────┬────┐
                                              │        ▼    ▼    ▼    ▼    ▼
                                              │      para jaim naks kala …
                                              │        └────┴─┬──┴────┴────┘
                                              │                ▼
                                              │         ┌────────────┐
                                              │         │   sakshi   │  §11.8
                                              │         └──────┬─────┘
                                              │        route_after_sakshi
                                              │       ┌────────┴────────┐
                                              │       ▼                 ▼
                                              │   re_examine        synthesis
                                              │  (bounded ×1)           │
                                              │                         ▼
                                              │                 ┌───────────────┐
                                              │                 │  answer_plan  │ AllowedClaims
                                              │                 └───────┬───────┘
                                              └────────────────────────►│
                                                                        ▼
                                                                 ┌───────────┐
                                                                 │  narrate  │ streaming
                                                                 └─────┬─────┘
                                                                       ▼
                                                                 ┌───────────┐
                                                                 │  persist  │ trace + ledger
                                                                 └───────────┘
```

`varga_select` and `dasha_windows` are siblings and run concurrently — neither
reads the other's output; both read `chart_state`.

---

## 4. State schema

One `TypedDict`, `rishivan/graph/state.py`. Reducers noted where LangGraph needs
them for the parallel fan-out.

```python
class RishivanState(TypedDict, total=False):
    # -- request identity, set once at intake --------------------------
    run_id: str                      # ULID; becomes the trace id
    question: str
    turn: int
    history: list[dict]              # last N turns, read-only here

    # -- intake -------------------------------------------------------
    spec: QuestionSpec               # koonji/question.py, already built
    plan: RetrievalPlan              # koonji/router.py, already built
    outcome: str                     # served|refused|clarify|needs_input|…
    message: str                     # user-facing text for a terminal outcome

    # -- chart --------------------------------------------------------
    birth: BirthData | None
    chart: Chart | None
    chart_digest: str                # sha256 over positions; drift alarm

    # -- §6 -----------------------------------------------------------
    chart_state: ChartState | None   # THE canonical diagnosis. Immutable.

    # -- §7 -----------------------------------------------------------
    vargas: VargaSelection | None    # which, why, and with what confidence

    # -- §8 -----------------------------------------------------------
    timing: TimingReport | None      # windows + what each period activates

    # -- §12 ----------------------------------------------------------
    hierarchy: EvidenceHierarchy | None

    # -- Koonji -------------------------------------------------------
    reading: Reading | None          # koonji/engine.py, already built
    passages: list[Passage]          # Qdrant, citation display only

    # -- §11 · parallel fan-out; needs an additive reducer -------------
    reports: Annotated[list[RishiReport], operator.add]
    audit: SakshiReport | None
    revisions: int                   # bounded re-examination counter

    # -- output -------------------------------------------------------
    answer_plan: AnswerPlan | None   # AllowedClaims — the narrative gate
    answer: str
    trace: dict
```

**Why one flat state and not per-node models:** LangGraph merges partial dict
updates. A node returns only the keys it owns, so ownership stays obvious, and
the merge is what makes the parallel Rishi fan-out safe.

**`reports` is the only reduced key.** Eight nodes writing one list needs
`operator.add`. Everything else is written by exactly one node — enforced by a
test that asserts node/key ownership is a partition.

---

## 5. §6 — The chart-understanding engine

New package `rishivan/chartstate/`. Produces `ChartState`, a diagnosis, not a
fact set. It sits *beside* `koonji/facts.py`, not inside it: facts are for
retrieval (flat, interned, superset-safe), chart state is for reasoning
(structured, navigable, explanatory). Both are derived from the same `Chart`,
and a test asserts they never disagree.

### 5.1 `PlanetDiagnosis`

Every field in blueprint §6's planet-level list:

```python
@dataclass(frozen=True, slots=True)
class PlanetDiagnosis:
    graha: str                       # graha.saturn
    natural_nature: str              # benefic | malefic | neutral
    functional_nature: str           # per declared lagna framework
    functional_reason: str           # which lordships produced it
    rashi: str
    dignity: str
    dispositor: str                  # lord of the rashi it occupies
    dispositor_chain: tuple[str, ...]  # to a terminus or a detected cycle
    bhava: int
    lordships: tuple[int, ...]
    conjunctions: tuple[str, ...]
    aspects_cast: tuple[str, ...]
    aspects_received: tuple[str, ...]
    combust: bool
    retrograde: bool
    vargottama: bool
    strength: StrengthReading        # value, band, system, is_estimated
    varga_dignity: dict[str, str]    # {"D9": "exalted", "D10": "own_sign"}
    varga_confirms: dict[str, bool]  # does the varga corroborate D1?
    nakshatra: str
    nakshatra_lord: str
    nakshatra_lord_chain: tuple[str, ...]
    yogas: tuple[str, ...]           # yoga ids this planet participates in
```

### 5.2 `HouseDiagnosis`

```python
@dataclass(frozen=True, slots=True)
class HouseDiagnosis:
    bhava: int
    rashi: str
    lord: str
    lord_placement: int
    lord_strength: StrengthReading
    lord_dispositor: str
    occupants: tuple[str, ...]
    aspects_received: tuple[str, ...]
    karakas: tuple[str, ...]         # natural significators for this bhava
    benefic_influence: float         # −1..1, signed and explained
    influence_reason: tuple[str, ...]
    yogas: tuple[str, ...]
    varga_confirms: dict[str, bool]
    dasha_active: bool               # is a period lord tied to this house now
    transit_active: tuple[str, ...]
```

### 5.3 The four sub-engines

| Module | Produces | Notes |
|---|---|---|
| `functional.py` | functional benefic/malefic per lagna | **Doctrine, so it is rules, not code.** Emit as `DERIVE_FACT` rules into the registry's `functional_nature` predicate, sourced to a verse. Closes gap #2. |
| `dispositor.py` | dispositor + nakshatra-lord chains | Must detect cycles. Sun↔Moon mutual disposition is a 2-cycle and a chain-walker without a visited-set hangs. |
| `strength.py` | `StrengthReading` | Shadbala behind an interface with a **declared system id**, so "the selected strength system" is a config value. Ships with `sthana+dig+kaala` partial and `is_estimated=True` until the full six are validated. Closes gap #3. |
| `yoga.py` | yoga hits + cancellations | Reuses the Koonji VM — a yoga is a rule. No second matcher. |

**`strength.py` deserves the caution.** A Shadbala number that is wrong is worse
than none, because everything downstream weights by it. `StrengthReading` carries
`system`, `is_estimated`, and `components`, and `is_estimated=True` forces the
band into the fact set while keeping the scalar out of any user-visible claim.

### 5.4 The digest

`chart_digest = sha256(canonical(positions, ayanamsa, house_system, ephemeris_version))`.
Recomputation must reproduce it. **A mismatch is a page-on-call alarm**, not a
warning — it means readings are silently changing under a stable question.

---

## 6. §7 — Varga engine

New `rishivan/varga/policy.py`. A registry, in the Koonji sense: additive,
versioned, and every entry carries its own justification.

```python
@dataclass(frozen=True, slots=True)
class VargaPolicy:
    code: str                    # "D10"
    name: str                    # "Dashamsha"
    domain: str                  # "domain.career"
    purpose: str                 # one sentence, from the blueprint
    method: str                  # "parashari_standard" — the calculation used
    method_source: str           # book + locator. No method without a citation.
    usage: Literal["always", "mandatory_crosscheck", "domain_engine",
                   "method_specific", "validated_only"]
    min_birth_confidence: BirthConfidence
    evidence_tier: int           # 1 = corroborates D1, 2 = supporting only
```

Seeded verbatim from the blueprint table: D1 always · D2 wealth · D3 siblings ·
D4 property · D7 children · **D9 mandatory cross-check** · **D10 mandatory
career cross-check** · D12 parents · D16 comforts (method-gated) · D20
spirituality · D24 education · D27 (validated only) · D30 misfortune (cautious) ·
D40/D45 method-specific · **D60 requires exact-time confidence**.

### 6.1 Birth-time confidence — C5 made mechanical

```python
class BirthConfidence(IntEnum):
    UNKNOWN   = 0   # no time given; noon assumed
    HOUR      = 1   # ±30 min or worse
    QUARTER   = 2   # ±15 min
    MINUTE    = 3   # ±1 min, or rectified
    EXACT     = 4   # recorded to the second
```

A varga whose `min_birth_confidence` exceeds the chart's is **withheld**, and the
withholding is a first-class output:

```python
@dataclass(frozen=True, slots=True)
class VargaSelection:
    selected: tuple[str, ...]
    withheld: tuple[WithheldVarga, ...]   # code, required, actual, reason
    confidence: BirthConfidence
```

`withheld` reaches the user: *"D60 needs a birth time to the minute; yours is
recorded to the hour, so I have not used it."* That sentence is the product.

**Implementation note:** the varga arc for D60 is 0.5° — half a degree of
ascendant error changes the sign. At `HOUR` confidence the ascendant moves ~7.5°.
The gate is arithmetic, not taste.

### 6.2 Widening the fact set

`EMITTED_VARGAS` grows from 6 to the policy-selected set for the routed domain.
Vargas are emitted **per request**, not all-at-once: `varga_occupies` for 16
vargas × 9 grahas is 144 extra atoms and most are never matched. `varga_select`
runs before `koonji_retrieve` precisely so the fact set is compiled once, with
the right vargas in it.

---

## 7. §8 — Dasha & time engine

New `rishivan/timing/`. Vimshottari only, made extremely reliable, exactly as
the blueprint orders.

### 7.1 The five windows

```python
@dataclass(frozen=True, slots=True)
class EventWindow:
    promise: bool                # is the natal promise present at all
    promise_basis: tuple[str, ...]   # rule ids establishing it
    activation: DateRange | None     # period lord tied to the significator
    trigger: DateRange | None        # sub-period sharpening it
    peak: DateRange | None           # innermost level + transit corroboration
    fading: DateRange | None         # the tail
    confidence: float
    reasons: tuple[str, ...]
```

**`promise=False` short-circuits everything.** A timing question about an event
the chart does not promise has no answer worth computing, and producing a window
anyway is the single most common way an astrology product invents a prediction.
This is a hard gate in `dasha_windows`, not a low score.

### 7.2 Activation mapping

`activation.py` answers: *what does this period activate?* For a period lord `L`:

- houses `L` owns, occupies, and aspects
- yogas `L` participates in (from `ChartState`)
- natural karakas `L` carries
- nakshatra dispositorship — `L` as lord of the nakshatra another graha occupies

That mapping is what makes a period relevant to a *domain*, and it is what the
Kala Rishi reasons over.

### 7.3 Arbitrary date-time queries

`query.py`: `periods_at(chart, when, levels=3)` and
`windows_between(chart, start, end)`. Both pure, both cached on
`(chart_digest, when)`. Exact start/end are already stored by `chart/dasha.py`;
this layer must not re-derive them.

### 7.4 Multiple systems, unblended

`TimingReport.by_system: dict[str, EventWindow]`. Chara Dasha, when it arrives,
is a **second independent opinion** and is reported as such. Averaging two dasha
systems produces a number that no tradition endorses and no reviewer can check.

---

## 8. §12 — Event-specific evidence hierarchies

`rishivan/council/domains/hierarchy.py`. Declarative (C4), seeded verbatim from
the blueprint's table.

```python
@dataclass(frozen=True, slots=True)
class EvidenceHierarchy:
    domain: str
    houses: tuple[int, ...]              # in priority order
    lords: tuple[int, ...]
    karakas: tuple[str, ...]
    vargas: tuple[str, ...]
    jaimini: tuple[str, ...]             # upapada, darakaraka, …
    requires_dasha: bool
    requires_transit: bool
    min_independent_sources: int
    tier_weights: dict[str, float]       # house=1.0, varga=0.6, transit=0.3
```

Seeded rows, from the table: marriage (7th/7L, Venus/Jupiter, D9, Upapada,
Darakaraka) · career (10th/10L, 6/7/11, D10, Amatyakaraka) · business
(2/7/10/11, D10) · wealth (2/5/9/11, D2, Dhana yogas) · property (4th/4L, D4) ·
education (4/5/9, Mercury/Jupiter, D24) · children (5th/5L, Jupiter, D7) ·
relocation (4/9/12, Rahu, D4) · spirituality (5/9/12, Jupiter/Ketu, D20,
Atmakaraka) · major transition (event signature + dasha + transit +
**independent** corroboration).

**How it plugs into Koonji:** the hierarchy produces (a) the `domains` filter
already accepted by `index.query`, (b) the varga set for `varga_select`, and
(c) `tier_weights` handed to `evidence.build_evidence` so a D1 house placement
outranks a D9 confirmation. Today every firing is weighted the same way for
every question — that is the "one generic scoring formula" the blueprint
rejects.

---

## 9. §11 — The eight Rishis as reasoning roles

`rishivan/council/rishis/`. Eight nodes, one contract.

**The existing eight personas are a different taxonomy and are not renamed.**
`agam/vyom/dhruvan/…` are voices for the RAG demo; these eight are analytical
roles. A mapping table relates them; neither is deleted. Renaming would silently
change what the demo's `rishi_affinity` annotations mean.

| Node | Role | Reads | Rules it may retrieve |
|---|---|---|---|
| `parashara` | houses, lordships, yogas, vargas, Vimshottari | full state | `school.parashari` |
| `jaimini` | karakas, arudhas, Jaimini aspects, Chara Dasha | full state | `school.jaimini` |
| `nakshatra` | pada, dispositor chains, lunar framework | full state | nakshatra-tagged |
| `kala` | dashas, sub-periods, transits, windows | state + `timing` | timing-tagged |
| `karma` | dharma, vocation, 5/9/10, karakas | state + hierarchy | domain.career/spiritual |
| `artha` | wealth, income, business, assets | state + hierarchy | domain.wealth/property |
| `jeevana` | marriage, family, children, relocation | state + hierarchy | domain.relationship/progeny/travel |
| `sakshi` | **adversarial auditor** | everything, **plus the seven reports** | — |

Rishi names will be same as agam, vyom, ritam,....

### 9.1 The contract — the nine protocol steps, typed

```python
class RishiReport(BaseModel):
    rishi: str
    domain: str
    supporting: list[EvidenceItem]      # step 4
    weakening: list[EvidenceItem]       # step 5
    assumptions: list[str]              # step 6
    would_change_my_mind: list[str]     # step 7
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_reasons: list[str]       # step 8
    abstained: str = ""                 # why, if it declined

class EvidenceItem(BaseModel):
    statement: str
    rule_ids: list[str]                 # every item traces to Koonji
    chart_basis: list[str]              # atoms/diagnoses it rests on
    weight: float
    tier: str                           # house | varga | dasha | transit | jaimini
```

**`weakening` is required, not optional.** A report with supporting evidence and
an empty `weakening` list is rejected by the contract validator unless
`abstained` is set. Every product on the market suppresses disconfirming signal
because it makes the answer messier; including it is the entire credibility play.

### 9.2 Which Rishis run

`route_rishis` uses LangGraph's `Send` API to fan out only to Rishis the
evidence justifies:

- always: the domain Rishi for the routed domain (karma/artha/jeevana)
- always: `parashara` (primary classical synthesis)
- `kala` iff the question has a timing component (`spec.mode` is timing, or the
  payload carries a `time_scope`)
- `jaimini` iff the hierarchy names Jaimini factors **and** the bundle holds
  `school.jaimini` rules that fired
- `nakshatra` iff nakshatra-tagged rules fired
- `sakshi` always, and always last

**The router proposes; the evidence graph disposes.** Invoking a Rishi whose
subgraph is empty spends tokens to produce nothing, and worse, produces
confident-sounding filler because a model asked for an opinion supplies one.

### 9.3 Sakshi and the bounded re-examination

`sakshi` receives all seven reports and hunts for: missing evidence a hierarchy
required, cancellations the VM found that no Rishi mentioned, contradictions
between reports, timing asserted without a dasha, claims exceeding
`min_independent_sources`, and alternative explanations.

`route_after_sakshi` → `re_examine` **at most once** (`state["revisions"] < 1`),
then forward regardless. An unbounded critic loop is how a graph hangs in
production at 3 a.m.

---

## 10. Where the conditionals go

The 564-line `council_consult` becomes nodes plus five named routers. Every
existing branch has a destination; nothing is dropped.

| Today, inline in `council_consult` | Becomes |
|---|---|
| `if classification.is_smalltalk_or_gibberish` | `route_after_intake → non_analytic` |
| `if domain == NATAL and birth_data is None` | `route_after_intake → need_input` |
| `if mentions_panchang(question)` | `panchang` node, reached by `route_after_chart` |
| `if domain in (MUHURTA, PRASHNA)` | `route_after_intake` → mode subgraph |
| `if intent == "chart"` + chart_type branches | `chart_render` node + `route_chart_kind` |
| `if dasha_level != "none"` | folded into `dasha_windows` |
| `if rishi == "tejan"` remedy augmentation | `remedy` node, conditional edge |
| extra-varga fetch loop | `varga_select` |
| Qdrant filter fallback | `retrieve_passages` node, internal retry |

**Test discipline:** each router is a pure function `State → str` (or
`list[Send]`) and gets its own table-driven test. That is the payoff — those
branches are currently untestable without running the whole pipeline.

---

## 11. Cross-cutting

**Streaming.** `narrate` is the only streaming node. The graph is driven with
`astream_events(version="v2")` and the transport filters to
`on_chat_model_stream` from that node. Everything before it is fast and
deterministic; first token lands after the deterministic phase completes.

**Checkpointing.** `MemorySaver` for the Streamlit demo, `AsyncPostgresSaver`
for the backend, behind `checkpointer_for(env)`. Thread id = conversation id, so
`turn_type: followup` resumes rather than recomputes.

**Determinism.** Everything up to `fan_out_rishis` must be reproducible from
`(chart_digest, bundle_id, registry_fingerprint, spec)`. A test asserts two runs
of the deterministic prefix produce identical `reading` and `chart_state`.

**Cost.** Deterministic phase: 0 model calls. Rishi fan-out: 3–8 calls,
parallel. Sakshi: 1. Synthesis + narrate: 2. Budget ceiling per run, enforced as
in `koonji/client.py`.

**Failure.** Every model node has a deterministic fallback: a Rishi that times
out returns `abstained="timeout"`, and synthesis proceeds with fewer reports and
says so. `narrate` falling back to a template rendered from `AnswerPlan` is
possible *only* because the evidence is structured — which is the argument for
this whole architecture in one sentence.

---

## 12. Phases

Five plans, in dependency order. Each ends with working, testable software.

| # | Plan | Delivers | Depends on |
|---|---|---|---|
| **1** | LangGraph skeleton | Graph replaces `council_consult`, **behaviour-preserving**. State schema, node/edge split, routers tested, streaming and checkpointing intact. No new astrology. | — |
| **2** | Chart state (§6) | `ChartState`, functional-nature derivation rules, dispositor chains, strength interface, yoga detection via the VM. Node between chart and retrieval. | 1 |
| **3** | Varga + timing (§7, §8) | `VargaPolicy` registry, birth-confidence gate, per-request varga emission; five-window timing, activation mapping, arbitrary-datetime queries. | 2 |
| **4** | Hierarchies + council (§12, §11) | Evidence hierarchy table wired into retrieval and weighting; eight Rishi nodes, `RishiReport` contract, `Send` fan-out, Sakshi with bounded re-examination. | 3 |
| **5** | Answer plan + ledger | `AllowedClaims` gate, streaming critic, trace persistence, prediction ledger, consistency directive on follow-ups. | 4 |

**Phase 1 first, deliberately.** Building §6–§12 against the current procedural
orchestrator means porting all of it twice. The skeleton is behaviour-preserving,
so it is reviewable against the existing outputs — the only phase where that
check is available.

---

## 13. Open decisions

Four things this spec does not settle, each needing a call before its phase:

1. **Which Shadbala.** Full six-fold Parashari, or Sthana+Dig+Kaala with
   `is_estimated=True`? Affects Phase 2. Recommendation: ship estimated, band
   only, and gate the scalar behind validation against a published reference set.
2. **Lagna framework for functional nature.** Parashari standard
   (kendra/trikona lordship) is assumed. Lal Kitab and some lineages differ, and
   the registry namespaces them — but the *default* is a doctrinal choice a
   reviewer must sign.
3. **`min_independent_sources` enforcement point.** In the hierarchy (per
   domain) or in `evidence.py` (per claim)? Recommendation: hierarchy sets it,
   `evidence.py` enforces it, so the existing corroboration machinery is reused.
4. **Whether Rishis retrieve or receive.** This spec has them *receive* a - another rishi will answer when some facts required to answer that quwstion comes under his domain.
   pre-built evidence subgraph. The alternative — each Rishi calls
   `index.query` itself — is more flexible and much harder to keep deterministic.
   Recommendation: receive, for Phase 4; revisit only with a measured need.
