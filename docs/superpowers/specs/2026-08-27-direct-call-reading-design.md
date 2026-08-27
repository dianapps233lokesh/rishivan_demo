# The direct-call reading lane

**Status:** design, approved 2026-08-27. Not implemented.
**Supersedes nothing.** This lane runs *beside* the retrieval pipeline, and the
existing one keeps working unchanged.

---

## Why

The complaint is answer quality, and it is not a retrieval bug. Three facts
about the current grounding, all measured rather than assumed:

* **Every one of the 1,117 extracted rules is `status: candidate`.** None has
  been promoted. `koonji.SERVED_STATUSES` serves candidates anyway, because the
  alternative was an honest-sounding silence caused by a deployment fact.
* **The corpus has no yoga-typed claims.** Fifteen claim-id namespaces, none of
  them `yoga.*`. `PlanetDiagnosis.yogas` is permanently empty.
* **Most questions match nothing.** `retrieve._match_rules` exists alongside
  page retrieval precisely because "the approved rule base is thin, so most
  questions still match nothing".

So a reading is grounded in whatever twenty pages came back topically similar,
plus up to ten rules if any fired. A model that has read these books in
training knows more than that, and knows it in an organised way.

The change is therefore **not** "remove retrieval". It is: stop retrieving
*documents*, and start retrieving *method* — tell the model which classical
procedure to apply, in what order, over facts that Swiss Ephemeris computed.

## Scope of this experiment

Deliberately narrow, because the purpose is a controlled comparison against
ChatGPT, Gemini and Claude in the browser. A comparison is only worth running
if the prompt can be pasted into all four places unchanged.

**In:**

* **One reading call.** No fan-out, no auditor, no second pass. Note the
  precision: `intake_node` still makes its own flash call to classify the
  question and pick the domain, so the turn costs two calls in total. Only the
  reading is single-call, and only the reading prompt is what gets pasted into a
  browser.
* `gemini-3.7-flash`, thinking **on**, `temperature=0`. Same model tier as the
  current pipeline, so what is being measured is the grounding change and the
  model's own knowledge — not a tier upgrade.
* The full assembled prompt printed to console on every call.
* No persona. The Rishi voice, the seven movements and the speech example are
  all out of this lane. Accuracy only; voice comes back later.

**Out (for now):**

* Structured analysis + separate narration (the two-call design). Better for
  quality, but a two-call pipeline cannot be pasted into a browser chat.
* The citations panel, the rules panel, the `sakshi` auditor, the prediction
  ledger's licensing checks.
* Deleting anything. Nothing in `council/`, `koonji/`, `rag/` or `knowledge/`
  is removed. If the direct lane loses on some question class, the comparison
  needs the old lane still runnable to show that.

## Topology

```
intake → chart_natal │ chart_moment → panchang → chart_state
       → hierarchy → varga_select → dasha_windows → direct_read → END
```

Skipped: `koonji_read`, `ground`, `council_routing`, `retrieve`, `fan_out`,
`rishi`, `sakshi`, `re_examine`, `synthesis`, `answer_plan`, `answer`.
Unchanged: `warmth`, all four `render_*` table paths, and every computational
node above.

`insufficient` can never fire in this lane. It means "the corpus is silent",
and there is no corpus.

### The routers are not touched

`route_after_intake` and `route_after_chart` both return the string
`"retrieve"` to mean *proceed to the reading*. The graph builder maps that
label to a node name per mode:

| label | default mode | direct mode |
|---|---|---|
| `retrieve` | `retrieve` | `direct_read` |

So the routers stay pure, and `tests/graph/test_edges.py`'s table stays valid
as written. No router edit, no test churn. A router returning a *destination*
rather than a *decision* is the thing that would have forced an edit, and this
is the cheap way out of it.

### `dasha_windows` without a reading

`dasha_windows_node` computes `promise = bool(reading and reading.promises(domain))`
and `windows_between(..., promise=promise)` yields no window when it is false.
Drop the Koonji reading and **every timing answer silently loses its window** —
the exact failure that node's docstring was written to prevent.

Resolution: the node takes `assume_promise: bool = False`, bound by
`functools.partial` in the builder, and the direct lane binds it `True`. The
arithmetic still produces the five-stage window; the prompt labels it
**computed period boundaries, not a prediction**, and the judgement about
whether the chart promises anything passes to the model.

That is the honest arrangement for this experiment. Swiss Ephemeris still owns
every date — the model is forbidden from deriving one — and the browser
platforms it is being compared against are making exactly the same judgement
call from exactly the same period boundaries.

## The prompt

Assembled by a **pure function** with no client, no network and no I/O:

```python
# rishivan/council/direct_prompt.py
def build_direct_prompt(state: RishivanState) -> str
```

