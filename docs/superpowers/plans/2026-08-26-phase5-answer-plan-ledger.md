# Phase 5 — The Answer Plan, the Ledger, and Getting the Generator Out of State

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nothing reaches the reader that the evidence did not license. Every
dated prediction is written down where it can later be scored. And the graph
becomes checkpointable, which it has never been.

**Architecture:** A deterministic `AnswerPlan` is the last thing the graph
produces. Narration moves *outside* the graph, into the adapter — which is what
removes the live generator from state and unblocks checkpointing as a side
effect rather than as a separate project.

**Tech Stack:** existing `koonji/engine.Engine.trace` (the audit chain already
exists) · `koonji/evidence.BANDS` · `council/rishis/` (Phase 4) · LangGraph
`MemorySaver`/`PostgresSaver`.

**Spec:** `docs/superpowers/specs/2026-08-25-chart-understanding-council-architecture.md` §3 (topology: `answer_plan → narrate → persist`), §4 (state), §11 (failure/fallback)

## Global Constraints

- **The graph must end msgpack-serialisable.** That is the whole structural
  change. A single generator, open file handle, or live client left in state
  puts checkpointing back where it was.
- **Every key a node returns must be declared in `RishivanState`.** LangGraph
  discards writes to undeclared channels silently. `test_integration.py`'s AST
  walk catches it; do not rely on noticing.
- **`council_consult`'s signature and `RESULT_KEYS` do not change.**
  `streamlit_app.py` and `tests/eval/run_eval.py` call it, and
  `answer_stream` must still be a generator of text chunks. A refactor that
  also moves its callers cannot be reviewed against the behaviour it preserves.
- **The gate is on the prompt, not on the output.** See "The honest limit"
  below — do not let a task drift into pretending otherwise.
- **A dated prediction without a window is not written to the ledger.** A ledger
  of unfalsifiable statements scores nothing and reads as rigour.
- **Determinism.** `build_answer_plan` takes no client and reads no clock.
- Test runner: `./.venv/bin/python -m pytest`. The untracked root `tests.py`
  shadows the `tests/` package — move it aside for full-suite runs.

---

## What exists, measured

| Capability | State |
|---|---|
| Koonji audit chain | `Engine.trace(reading)` — rules considered, fired, cancelled by what, indeterminate and why, with verses |
| Confidence bands and phrasing | `evidence.BANDS` — 4 bands, each with the language it licenses |
| Structured Rishi reports | `RishiReport` (Phase 4) — supporting, weakening, assumptions, confidence with reasons |
| Auditor findings | `Audit` (Phase 4) — six mechanical, one model |
| Five-stage windows | `EventWindow` (Phase 3) — with `promise_basis` |
| Conversation transcript | `council/conversation.py` — capped, in-memory, prose only |
| `state["trace"]` | **declared, never written** |
| `AnswerPlan` | **ABSENT** |
| Prediction ledger | **ABSENT** |
| Checkpointing | **available and deliberately unwired** — `test_parity.py` pins `TypeError: not msgpack serializable` |
| Anything gating what the narrative may claim | **ABSENT** — the prompt asks; nothing checks |

## The design problem, and the honest limit

**A "streaming critic" that retracts already-emitted tokens does not exist.**
Once a chunk has been yielded to the transport it is on the reader's screen. Any
plan promising a guardrail there is promising something the transport cannot do.

So the discipline splits into three things that are each real, and they should
be named separately rather than blurred into one word:

1. **The gate** is on the *prompt*. `AllowedClaims` is the exhaustive list of
   statements the narrative may make, each with its citation and the phrasing
   band its confidence licenses. Anything absent from it is absent from the
   prompt, and a model cannot cite what it was never shown.
2. **The verifier** runs on the *emitted* text and records violations into the
   trace. It is a measurement, not a guardrail — it tells you the gate leaked,
   after the fact, in a form you can act on next release. It also fails the eval
   harness loudly, which is where it earns its keep.
3. **The fallback** renders prose from the `AnswerPlan` deterministically when
   the model fails. This is possible *only* because the evidence is structured,
   and it is the single strongest argument for the whole architecture.

