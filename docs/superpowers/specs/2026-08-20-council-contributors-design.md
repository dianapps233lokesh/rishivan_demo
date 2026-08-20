# Council contributors: one voice, many computers

**Date:** 2026-08-20
**Status:** approved design, not yet implemented

## Problem

Three defects share one root cause.

1. **Two Rishis speak.** `council/lens.py` generates a second Rishi's prose after the
   primary answer, shown in its own expander. A reading arrives as two opinions rather
   than one grounded answer.
2. **The wrong Rishi answers.** The classifier routes *"When will I get married?"* to
   `ritam` (timing) as primary. Marriage belongs to PREMA, which `medhan` owns. Because
   the coverage gate keys off the routed life domain and `ritam` rates all eight domains
   uniformly medium, a timing question's rules are gated by nothing.
3. **Secondaries never fire.** `route_question("Will I become a billionaire?")` returns
   `secondary=()`. ER §12 prescribes ARTHA primary with KARMA / ATMA / YATRA secondary.
   Only the single word "billionaire" matched, so the multi-Rishi structure the client
   documents are built around collapses to one domain on most questions.

The root cause: the repo has two independent notions of "who owns this question" — the
classifier's persona and `routing`'s life domain — and no notion at all of a Rishi that
contributes evidence without speaking.

## Terminology

Two eight-member taxonomies exist and are not interchangeable.

* **Life domain** — the client's eight: ATMA, PREMA, ARTHA, KARMA, VANSH, AAROGYA,
  YATRA, DHARMA. Defined in ER §4–11. This is BP §4 level 4. Carried by
  `domains.LIFE_DOMAIN_KEYS`, and it is what rule coverage and `rishi_affinity` are
  annotated against.
* **Persona** — the eight implemented voices: agam, vyom, dhruvan, ritam, tejan, medhan,
  tattvan, pragnav. A repo concept with no client counterpart.

`domains.RISHI_LIFE_DOMAINS` already maps persona → life domain, weighted, many-to-many.
This design does not change that table. It changes who is allowed to use it.

## Section 1 — Two classes of Rishi

```python
DOMAIN_RISHIS  = frozenset({"agam", "dhruvan", "medhan", "tattvan", "pragnav"})
SERVICE_RISHIS = frozenset({"vyom", "ritam", "tejan"})
```

The split is not new information. It is already latent in `RISHI_LIFE_DOMAINS`: vyom and
ritam rate every domain exactly MEDIUM and tejan rates every domain LOW–MEDIUM, so none
of the three owns anything. `domains.py`'s own comment states the reason — they are
technique lenses, and the client treats them as shared services (ER §13 calls Muhurta a
"cross-domain timing service"; BP §17 puts remedies in a separate corpus).

**A service Rishi is never the primary voice.** Consequences, stated plainly because they
change current working behaviour:

| Question | Today | After |
|---|---|---|
| "When will I marry?" | ritam answers | medhan answers, ritam contributes the dasha |
| "What remedies for Saturn?" | tejan answers | see "Remedy questions" below |
| "What dasha am I running?" | ritam answers | `intent=="chart"` already returns a computed table with no persona; unchanged |
| routing finds nothing | vyom answers (all-medium: gates nothing) | tattvan answers |

**Remedy questions.** A remedy is not a life domain, so `routing` must not gain remedy
keywords — that would make "remedy" compete with "health" for ownership of a question.
The question's *subject* routes it, and tejan contributes regardless:

* *"What remedies should I do for my health?"* → AAROGYA (matched "health") → `medhan`
  answers, tejan contributes. Verified against the current keyword table.
* *"What remedies for Saturn?"* → routing returns `None` (verified: no keyword matches) →
  falls back to `tattvan` per Section 2 step 5.

The second case is weak but honest: the question names a planet, not a life area, so no
domain owns it. Do not paper over it by routing remedy words to a domain.

## Section 2 — The life domain picks the persona

Today `route_question()` picks the life domain (gating rules) and the classifier LLM picks
the persona (owning the voice), independently. In the billionaire reading they agreed by
luck.

New order of authority:

1. `route_question(question)` → primary life domain. Deterministic, unchanged.
2. `rishis_for_life_domain(domain)` → candidate personas at HIGH weight.
3. Exactly one candidate: that is the voice.
4. Two candidates (ATMA → agam | tattvan; DHARMA → agam | pragnav): the classifier's
   `primary_rishi` breaks the tie if it is one of them, else the first in
   `LIFE_DOMAIN_KEYS` order.
5. Routing returns `None`: use the classifier's `primary_rishi` if it is a domain Rishi,
   else `tattvan`.

One source of truth for coverage. The LLM is demoted to a tiebreak.