Pure so that the golden-snapshot test is trivial and the no-network test is
free. The model call lives elsewhere (`council/direct.py`), which is the same
split `answer_plan` / `narrate` already uses and for the same reason.

Four blocks, in order:

### 1. Framing

Neutral and short. An expert Vedic astrologer working in the classical
tradition; names the text families it should draw on — rendered from
`constitution.source_families` for the routed domain, not hardcoded, so the
framing tracks §4-11 the way the rest of the lane does — and forbids page
numbers, chapter-and-verse citations, and
attributed quotations outright — with the panel gone there is nothing to check
a citation against, and an unverifiable citation is worse than none.

### 2. Method

Rendered from `constitution.protocol` for the routed domain. This block is the
substance of the change and the answer to "how do we invoke the model's
knowledge".

`constitution.py` already holds these, ordered, per domain. Marriage:

```
promise → spouse indicators → relationship quality → D9 confirmation
→ Jaimini indicators → yoga/affliction/modification → dasha → transit
→ cross-school timing → confidence
```

Rendered as a numbered procedure the model must work through, each step
followed by the computed facts that bear on it. `constitution.forbidden_claims`
becomes an explicit prohibition list; `blocked_concepts` and
`unavailable_sources` are **not** mentioned, because they describe gaps in
*this repo's corpus* and are meaningless to a model reading from its own
knowledge.

A general question with no routed domain falls back to Vyom's whole-chart
protocol (`chart framework → Lagna and Lagna lord → Sun and Moon → strength →
Nakshatra → major combinations → relevant Vargas → synthesis → uncertainty`).

### 3. Chart — three tiers

The failure mode to design against is dumping everything. Thirty natal facts
plus six vargas plus a full mahadasha timeline plus ashtakavarga plus
numerology buries the 7th house for a marriage question, and burying the
relevant fact is how an accurate model gives an inaccurate reading.

| Tier | Contents | Source |
|---|---|---|
| **Always** | lagna and lagna lord, Sun, Moon, birth nakshatra, running maha/antar/pratyantar, date, time, place | `_FRAMEWORK` + `derive_dasha_facts` |
| **Primary** | the constitution's `primary_houses` and `supporting_houses` with their lords, its `planets`, its `vargas` ∩ what `varga_select` chose, the computed window from `dasha_windows` | `Constitution` + `state["vargas"]` + `state["timing"]` |
| **Wider** | everything else, labelled *real, but do not lead from these* | remainder |

`coverage_facts()` already does the inside/wider split on houses and planets,
using `_SUBJECT_HOUSE` to distinguish the house a fact is *about* from the
house a planet *sits in*. This is that logic extended to vargas and the dasha
slice, in a new function — `coverage_facts` itself is left alone because the
retrieval lane still depends on its exact output.

Nothing is withheld. Every §4-11 protocol ends in whole-chart synthesis, so the
wider chart is demoted and labelled rather than dropped.

`_GROUND_TRUTH_WARNING` is reused verbatim over the fact block: copy every
clock time character for character, copy the weekday from the Date line, never
convert or re-derive a time. It is the one instruction in the current prompt
that exists because the model got it wrong in production, and none of the
reasons for it have changed.

### 4. Question and output shape

With the persona gone, something must still fix the output format or it drifts
run to run and the comparison measures noise. The shape asked for:

1. work the numbered method steps visibly, stating for each what the classical
   principle is and what this chart shows;
2. then the answer to the question actually asked;
3. then a confidence statement;
4. then the timing window, with every date copied from the facts;
5. then what would falsify the reading.

Analytical prose, not a Rishi speaking. This is more useful for grading than
the current output — when a reading is wrong you can see which step it went
wrong at.

### Conversation history

The retrieval lane threads `continuity_instruction(conversation)` into the
prompt so a follow-up like "tell me more" continues the same thread. This lane
keeps that, appended after the framing block and before the method, because
dropping it would make every follow-up answer the question as though it were
asked cold — a regression the comparison would wrongly read as a grounding
failure.

It does mean a follow-up's prompt is not cleanly pasteable, since it carries
prior turns. **Build the comparison set from first-turn questions only.** The
console dump prints whatever was actually sent, history included, rather than a
cleaned-up version of it — printing a prompt that differs from the one sent
would defeat the entire purpose of printing it.

## The model call

```python
# rishivan/council/direct.py
def stream_direct(prompt: str, *, client) -> Generator[str, None, None]
```

```python
config=types.GenerateContentConfig(
    temperature=0.0,
    thinking_config=types.ThinkingConfig(thinking_budget=-1),  # dynamic
)
```