**And the structural change that makes checkpointing work.** The graph currently
ends by putting a live generator in `state["answer_stream"]`. Nothing can
serialise that. Moving narration into `council_consult` — after `graph.invoke`
returns — means the graph's final state is plain data, and the same
`checkpointer_for()` that has been sitting unused starts working. The caller
contract is unchanged: the adapter still returns `answer_stream`, it just builds
it one layer out.

```
before:  … → synthesis → answer(builds generator into state) → END
after:   … → synthesis → answer_plan → persist → END
         council_consult: invoke → narrate(plan) → answer_stream
```

---

### Task 1: `AnswerPlan` and `AllowedClaims`

**Files:** Create `rishivan/council/answer_plan.py` · Test `tests/council/test_answer_plan.py`

**Interfaces:**
- Consumes: `koonji.evidence.Claim`, `RishiReport`, `Audit`, `EventWindow`, `VargaSelection`
- Produces: `AllowedClaim`, `AnswerPlan`, `PHRASING_BY_BAND`, `build_answer_plan(...) -> AnswerPlan`

```python
@dataclass(frozen=True, slots=True)
class AllowedClaim:
    claim_id: str
    statement: str
    band: str                    # evidence.BANDS
    phrasing: str                # the language this band licenses
    confidence: float
    citations: tuple[str, ...]
    rule_ids: tuple[str, ...]
    tier: str
    counter: tuple[str, ...]     # what argues against, never dropped
    corroborated: bool
    window: str = ""             # only when a dasha window supports a date

@dataclass(frozen=True, slots=True)
class AnswerPlan:
    question: str
    domain: str
    allowed: tuple[AllowedClaim, ...]
    must_say: tuple[str, ...]    # withheld vargas, unreviewed rules, abstentions
    must_not_say: tuple[str, ...]
    disagreement: str
    insufficient: bool
    unreviewed: bool
```

**`must_not_say` is not decoration.** It carries the specific over-claims this
run is at risk of: a date when no window exists, a certainty word when the top
band is `some_indications`, a cancelled yoga named as intact.

- [ ] **Step 1: Write the failing test**

```python
def test_a_claim_below_the_evidence_floor_is_not_allowed(reading):
    """`INSUFFICIENT_BELOW` is the line. A 0.2-confidence claim may be
    reported as a faint indication; it may not be a claim the prose asserts."""
    plan = build_answer_plan(question="q", domain="domain.wealth",
                             reading=_thin_reading(), reports=[], audit=None,
                             timing=None, vargas=None)
    assert plan.allowed == ()
    assert plan.insufficient


def test_an_allowed_claim_carries_the_phrasing_its_band_licenses():
    claim = _allowed(confidence=0.5)
    assert claim.phrasing == "some indications suggest"


def test_a_certainty_word_is_never_licensed():
    for band, _, phrasing in BANDS:
        assert "will definitely" not in phrasing
        assert "guaranteed" not in phrasing


def test_counter_evidence_is_carried_on_the_claim_not_dropped(reading):
    """The half every product drops. If it survives the evidence graph and
    dies here, it has been dropped."""
    plan = build_answer_plan(...)
    assert any(c.counter for c in plan.allowed)


def test_a_date_is_only_allowed_when_a_window_supports_it(reading):
    without = build_answer_plan(..., timing=None)
    assert all(not c.window for c in without.allowed)
    assert any("date" in m for m in without.must_not_say)


def test_an_uncorroborated_claim_is_marked_not_deleted(reading):
    plan = build_answer_plan(...)
    weak = [c for c in plan.allowed if not c.corroborated]
    assert weak  # present, and the phrasing is the quiet band


def test_withheld_vargas_become_something_that_must_be_said(vargas):
    plan = build_answer_plan(..., vargas=vargas)
    assert any("D60" in m for m in plan.must_say)


def test_a_wholly_abstaining_council_is_insufficient(reading):
    plan = build_answer_plan(..., reports=[_abstained(), _abstained()])
    assert plan.insufficient


def test_the_council_disagreement_survives():
    plan = build_answer_plan(..., reports=[_report(0.7), _report(-0.6)])
    assert plan.disagreement
    assert "average" in plan.disagreement.lower()


def test_the_plan_is_deterministic():
    assert build_answer_plan(**kw) == build_answer_plan(**kw)


def test_the_builder_takes_no_client_and_reads_no_clock():
    src = inspect.getsource(build_answer_plan)
    assert "client" not in inspect.signature(build_answer_plan).parameters
    assert "datetime.now" not in src


def test_the_plan_is_serialisable():
    """The whole structural point of the phase."""
    import msgpack
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    JsonPlusSerializer().dumps_typed(plan)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `./.venv/bin/python -m pytest tests/council/test_answer_plan.py -q`
Expected: `ModuleNotFoundError: No module named 'rishivan.council.answer_plan'`

- [ ] **Step 3: Implement**

`build_answer_plan` walks `reading.claims`, keeps those at or above
`INSUFFICIENT_BELOW`, and attaches: the band's phrasing verbatim from
`evidence.BANDS`, the claim's citations, the rule ids, the weakest tier among
its supports, and its counter-evidence. A claim whose supporting Rishi report
named a window gets `window`; every other claim gets `""` and the plan gains a
`must_not_say` entry naming dates.

`must_say` is assembled from: withheld vargas with their reasons, the unreviewed
provenance, Rishi abstentions, and unmet corroboration.

- [ ] **Step 4: Run the tests** · **Step 5: Commit**

```bash
git commit -m "feat(council): the exhaustive list of what may be said"
```

---

### Task 2: The `answer_plan` node

**Files:** Create `rishivan/graph/nodes/answer_plan.py` · Modify `rishivan/graph/state.py`, `build.py` · Test `tests/graph/test_nodes_answer_plan.py`

**Interfaces:**
- Produces: `answer_plan_node(state) -> dict` writing `answer_plan`

Deterministic, no client. Sits where `answer` currently sits; `answer` moves out
of the graph in Task 3, so this task leaves both in place and the graph running
green with the plan computed but unused. That is deliberate — Task 2 must be
independently reviewable.

- [ ] **Step 1: Write the failing test**

```python
def test_the_node_produces_a_plan(served_state):
    assert answer_plan_node(served_state)["answer_plan"] is not None


