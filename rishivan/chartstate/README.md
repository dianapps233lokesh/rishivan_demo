# Chart state — the diagnosis before the prose

Blueprint §6: *"The engine should produce a chart state before it produces any
prose prediction."* This is that.

```
Chart ──┬─→ koonji/facts.py  → flat interned atoms   → retrieval
        └─→ chartstate/      → structured diagnosis  → reasoning
```

Two derivations of one chart, on purpose. A `FactSet` answers *does this chart
satisfy this predicate* in constant time and is unreadable. A `ChartState`
answers *what is going on with Saturn* and carries the reasons — which is what a
Rishi argues from and a reviewer checks. Five tests in `test_build.py` assert the
two never disagree, because separate code paths drift.

## Modules

| File | Produces |
|---|---|
| `types.py` | `Band`, `StrengthReading`, `PlanetDiagnosis`, `HouseDiagnosis`, `ChartState` — all frozen |
| `dispositor.py` | dispositor and nakshatra-lord chains, cycle-safe |
| `functional.py` | functional benefic/malefic under a named lagna framework |
| `strength.py` | partial strength, marked estimated |
| `build.py` | assembly, and the calculation-drift digest |

Everything is pure and deterministic. The same chart produces a byte-identical
diagnosis, or a trace cannot be replayed and the digest means nothing.

## Three decisions worth knowing

**Chains detect cycles rather than assuming termination.** Mutual disposition —
Sun in Cancer with Moon in Leo — is a 2-cycle. A walker without a visited set
does not fail, it *hangs*: no error, no answer, a request that never returns.
`Chain` carries `cycle: bool` and returns the ring, because parivartana is a real
configuration and the caller decides what it means.

**Strength is estimated, and says so in every reading.** Full six-fold Shadbala
needs ephemeris work this codebase does not do — Chesta wants true velocity
relative to the Sun, Kaala wants a dozen day/night and paksha terms. Three of six
called "Shadbala" would be worse than useless. So `StrengthReading` carries
`system="parashari.partial.v1"`, `is_estimated=True`, and itemised `components`,
and **`claimable_value` returns `None` while estimated**. The band survives
estimation; the number does not. That matters because everything downstream
weights by strength — the evidence graph, Phase 4's hierarchies, any Rishi that
says "weak" — and a confidently wrong number propagates into all of them
invisibly.

**Functional nature is code, not a Koonji rule — and that is a compromise.** The
architecture spec argued it should be sourced `DERIVE_FACT` rules, and in
principle that is right: lineages disagree, so it wants a citation and a version.
But the ingested corpus holds only *lagna-specific* commentary (Bhavartha
Ratnakara ch1, on Mesha lagna's 10th/11th lord), not a general statement of the
kendra/trikona doctrine. Generalising those verses into a universal rule is
exactly the scope inflation `koonji.validate.check_scope_inflation` exists to
catch.

So the Koonji `functional_nature` predicate **stays `derived=True` and
unsatisfied**, and rules resting on it still evaluate INDETERMINATE. That is a
corpus-acquisition blocker, not an engineering one: it needs a BPHS yogakaraka
verse the bridge has not produced.

## The doctrine, stated

Parashari standard, namespaced as `"parashari"` so another lineage is additive:

- kendras 1/4/7/10 · trikonas 1/5/9 · dusthanas 6/8/12
- a trikona lord is benefic; a lord of 3/6/11 is malefic
- a **natural benefic** owning a kendra is blemished (kendradhipatya dosha); a
  natural malefic owning one is not. That asymmetry is the part people get wrong
  and the part that changes readings.
- owning both a kendra **and** a trikona — two different houses, not the 1st
  counted twice — is yogakaraka
- Rahu and Ketu own no sign, so they inherit their dispositor's verdict

Kendradhipatya is recorded as `neutral` plus a `kendradhipatya_dosha` flag, not
as `malefic`. Authorities differ — many call Mercury an outright functional
malefic for Pisces lagna, owning 4 and 7 — and this is the conservative reading.
The flag lets a policy layer take the stronger line without this module picking a
side it cannot cite.

Two more approximations, named rather than hidden: Mercury and the Moon are
treated as unconditional natural benefics (Mercury takes its associates' colour
and a waning Moon is malefic in the full doctrine), and the 8th/12th lordships
are handled as a weakening note rather than in `MALEFIC_LORDSHIPS`.

## Two fields ship empty

Declared so later phases add a value rather than migrating the type.

| Field | Filled by | Why not now |
|---|---|---|
| `PlanetDiagnosis.yogas` | Phase 4 | A yoga *is* a fired rule here, and the engine runs after this node |
| `HouseDiagnosis.transit_active` | Phase 3 | Needs the transit windows |

## Using it

```python
from rishivan.chartstate.build import build_chart_state

state = build_chart_state(chart, when=query_time)
saturn = state.planet("graha.saturn")
print(saturn.functional_nature, "—", saturn.functional_reason)
print(state.house(10).benefic_influence, state.house(10).influence_reason)
```

In the graph it is the `chart_state` node, between every chart node and
`ground`. `rishivan/graph/README.md` has the topology.
