# Client demo script

Every question below was run against the engine on the reference chart
(New Delhi, 15 Aug 1947 00:00 IST) and the observed behaviour recorded. Rule counts come
from the extracted corpus with the coverage gate applied; the live figures depend on
which rules are approved and published, so treat them as the shape to expect rather than
exact numbers to quote.

Ordering is deliberate: openers that cannot fail, then the domain sweep, then the
showpieces, then the boundary. Do not reorder — the showpieces only land once the client
believes the arithmetic.

---

## 0. Before you start — one hard prerequisite

Run the embedder. `activation` reaches the vector payload only when
`scripts/embed_rules.py` is re-run; on a stale collection every rule parses to
"no period recorded", the timing labels silently never appear, and **Track C.3 below
will not work**.

Verify it took: ask any "when" question and open the rules panel. It must say
*"N of them record an activating period"*. If it says *"No rule in this collection
records an activating period"*, the index is stale — that message exists precisely so
this fails loudly instead of quietly.

---

## Track A — openers that cannot fail

Pure arithmetic on the computed chart. No LLM writes these numbers, so they are always
exactly right. Open here: it establishes that the engine computes rather than talks.

| Ask | What appears | Point at |
|---|---|---|
| "Show me my D9 chart" | D9 table | Swiss Ephemeris, computed locally. Try D10, D30, D60 — all 16 vargas |
| "Show me my Vimshottari dasha periods" | full timeline, current period marked | maha → antar → pratyantar → sookshma → prana |
| "What is my mulank and bhagyank?" | numerology table | BP §4 level 1 — a separate universe, additive to Jyotisha, never a substitute |
| "Show me my ashtakavarga" | SAV/BAV table | |
| "What is the rahu kaal today?" | computed window with clock times | sunrise/sunset arithmetic. "tomorrow" and "day after tomorrow" also parse |

If a table cannot be computed the engine says so by name rather than showing a different
chart. That refusal is worth pointing out — it is the same discipline as everything else.

---

## Track B — the eight-domain sweep

One per Rishi, ordered by how much rule evidence actually stands behind it on this chart.
**Lead with the first four.**

| # | Ask | Routes to | Voice | Eligible rules |
|---|---|---|---|---|
| 1 | "What is my relationship with my father?" | VANSH | medhan | 34 |
| 2 | "Will I have children?" | VANSH | medhan | 26 |
| 3 | "Will I settle abroad?" | YATRA | dhruvan | 26 |
| 4 | "What does my chart say about my vitality?" | AAROGYA | medhan | 25 |
| 5 | "What is my personality like?" | ATMA | agam | 24 |
| 6 | "What kind of spouse will I have?" | PREMA | medhan | 21 |
| 7 | "Will I be wealthy?" | ARTHA | dhruvan | 15 |
| 8 | "What career suits me?" | KARMA | dhruvan | 14 |
| 9 | "What is my life purpose?" | DHARMA | agam | 11 |

Routing is deterministic keyword matching, not a model call, so it is reproducible and
explainable — open the routing panel and show which phrase matched.

Question 1 is worth a sentence of its own. It used to route to PREMA and answer a
question about a parent with marriage rules, because the generic word "relationship" tied
with the specific word "father" and document order broke the tie. Specific now beats
generic. It is also the best-evidenced question in the set.

---

## Track C — the four showpieces

### C.1 The coverage gate — the thing nothing else does

Ask **"What career suits me?"**, open the rules panel.

> 54 rules are true of this chart. **14 are shown. 40 scored exactly zero** — not ranked
> low, zero — because their subject house sits outside KARMA's coverage.

Then ask **"What is my life purpose?"** on the same chart: 11 eligible, 43 dropped. Same
chart, same corpus, different question, different admissible evidence.

This is the difference between the engine and a document search. A similarity search
would return the same top-k for both. Say plainly: *matching happens first, ranking
second* — nominating by similarity first measured a loss of 11–14 of 21 true rules,
because a similarity window has no way to prefer rules that are actually true.

### C.2 The safety gate — refusing the source, not softening it

Ask **"Will my marriage be happy?"**

The corpus genuinely contains rules stating outcomes like *"his death is quite certain."*
They are legitimately stored — ER §9 forbids presenting them as certainty, not holding
them. On a marriage question they are **withheld entirely**.

Then ask **"How long will I live?"** The same rule is now **admitted**, flagged
`⚠ traditional indication, not a prediction`.

The gate is the question's own words, not the Rishi's domain. Gating on domain was
circular — medhan owns health, so every medhan question admitted every death rule.

### C.3 Timing — a promise is not a running period

Requires the embedder to have been re-run (§0).

Ask **"Will I marry?"** then **"When will I marry?"** back to back, same chart.

| | "Will I marry?" | "When will I marry?" |
|---|---|---|
| Application | `potential` | `timing` |
| Rules returned | formation only | timing rules lead |
| Timing labels | none | RUNNING NOW / NOT RUNNING |

Three states, and the third is the point:

- **RUNNING NOW** — the dasha period this rule needs is current
- **NOT RUNNING** — the promise holds, its activating period does not
- **no label** — the rule records no activating period; nothing is claimed about when

On this chart the running periods are Mars maha / Rahu antar, and the rules that activate
cite exactly that. Be straight about the limit: the engine says **whether** a period is
running, not the window's start and end dates. Do not let the client infer dates.

### C.4 Cross-domain evidence (ER §12)

Ask **"Will I become a billionaire?"** — ARTHA primary, with KARMA / ATMA / YATRA
contributing. Secondary Rishis **compute and report**; they do not speak. One question,
one voice, several computers. Cap is three domains, because §12 says *"do not invoke all
eight by default."*

Good second: **"Should I leave my job and start a business?"** → KARMA primary.

---

## Track D — the boundary (do not skip this)

Ask **"What does horary astrology say about my question right now?"** or
**"What is my lucky colour?"**

The engine reports these as **outside the supported knowledge boundary** rather than
answering from whatever happened to match. ER §20: *"Unsupported questions must be
surfaced as unsupported rather than hallucinated."*

Showing a deliberate refusal is stronger than hiding it. It is also the honest frame for
every gap that follows — the system knows what it does not know.

---

## Do not ask these

| Ask | Why not |
|---|---|
| Anything expecting a **date, year or age** | Timing resolves to running / not running, never to a window. The model may hedge well, but do not invite it |
| "What are my yogas?" / "Do I have Gaja Kesari yoga?" | No yoga recognition. Named yogas will not be identified |
| "Is Saturn strong in my chart?" | Shadbala is not computed — `strength_cmp` is deliberately out of DSL scope, so strength claims have no basis |
| "Compare my chart with my partner's" | Single-chart engine. No synastry |
| "What does Jaimini / KP say?" | Corpus not acquired. Correctly refuses, but do not build a moment around a refusal |
| Anything on **D3, D4, D16, D20, D24, D27, D40, D45, D60** as *rule evidence* | Computed and displayable, but emit no fact tokens, so no rule tests against them. The **table** is safe to show; a **reading grounded in them** is not |

---

## If the client asks "is it finished?"

No, and the record is explicit — `docs/client-spec-gap-map.md` tracks every spec line as
DONE / PARTIAL / ABSENT / BLOCKED, including 23 items blocked on corpus acquisition
(Jaimini, KP, Tajika, Samudrika, Vastu, Dharma scripture) that are acquisition problems,
not engineering ones. BP §21's validation lab is unstarted.

What is finished is the spine: question → intent → chart → exact rule match → cited
answer, with the coverage gate, the safety gate and the timing split all observable in
the UI. That is the part that was hard, and it is the part being demonstrated.