def test_no_reading_still_produces_a_plan(chartless):
    """A general question has no rules and still gets an answer. A None plan
    downstream is indistinguishable from a crash."""
    plan = answer_plan_node(chartless)["answer_plan"]
    assert plan is not None and plan.insufficient


def test_the_node_makes_no_model_call():
    assert "client" not in inspect.signature(answer_plan_node).parameters


def test_every_key_returned_is_declared_in_the_state(served_state):
    assert set(answer_plan_node(served_state)) <= set(RishivanState.__annotations__)


def test_the_plan_reaches_the_end_of_the_graph(served):
    final, _ = served
    assert final["answer_plan"] is not None
```

- [ ] **Step 2: Run and fail** · **Step 3: Implement** · **Step 4: Run** · **Step 5: Commit**

---

### Task 3: Narration leaves the graph

**Files:** Create `rishivan/council/narrate.py` · Modify `rishivan/graph/nodes/answer.py`, `build.py`, `rishivan/council/orchestrator.py` · Test `tests/council/test_narrate.py`, `tests/graph/test_adapter.py`

**Interfaces:**
- Produces: `stream_answer(plan, *, client, state) -> Generator[str, None, None]`, `render_template(plan) -> str`

**This is the structural change.** The graph stops at `persist`; the adapter
builds the stream. `RESULT_KEYS` is unchanged and `answer_stream` is still a
generator of text chunks — the contract test in `test_adapter.py` is the gate.

- [ ] **Step 1: Write the failing test**

```python
def test_the_adapter_still_returns_a_stream(result):
    assert "".join(result["answer_stream"]).strip()


def test_the_graph_no_longer_puts_a_generator_in_state(final):
    """The reason the whole phase exists."""
    assert not isinstance(final.get("answer_stream"), types.GeneratorType)


def test_the_prompt_contains_only_allowed_claims(recording_client):
    stream_answer(plan, client=recording_client, state=state)
    prompt = recording_client.prompts[0]
    for claim in plan.allowed:
        assert claim.statement[:30] in prompt
    assert "wealth.loss" not in prompt          # a claim below the floor


def test_the_prompt_carries_the_phrasing_each_claim_licenses(recording_client):
    assert "some indications suggest" in recording_client.prompts[0]


def test_the_prompt_carries_what_must_be_said(recording_client):
    assert all(m[:20] in recording_client.prompts[0] for m in plan.must_say)