## Section 3 — The contributor protocol

```python
@dataclass(frozen=True)
class ContributorReport:
    rishi: str                     # persona key
    computed: dict[str, str]       # label -> value; ground truth, never paraphrased
    rules: tuple[RuleHit, ...]     # rules true of the chart under THIS rishi's coverage
    note: str = ""                 # one templated sentence; no LLM

def contribute(chart, tokens, routing, applicable) -> ContributorReport | None
```

Deterministic. No LLM call per contributor. Two reasons: N serial generations before the
first token is a latency cost the reading cannot absorb, and a generated briefing
paraphrases — the same failure that already forces nakshatra names to be printed outside
the Rishi's voice.

`None` means "nothing to contribute". An empty report never reaches the prompt, so a thin
corpus cannot pad an answer with noise.

| Contributor | `computed` | `rules` |
|---|---|---|
| ritam | maha / antar / pratyantar lord + end date, from `chart/dasha.current_periods` | `rule_category == "timing"` |
| vyom | janma nakshatra, conjunctions, dignities | condition names a conjunction or nakshatra |
| tejan | — | rules carrying a remedy effect |
| domain (e.g. tattvan) | — | rules passing that domain's coverage gate |

Two honest gaps:

* **vyom** — its real job is yoga recognition, which does not exist. It reports nakshatra,
  conjunctions and dignity only, and the gap stays visible rather than being filled.
* **tejan** — a remedy corpus *does* exist. `knowledge/compile/persist.py:94` writes a
  `remedies` list onto every compiled rule, populated by extractor Example 4. But
  `scripts/embed_rules.py` never copies it into the Qdrant payload and `rag/rules.py`
  never reads it, so it is unreachable at query time. This is the same reader/writer
  contract gap already found once with `exceptions`/`modifiers`. **Adding `remedies` to
  the payload is in scope for this change** — without it tejan can only ever return
  `None`, and the contributor would be dead code.

## Section 4 — Which contributors fire

Service Rishis, deterministic triggers:

* **ritam** — `routing.application == "timing"`, or the question names a dasha level.
* **vyom** — always. Every ER §4–11 protocol contains a "major combinations" step and a
  "Nakshatra" step, so this is not selective and must not pretend to be.
* **tejan** — the question asks for a remedy.

Domain Rishis: the union of `routing.secondary` and the classifier's `supporting_rishis`
mapped back to life domains. `supporting_rishis` is already in the classifier's output
and costs nothing extra.

**Prerequisite, in scope.** `routing.secondary` is empty on most questions, so domain
contributors would almost never fire and this change would be inert on real input. The
routing-secondary fix ships inside this change, with `supporting_rishis` as the second
source. It is not a follow-up.

## Section 5 — What the primary receives

```
YOUR COVERAGE (ER §6 — Dhruvan / ARTHA):
  houses 1, 2, 11 primary · 5, 9, 10 supporting

CHART — WITHIN YOUR COVERAGE:
  - 2nd lord Sun in the 6th house
  - 11th lord Venus in the 7th house

CHART — WIDER CONTEXT (do not lead from these):
  - 7th lord Saturn in the 6th house

EVIDENCE FROM RITAM (Keeper of Time):
  - Mahadasha: Saturn until 2037-06-07
  - Antardasha: Venus until 2028-05-29
  - 3 timing rules true of this chart

EVIDENCE FROM TATTVAN (Keeper of Truth · ATMA):
  - 4 rules on the 1st house and its lord

CLASSICAL RULES:
  BPHS 2.1 [S0 · parashari] ...
  Hindu Predictive Astrology p.178 [S3 · parashari] ...
```

Two existing defects close here as a consequence rather than as separate work:

* **Facts are ordered by the primary's coverage** instead of dumped flat. Today ATMA is
  gated to house 1 for rules, then handed all twelve house lords as prose — so the model
  reasons from evidence no rule licensed, defeating the gate. Nothing is deleted (every
  §4–11 protocol ends in whole-chart synthesis); it is demoted and labelled.
* **Every source carries tier and school.** In the billionaire reading the second voice
  named S3 *Hindu Predictive Astrology* as a "classic text" while S0 BPHS sat unnamed in
  the same page set — BP §8 rule 4 (evidence hierarchy) has nothing to act on when the
  model cannot see which page outranks which.

## Section 6 — Deletions

* `council/lens.py` — second-voice generation and prompt.
* `streamlit_app.py` — the second-voice expander, replaced by a panel listing each
  contributor and what it supplied.