`thinking_budget=-1` for dynamic rather than a fixed number, because the right
budget for "what colour should I wear" and "will I have children" are not the
same and the model is better placed to judge than a constant is. **Verify at
implementation** that this SDK version and `gemini-3.7-flash` accept `-1`; the
only in-repo precedent is `thinking_budget=0` in `knowledge/extract/runner.py`,
which proves the field is accepted but not that the sentinel is.

Mid-stream failure is handled the way `narrate.stream_answer` handles it: the
accumulated partial is discarded rather than left as half a sentence. There is
no template fallback in this lane — no `AnswerPlan` to render one from — so the
fallback is a plain stated failure.

### Console output

`stream_direct` prints the prompt immediately before the call, so what is
printed is provably what was sent:

```
================ DIRECT PROMPT (1,847 tokens est.) ================
<the entire prompt>
=================== END DIRECT PROMPT ===================
```

To stdout, not the logger, and not gated on `DEBUG` — the whole point is that
it is there to copy. Under Streamlit stdout lands in the terminal running the
server, which is where it is wanted.

## Wiring

`council_consult` gains `direct: bool = False`. Default preserves today's
behaviour exactly, so `tests/eval/run_eval.py` and every existing caller are
untouched.

Narration stays outside the graph, as now:

```python
if direct:
    result["answer_stream"] = direct.stream_direct(final["direct_prompt"], client=client)
else:
    result["answer_stream"] = narrate.stream_for(final, client=client)
```

`direct_read_node` writes one new state key, `direct_prompt: str`, declared in
`RishivanState` — LangGraph discards writes to undeclared channels silently,
which has shipped as a bug in this repo once already.

### UI

A sidebar toggle, passed through as `direct=`. **No panel work is needed:** the
sources strip is guarded by `if page_groups:` and the rules panel by
`if matched_rules:`, and both are empty in this lane, so both disappear on
their own. To verify, not to assume.

One new expander is worth it anyway — the assembled prompt, copyable — for when
the comparison is being run from the deployed app rather than a terminal.

### Script

```bash
python -m scripts.direct_prompt \
  --question "when will I marry?" \
  --dob 1994-03-17 --tob 04:25 --place "Jaipur, India"
```

Prints the prompt and exits. No model call, no network, no credentials. This is
the path for building the comparison set: generate N prompts, paste each into
four places, grade the four answers.

## Tests

| Test | What it pins |
|---|---|
| Golden prompt snapshot | Fixed chart + question → a checked-in prompt file. The thing that catches accidental drift while the wording is being iterated on, which it will be. |
| Scoping | A marriage question's primary tier contains the 7th lord and no ashtakavarga; a career question contains the 10th. Both assert the wider tier is present and labelled. |
| No network | `build_direct_prompt` completes with Qdrant and Postgres both unreachable. This is the actual proof the dependency is gone, and the only test that would catch a stray import re-introducing it. |
| Label mapping | In direct mode the graph reaches `direct_read` and never `retrieve`; in default mode, the reverse. |
| Timing | With `assume_promise=True` and no reading, a window is still produced. Guards the regression this design exists to avoid. |
| State declaration | `direct_prompt` is in `RishivanState`. The existing key-walker in `tests/graph/test_integration.py` covers this for free once the node exists. |
| Parity | Existing `tests/graph/test_parity.py` stays green. The old lane is untouched, and a green parity suite is what proves it. |

## What this does not answer

The comparison will show whether direct-from-knowledge beats thin retrieval. It
will not show whether **two-call** direct (structured analysis, then narration)
beats single-call — and that remains the design most likely to be right for
production, because separating "what is true" from "how it is said" is the
largest available quality lever with these models. The prompt builder here is
deliberately a pure function returning a string, so the analysis call can be
added later by changing what consumes it rather than how it is built.

The persona also comes back later. Nothing in this lane's design blocks it: the
Rishi voice becomes a narration step over this same material.

---

## Revisions, after the first real output

The lane was built, a career prompt was run through a browser platform, and the
answer it produced changed three things in this design. Recorded here rather
than edited in above, because what the design got wrong is worth keeping.

**What held.** The method block worked: the model walked all ten protocol steps
in order, declared the D10 step unsupported instead of bluffing it, and cited
nothing. Not one date in the answer was invented — every one appeared verbatim
in the prompt, so the `_GROUND_TRUTH_WARNING` discipline carried over intact.

### 1. `assume_promise` did not hold, and is reverted

The design's position was that the arithmetic could run with a fabricated
promise as long as the prompt labelled the stages "period boundaries, not a
prediction" and asked the model for the promise judgement. It did not judge. It
wrote:

> You will receive your major career promotion during 2026-08-27 to 2027-08-07.