def test_the_prompt_carries_what_must_not_be_said(recording_client):
    assert "must not" in recording_client.prompts[0].lower()


def test_a_model_failure_falls_back_to_the_template(failing_client):
    """Possible only because the evidence is structured — which is the whole
    architecture in one test."""
    text = "".join(stream_answer(plan, client=failing_client, state=state))
    assert text.strip()
    assert plan.allowed[0].citations[0] in text


def test_the_template_cites_every_claim_it_states():
    text = render_template(plan)
    for claim in plan.allowed:
        assert any(c in text for c in claim.citations)


def test_the_template_states_the_counter_evidence():
    assert "against" in render_template(plan).lower()


def test_an_insufficient_plan_declines_rather_than_composing():
    text = "".join(stream_answer(_insufficient_plan(), client=..., state=...))
    assert "don't have" in text or "silent" in text
```

- [ ] **Step 2: Run and fail** · **Step 3: Implement**

`answer_node` becomes `answer_plan_node`'s neighbour and is deleted; `build.py`
routes `synthesis → answer_plan → persist → END` and
`insufficient → persist → END`. `orchestrator.council_consult` gains:

```python
    result["answer_stream"] = (
        None if final["outcome"] == "insufficient"
        else narrate.stream_answer(final["answer_plan"], client=client, state=final)
    )
```

`answer_stream=None` on the insufficient path is preserved exactly —
`streamlit_app` renders its own warning for that case, and changing it is a
product decision this phase does not own.

- [ ] **Step 4: Run the tests**

Run: `./.venv/bin/python -m pytest tests/graph/ tests/council/ -q`

- [ ] **Step 5: Commit**

---

### Task 4: Checkpointing, unblocked

**Files:** Modify `rishivan/council/orchestrator.py`, `rishivan/graph/build.py` · Test `tests/graph/test_parity.py`, `tests/graph/test_checkpointing.py`

The pin in `test_parity.py::test_a_generator_in_state_cannot_be_checkpointed`
asserts a `TypeError`. **Invert it.** That test was written to record a
constraint so it would not be rediscovered; discharging it is the deliverable.

- [ ] **Step 1: Write the failing test**

```python
def test_the_state_is_now_checkpointable(monkeypatch):
    """Inverted from `test_a_generator_in_state_cannot_be_checkpointed`,
    which existed to record this constraint until Phase 5 removed it."""
    graph = build_graph(store=..., client=..., checkpointer=checkpointer_for("demo"))
    final = graph.invoke(initial_state("will I be wealthy?", birth_data=BIRTH),
                         config={"configurable": {"thread_id": "c1"}})
    assert final["outcome"] == "served"


def test_a_second_turn_on_the_same_thread_resumes():
    ...


def test_the_thread_id_is_the_conversation_id():
    ...


def test_every_value_in_the_final_state_is_serialisable(final):
    """One live object anywhere puts this phase back where it started."""
    JsonPlusSerializer().dumps_typed(final)
```

- [ ] **Step 2: Run and fail** · **Step 3: Wire the checkpointer into `council_consult`**

Behind a parameter (`thread_id: str | None = None`) so a caller that does not
pass one gets today's behaviour exactly. `streamlit_app` passing its session id
is a one-line change and belongs in this task, not a later one.

- [ ] **Step 4: Run** · **Step 5: Commit**

---

### Task 5: The claim verifier

**Files:** Create `rishivan/council/verify.py` · Modify `rishivan/council/narrate.py` · Test `tests/council/test_verify.py`

**Interfaces:** `Violation`, `verify_answer(text, plan) -> list[Violation]`

A measurement, not a guardrail — see "The honest limit". It runs on the
accumulated text once the stream closes, records violations into the trace, and
raises in the eval harness where a loud failure is what you want.

Four checks, each mechanical:

| check | how |
|---|---|
| `uncited_date` | a year or month-year in the prose with no `window` on any allowed claim |
| `overclaimed_band` | certainty language when the top allowed band is below `strongly_indicated` |
| `unlicensed_claim` | a claim id's subject asserted that is not in `allowed` |
| `suppressed_counter` | an allowed claim with counter-evidence, stated with none of it |

- [ ] **Step 1: Write the failing test**

```python
def test_a_date_with_no_window_behind_it_is_a_violation():
    assert any(v.kind == "uncited_date"
               for v in verify_answer("You will marry in 2028.", _plan_without_window()))