This removes, rather than patches, a live rendering bug: `streamlit_app.py:668` calls
`st.markdown(_md(secondary["body"]))` with no `unsafe_allow_html=True`, and `_MD` is
built with `html: False` so markdown-it escapes the model's `<p>`/`<em>` tags before
Streamlit ever sees them. The second voice renders its HTML as literal text. The lens
prompt forbids headers and bullets but not HTML, which is why only this path is affected.

Net effect: one fewer LLM call per reading, and the transparency moves from a second
opinion to an attribution panel.

## Section 7 — `QueryDomain` is two ideas in one enum

`natal | muhurta | prashna | general` appears in neither client document. Against BP §4:

| value | what it is |
|---|---|
| `prashna` | BP §4 level 2 — a school |
| `muhurta` | BP §4 level 2 — a school |
| `natal` | not a level; the default (Parashari hora at the birth moment) |
| `general` | not in the ontology |

So two schools, one default and one null case share a list named `domain`, while BP §4
level 4 *also* means domain and refers to the eight Rishis. This is the `book_domain`
mistake — already deleted from `domains.py` for flattening three of §4's levels into one
list — recurring in a different place.

`GENERAL` is also dead: assigned as a default at `classifier.py:282` and
`orchestrator.py:79`, branched on nowhere. A conceptual question falls through every
branch and reaches the plain `search()` fallback because `chart_facts` is empty. It works
by accident.

The enum does do one real job that no BP level covers, because the documents describe an
ontology and not a compute path: **which moment to cast the chart for**.

Split into two orthogonal fields:

```python
class ChartEpoch(str, Enum):
    BIRTH  = "birth"
    TARGET = "target"      # the day a muhurta question names
    NOW    = "now"
    NONE   = "none"        # conceptual; cast nothing

class QuestionSchool(str, Enum):
    PARASHARI = "parashari"
    PRASHNA   = "prashna"
    MUHURTA   = "muhurta"
```

Same information, one field per idea, and `NONE` becomes a case something branches on.

**The payoff is enforcement, not tidiness.** The question's school is currently implicit
in `QueryDomain` and never reaches retrieval — which is why *Prashna Marga Part 2* and
*Deva Keralam (nadi)* pages were cited in the natal billionaire reading, four schools
deep and unlabelled. With school as a first-class field, BP §8 rule 5 ("never mix schools
silently") becomes checkable: a `parashari` question does not retrieve `prashna` or `nadi`
pages unless a protocol's cross-school confirmation step asks for them, and when it does,
they arrive labelled.

## Scope and phasing

Two phases. Each is independently shippable and independently valuable; phase 1 does not
depend on phase 2.

**Phase 1 — the council restructure.** Sections 1–6. Rishi classes, domain-picks-persona,
the contributor protocol, contributor selection, the coverage-ordered prompt with tier and
school labels, the `lens.py` deletion, the routing-secondary fix, and the `remedies`
payload field.

**Phase 2 — the `QueryDomain` split.** Section 7. `ChartEpoch` + `QuestionSchool`, and the
school filter on retrieval that BP §8 rule 5 needs.

Phase 2 is separable because nothing in phase 1 reads `QueryDomain` except
`prompts.py:263`'s three-way branch, which keeps working unchanged. Splitting keeps each
plan reviewable — phase 1 alone touches routing, domains, orchestrator, prompts, a new
contributors module, streamlit, and the embed script.

## Known limitation, accepted

**YATRA has no real owner.** It is assigned to `dhruvan`, and `domains.py` says so
itself: the client gives Yatra its own protocol (D4, houses 3/4/9/12, Prashna) that no
persona implements. Career/wealth and foreign-settlement are different coverage sets, so
*"Should I settle abroad?"* is answered by the wealth Rishi using wealth houses.

Left unchanged here. Fixing it means adding a ninth persona or resplitting `dhruvan` —
a separate decision. Yatra questions stay weak after this lands.

## Testing

TDD throughout: test first, watch it fail, then implement.

Contract tests:

* every one of the eight life domains resolves to exactly one primary persona, and that
  persona is in `DOMAIN_RISHIS`
* no service Rishi is ever primary, across all 30 questions in `tests/eval/questions.py`
* a contributor with nothing to report returns `None` and emits no prompt block
* `"Will I become a billionaire?"` → primary `dhruvan`, contributors include `tattvan`
  (ER §12's ATMA secondary)
* `"When will I marry?"` → primary `medhan`, contributors include `ritam` — asserting
  the specific inversion this design exists to fix
* a `parashari` question retrieves no `prashna` or `nadi` pages
* `ChartEpoch.NONE` is branched on, not merely assigned

Regression: `scripts/eval_rules.py` routing accuracy must not fall. Note that it grades
only `primary`, so it cannot see the secondary fix — the two assertions above cover that.