High confidence, no promise verdict anywhere. The reason is visible in the block
itself: `activation` and `trigger` were the **same range**, and both began on the
query date, because `windows_between` anchors to `start=now`. The block contained
no event — it was the ten-year horizon restated. A range that begins today reads
as imminent whatever sits above it, and no label survives that.

So `dasha_windows` leaves the direct topology, `assume_promise` is deleted from
the timing node, and the chain shortens to `hierarchy → varga_select →
direct_read`. In place of the window the prompt derives, from the chart:

* the antardashas of the running mahadasha, and
* the pratyantardashas of the running antardasha.

That is the granularity a timing answer needs — a mahadasha runs six to twenty
years and cannot time anything — and none of those boundaries starts today.

Two instructions changed with it. The timing step now requires a promise verdict
in one sentence *before any date may be written*, and a "no" ends the step. And
the no-certainty rule, which covered only health, treatment and death, now
covers dated claims of every kind: "never state that an event WILL happen, on a
date or in a window".

### 2. The prompt was arguing with itself about D10

It supplied ten D10 placements under WIDER CHART and, below them, "D10 … I have
not used it. Do not reason from these." `chart_natal_node` appends varga facts
for whatever `relevant_vargas` the intake classifier named; `varga_select`
decides admissibility from birth-time precision and knows nothing about that
list. When they disagree, both verdicts shipped.

`without_withheld_vargas` drops the facts and keeps the statement. Dropping both
would leave a silence indistinguishable from a division nobody needed.

### 3. The computed diagnosis was never being sent

`PlanetDiagnosis` has carried `dignity`, `combust`, `strength`, `vargottama`,
`functional_nature`, `aspects_received`, `dispositor` and `nakshatra_lord` since
Phase 2. **None of it reached the prompt.** The chart block was sign, house,
nakshatra, pada and retrogression only.

The cost was legible in the output. The model re-derived exaltation from raw
signs — correctly — and then wrote "there are no conflicting malefic afflictions
to the 10th house or its ruler" about a chart whose Sun and Moon sat in the same
nakshatra *pada*. That is a new-moon birth: the lagna lord is dark, and the model
had cited that same Moon as a Raja Yoga component. With no combustion flag and no
aspect list in front of it, the sentence could not have been a judgement.

A `PLANETARY CONDITION` block now carries it, marked authoritative over the
model's own reading. Registry symbols are humanised (`dignity.neutral` →
`neutral`); `karaka.*` and `lord.bhava.*` entries are filtered out of the aspect
lists, since those are join keys rather than aspecting bodies; grahas are in
conventional order so the two blocks line up; and the partial-strength-system
caveat is stated once rather than nine times.

This is the largest of the three. Everything in it was already computed and
simply withheld.

### 4. The prompt did not know what day it was

Found by the second reading, and the plainest miss of the four. The period block
named the running dasha — "Currently running: Sun Mahadasha, Venus Antardasha" —
and never stated the date. So nothing in the prompt distinguished a window that
had closed from one still ahead, and a reading of "when will I get married?"
offered `Saturn: 2024-06-12 to 2025-05-25` as "an earlier period of potential
activation": a window that shut sixteen months before the question was asked.
`query_time` was in state throughout and simply never rendered.

Three changes:

* **`today_block`** states the date and the weekday — the weekday because
  `ground_truth_rules` tells the model to copy it from the Date line rather than
  work it out, which requires a Date line to exist. No fallback to
  `datetime.now()`: a fabricated date is worse than none, and it would make the
  golden snapshot unpinnable.
* **Every period carries `[past]`, `[RUNNING NOW]` or `[future]`**, computed
  against the reading date rather than left for the model to infer. It had the
  boundaries and could in principle have compared them; "in principle" is what
  produced the closed window.
* **The horizon extends one mahadasha further.** Only the current mahadasha was
  broken down, so a question whose answer fell past it had nowhere to land — the
  reading named the next mahadasha correctly and then could not time anything
  inside it. Six to twenty more years of horizon for nine more lines.

The timing step now also says to name only `[RUNNING NOW]` or `[future]`
periods, and that if the suited periods have gone by, to say so and name the
next one that fits however far out it falls.

### Still open

**Steps the facts cannot support get padded rather than declared.** Step 4 (D10)
was correctly declared unsupported, but step 9 (cross-school confirmation)
produced "interlocking dispositor dynamics and nakshatra dispositors validate
institutional elevation" — filler in the shape of an answer. Step 8 (transit)
reached for the transiting Moon's nakshatra, which moves every 2¼ days and is
noise at career scale, because the prompt carries no real transit data. Either
supply transit positions or name transit as unavailable; the current prompt does
neither, and the model fills the gap.