def test_a_date_with_a_window_is_not_a_violation():
    assert not verify_answer("The window opens in 2028.", _plan_with_window())


def test_certainty_language_over_a_weak_band_is_a_violation():
    assert any(v.kind == "overclaimed_band"
               for v in verify_answer("This will definitely happen.", _weak_plan()))


def test_suppressed_counter_evidence_is_a_violation():
    ...


def test_a_faithful_answer_produces_no_violations():
    """The check that stops the verifier becoming noise."""
    assert verify_answer(render_template(plan), plan) == []


def test_the_template_fallback_never_violates_its_own_plan():
    """It is generated FROM the plan. If it can violate it, the plan is not
    the thing it is generated from."""
    for plan in _many_plans():
        assert verify_answer(render_template(plan), plan) == []


def test_the_verifier_reads_no_clock_and_calls_no_model():
    ...
```

`test_the_template_fallback_never_violates_its_own_plan` is the strongest test
in the phase: it closes the loop between the two halves.

- [ ] **Step 2: Run and fail** · **Step 3: Implement** · **Step 4: Run** · **Step 5: Commit**

---

### Task 6: The prediction ledger

**Files:** Create `rishivan/council/ledger.py` · Test `tests/council/test_ledger.py`

**Interfaces:** `Prediction`, `Ledger`, `predictions_from(plan, *, run_id, asked_at) -> list[Prediction]`, `Ledger.append/open_at/due_before`

**The falsifiability play, and the reason it is small.** A prediction is only
written when it has *both* a claim above the floor *and* a dasha window to land
in. A ledger of unfalsifiable statements scores nothing and reads as rigour,
which is worse than not having one.

```python
@dataclass(frozen=True, slots=True)
class Prediction:
    prediction_id: str        # content hash: run + claim + window
    run_id: str
    asked_at: str             # ISO; passed in, never read from the clock
    claim_id: str
    statement: str
    domain: str
    window_start: str
    window_end: str
    confidence: float
    band: str
    citations: tuple[str, ...]
    rule_ids: tuple[str, ...]
    outcome: str = "open"     # open | occurred | did_not_occur | unresolvable
    resolved_at: str = ""
    note: str = ""
```

- [ ] **Step 1: Write the failing test**

```python
def test_a_claim_without_a_window_is_not_a_prediction():
    """Unfalsifiable. A ledger full of these scores nothing and reads as
    rigour, which is worse than not keeping one."""
    assert predictions_from(_plan_without_window(), run_id="r", asked_at=T) == []


def test_a_claim_with_a_window_becomes_a_prediction():
    assert predictions_from(_plan_with_window(), run_id="r", asked_at=T)


def test_a_prediction_carries_the_verses_behind_it():
    p = predictions_from(...)[0]
    assert p.citations and p.rule_ids


def test_the_same_run_and_claim_produce_the_same_id():
    """Content-addressed, so replaying a run cannot double-count it."""
    assert predictions_from(...)[0].prediction_id == predictions_from(...)[0].prediction_id


def test_two_different_claims_produce_different_ids():
    ...


def test_appending_the_same_prediction_twice_stores_one(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append(p); ledger.append(p)
    assert len(ledger.all()) == 1


def test_a_prediction_starts_open():
    assert predictions_from(...)[0].outcome == "open"


def test_resolving_a_prediction_records_when_and_why(tmp_path):
    ...


def test_due_before_finds_windows_that_have_closed(tmp_path):
    """The point of the whole file: what can be scored now."""
    ...


def test_the_ledger_never_reads_the_clock():
    """A backtest asks about 1998. A ledger that stamps `now` makes every
    replayed run look like it was predicted today."""
    assert "datetime.now" not in inspect.getsource(ledger_module)


def test_a_corrupt_line_does_not_take_down_the_ledger(tmp_path):
    """JSONL on disk. One bad append must cost one record."""
    ...
```

- [ ] **Step 2: Run and fail** · **Step 3: Implement** · **Step 4: Run** · **Step 5: Commit**

---

### Task 7: The `persist` node — trace and ledger

**Files:** Create `rishivan/graph/nodes/persist.py` · Modify `build.py`, `state.py` · Test `tests/graph/test_nodes_persist.py`

**Interfaces:** `persist_node(state, *, sink) -> dict` writing `trace`

`Engine.trace(reading)` already produces the Koonji half of the audit chain and
is not reimplemented. This node composes it with the council half — reports,
audit, plan, convergence, withheld vargas, timing — and hands the whole thing to
a `sink`.

**The sink is injected**, defaulting to a JSONL file under a configured
directory. Streamlit Cloud has no Postgres and the demo's requirements
deliberately exclude it; a node that assumes a database is a node that fails in
the one environment this repo actually ships to.

- [ ] **Step 1: Write the failing test**

```python
def test_the_trace_carries_the_koonji_audit_chain(served_state):
    trace = persist_node(served_state, sink=_null)["trace"]
    assert trace["koonji"]["firings"]
    assert trace["koonji"]["bundle_id"]


def test_the_trace_carries_the_council(served_state):
    trace = persist_node(served_state, sink=_null)["trace"]
    assert trace["council"]["reports"]
    assert "audit" in trace["council"]


def test_the_trace_records_the_chart_digest(served_state):
    """A mismatch on recomputation means the calculation stack drifted under
    stored answers. The highest-severity alarm in the system."""
    assert persist_node(...)["trace"]["chart_digest"]


def test_the_trace_records_the_registry_fingerprint(served_state):
    """A trace that cannot say which vocabulary it was produced against is a
    trace nobody can replay."""
    ...


def test_the_trace_is_json_serialisable(served_state):
    json.dumps(persist_node(served_state, sink=_null)["trace"])


def test_a_sink_failure_does_not_fail_the_turn(served_state):
    """A full disk must not cost the reader their answer."""
    out = persist_node(served_state, sink=_raises)
    assert out["trace"]


def test_predictions_reach_the_ledger(served_state, tmp_path):
    ...


def test_no_reading_still_writes_a_trace(chartless):
    """Why a question produced no reading is exactly what a trace is for."""
    assert persist_node(chartless, sink=_null)["trace"]


def test_every_key_returned_is_declared_in_the_state(served_state):
    ...
```

- [ ] **Step 2: Run and fail** · **Step 3: Implement** · **Step 4: Run** · **Step 5: Commit**

---

### Task 8: The follow-up consistency directive

**Files:** Modify `rishivan/council/conversation.py`, `rishivan/council/narrate.py` · Test `tests/council/test_consistency.py`

**Interfaces:** `Turn.claims: tuple[str, ...]`, `consistency_instruction(convo, plan) -> str`

Turn 14 disagreeing with turn 13 about a fact is the failure a reader notices
fastest and forgives least. `Conversation` currently carries prose only, so
nothing on turn 14 can know what turn 13 asserted.

Carry the earlier turn's **allowed claim ids and their bands** — not the prose.
Prose is what the model already sees; the claim ids are what it can be held to.

- [ ] **Step 1: Write the failing test**

```python
def test_a_turn_remembers_what_it_was_allowed_to_claim():
    convo.add("q", "a", "vyom", claims=("wealth.accumulation",))
    assert convo.last.claims == ("wealth.accumulation",)


def test_a_repeated_claim_must_not_change_band():
    """The same evidence read twice must not get louder on the second
    telling."""
    text = consistency_instruction(convo, plan)
    assert "already told" in text.lower()
    assert "wealth.accumulation" in text


def test_a_claim_that_has_dropped_out_of_the_plan_is_flagged():
    """It was asserted last turn and this turn's evidence does not support
    it. Say so; do not silently stop mentioning it."""
    ...


def test_an_empty_conversation_produces_no_directive():
    assert consistency_instruction(None, plan) == ""


def test_the_directive_reaches_the_narration_prompt(recording_client):
    ...


def test_an_older_turn_is_not_carried_forever():
    """`MAX_TURNS` still bounds it. An unbounded directive is an unbounded
    prompt."""
    ...
```

- [ ] **Step 2: Run and fail** · **Step 3: Implement**

`Conversation.add` gains an optional `claims` parameter defaulting to `()`, so
every existing caller is unchanged and `streamlit_app` opts in.

- [ ] **Step 4: Run** · **Step 5: Commit**

---

### Task 9: The seam, end to end

**Files:** Modify `tests/graph/test_integration.py` · Test only

Phase 1 shipped two bugs that lived between a node and the graph, and Phase 4
found `Send` replacing rather than merging state. Both were invisible to node
tests. So the phase closes the same way: assert on what reaches the reader.

- [ ] **Step 1: Write the failing test**

```python
class TestTheAnswerIsGated:
    def test_the_narration_prompt_contains_the_allowed_claims(self, served):
        ...

    def test_a_claim_below_the_floor_never_reaches_the_prompt(self, served):
        """The gate. A model cannot cite what it was never shown."""
        ...

    def test_the_answer_verifies_against_its_own_plan(self, served):
        final, _ = served
        assert verify_answer(final["answer_text"], final["answer_plan"]) == []

    def test_the_trace_was_written(self, served):
        ...

    def test_the_state_left_the_graph_serialisable(self, served):
        ...

    def test_the_whole_turn_runs_under_a_checkpointer(self):
        ...
```

- [ ] **Step 2: Run and fail** · **Step 3: Fix whatever it finds** · **Step 4: Run the full suite**

```bash
mv tests.py /tmp/tests.py.bak && ./.venv/bin/python -m pytest -q; mv /tmp/tests.py.bak tests.py
```

- [ ] **Step 5: Commit**

---

### Task 10: Documentation

**Files:** Create `rishivan/council/README.md` · Modify `rishivan/graph/README.md`, `docs/client-spec-gap-map.md`

- [ ] Regenerate the mermaid topology from `draw_mermaid()`.
- [ ] Update the graph README's phase table — Phase 5 done; delete the
      checkpointing constraint note, which Task 4 discharges.
- [ ] Write `council/README.md`: the gate/verifier/fallback distinction in
      full, including **what the verifier cannot do**. That distinction is the
      thing most likely to be misremembered as "we validate the output".
- [ ] Gap map: §19 rows, ER §1 "Uncertainty in the answer", and BP §15
      (validation lab) — the ledger is its input, not the lab itself, and the
      row should say so rather than claiming more.
- [ ] Record what Phase 5 does **not** close: `rule.confidence` is still
      uniformly 0.5; backtest-informed confidence needs resolved ledger entries
      that do not exist yet on day one; `functional_nature` and yogas remain
      corpus-blocked.
- [ ] Commit.

---

## Self-review

**Spec coverage.** §3 topology: `answer_plan` ✓ (T2), `narrate` ✓ (T3),
`persist` ✓ (T7). §4 state: `answer_plan`, `answer`, `trace` ✓. §11 failure:
template fallback from `AnswerPlan` ✓ (T3). §12 phase row: `AllowedClaims` gate
✓ (T1/T3), streaming critic ✓ (T5, with its limit stated), trace persistence ✓
(T7), prediction ledger ✓ (T6), consistency directive ✓ (T8). Checkpointing
unblocked ✓ (T4) — named in the phase table as a consequence, and it is.

**Decisions this plan makes, for a reviewer to overturn:**

1. **Narration leaves the graph.** The alternative — keeping `answer` inside and
   teaching the checkpointer to skip one channel — makes the serialisable
   boundary a configuration detail rather than a structural fact, and it comes
   back the next time somebody puts an object in state.
2. **The verifier measures; it does not gate.** Stated plainly rather than
   engineered around, because a guardrail that cannot guard is worse than a
   measurement that is honest about being one.
3. **A prediction needs a window.** Claims without one are not written to the
   ledger at all.
4. **The sink is injected and defaults to JSONL.** Not Postgres. Streamlit
   Cloud has none and the demo's requirements exclude it.

**Risk, concentrated in Task 3.** It deletes `answer_node`, changes where the
stream is built, and touches the one function `streamlit_app` and `run_eval`
both call. `test_adapter.py`'s contract test is the gate and must pass before
Task 4 starts. Run `tests/graph/test_parity.py` after Tasks 3 and 4 rather than
at the end.

**Second risk.** `verify_answer` running on live output will find violations on
real generations — that is what it is for, but a noisy verifier gets switched
off. `test_a_faithful_answer_produces_no_violations` and
`test_the_template_fallback_never_violates_its_own_plan` are the two tests that
keep its false-positive rate honest, and they should be written first.
