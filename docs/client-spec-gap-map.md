# Client spec → implementation gap map

Every section of both client documents, against what is actually built, as of 2026-08-20
on branch `prod_pipeline`.

**Update — Tier 1 of §5 is implemented** (`2a765f1`). The concept layer now exists:
`council/constitution.py` (§16 from §4-11), `council/routing.py` (§12),
`knowledge/concepts.py` (§6's CONCEPTS), `rag/relevance.py` (coverage as a gate) and
`council/source_matrix.py` (§15). Rows changed by that work are marked `DONE (Tier 1)`
below; everything else is unchanged.

- `docs/client/blueprint-master-implementation.pdf` — cited as **BP §n**
- `docs/client/eight-rishis-domain-ownership.pdf` — cited as **ER §n**

No implementation spec here, by request. Status and effort per item, blockers named,
sequencing recommendation at the end.

**Status vocabulary**

| | meaning |
|---|---|
| `DONE` | implemented and verified |
| `PARTIAL` | some of it works; the gap is stated |
| `ABSENT` | nothing implements this |
| `BLOCKED` | cannot be built from the corpus we hold — acquisition or vocabulary decision first |
| `N/A` | belongs to the production backend, not this repo |

**Effort vocabulary** — `S` under a day · `M` a few days · `L` one to two weeks ·
`XL` a month or more, or gated on research.

---

## 1. Verified current state

Everything below was measured, not recalled.

### Corpus: 23 books ingested, 18 now bridged

Updated after `68afd40` (edition profiles). Readiness is units per page — BPHS runs at
1.3-1.6, so anything under 0.3 means the adapter is not pairing that book's verses.

```
                                       pages shloka  units  u/pg   state
bphs-gcsharma-vol1                       657   1065   1041  1.58   READY
bphs-gcsharma-vol2                       818   1183   1076  1.32   READY
sarvartha-chintamani                     374   1684   1112  2.97   READY
prashna-tantra                           123    368    339  2.76   READY
saravali-santhanam-en                    351    664    567  1.62   READY
muhurtachintamani                        322    523    423  1.31   READY
hindupredictiveastrology-raman           456      0    304  0.67   partial
jatakaparijata-sastri-vol2               684   1323    396  0.58   partial
jatakaparijata-sastri-vol1               662   1720    292  0.44   partial
phaladeepika-sastri-1950                 473    866    141  0.30   THIN
cheiros-book-of-numbers                  194      0     39  0.20   THIN
prasnamarga-raman-part1                  278      0     34  0.12   THIN
bhavartha-ratnakara                      128      5      9  0.07   THIN
numerology-and-the-divine-triangle       292      0     18  0.06   THIN
brihatjataka-row-1919                    274      1     13  0.05   THIN
numerology-key-to-your-inner-self        292      0     10  0.03   THIN
prasnamarga-raman-part2                  242      0      3  0.01   THIN
the-complete-book-of-numerology          205      0      1  0.00   THIN
devakeralam vol 1 / vol 2, dharma-sindhu, laghu-parashari, vivaha-patalam
                                                        0  0.00   no chapters
```

**5,818 units, 2,932 rule-destined**, up from 2,063 and 975. Six books are ready, three
partial, nine thin, five unbridgeable.

**The thin books need a second profile dimension.** Chapters are solved; verse *pairing*
is not. Phaladeepika has 866 shlokas and 1,401 prose blocks and yields 141 units, because
`bridge/verse_ref.py` reads BPHS's danda conventions and `bridge/adapt.py` pairs a shloka
with a *numbered* translation. Books that number verses differently, or print no
Devanagari at all (Prasna Marga, Hindu Predictive, all four numerology titles have zero
shloka elements), do not pair. That is an `EditionProfile` field that does not exist yet.

Two separate stores, and the difference matters:

- **Page retrieval** (Qdrant `rishivan_docs`) holds **52,958 vectors covering all 22
  books.** This is what the app answers from today.
- **The knowledge pipeline** (`corpus_page` → `chapter` → `sutra_unit` → `rule`) holds
  **only BPHS.** Every other book is pages-only: no chapters, no verses, no rules.

So "we are following only the Koonji thing from these books" is half the picture — the
Koonji path covers *one* book, and the other 21 reach the user only as page text.

### Triage: vol 2 is extracted-ready and untouched

| | rule-destined | knowledge item | ambiguous |
|---|---|---|---|
| BPHS vol 1 | 486 | 423 | 99 |
| BPHS vol 2 | **489** | 392 | 174 |

Vol 2 is bridged and triaged with 489 rule-bearing verses and **zero rules extracted**.
On vol 1's measured rate that is ~34 minutes and ~$0.78.

### The rule base: 376 approved rules, one school, no confidence

```
school / tradition   parashari / classical   398 of 398   (100%)
confidence           0.5 min, 0.5 max, 1 distinct value   (never set)
```

Condition atoms across the 376 valid rules:

```
lord_of_house_in_house 286   houses  1:92  2:73  3:66  4:70  5:72  6:70
planet_in_house        154           7:92  8:68  9:74 10:64 11:66 12:79
aspected_by             31   planets sun:45 mars:42 saturn:33 jupiter:32
conjunct                24           moon:31 venus:29 mercury:22 rahu:16
dignity_is              12
planet_in_sign           9   vargas  ZERO atoms use a divisional chart
house_is_empty           4
lord_of_house_in_sign    1
```

Two facts to carry into the map:

1. **Every rule names houses and planets.** Concept-overlap relevance is therefore
   computable from the atoms we already store, with no re-extraction.
2. **No rule and no chart token uses a divisional chart.** `vocab.EMITTED_SCOPES` lists
   d2/d7/d9/d10/d12/d30, but `chart.tokens.SUPPORTED_SCOPES` is `("", "from_moon.",
   "from_sun.")`. Both halves are missing it, so a varga rule can never match.

### The vocabulary ceiling, measured on 581 declines

```
195  benefic/malefic as a class      33  ascendant sign as a condition
150  avastha / combustion            32  house or lord as an atom subject
 44  strength / shadbala             29  vargas beyond D9
 29  dignity of a house lord         14  chara karakas
```

---

## 2. Eight Rishis document

### ER §1 — the routing pipeline

> question classifier → primary Rishi → **secondary Rishi(s)** → shared calculation →
> **domain-specific Koonji + source retrieval** → Rishi reasoning → **cross-Rishi
> evidence comparison** → **master synthesis** → answer + sources + uncertainty

| Stage | Status | Effort | Note |
|---|---|---|---|
| Question/intent classifier | `DONE` | — | `council/classifier.py`, one Flash call, returns rishi + domain + intent + vargas + dasha level |
| Primary Rishi | `DONE` | — | |
| Secondary Rishi(s) | `DONE (Tier 1)` | — | `routing.py` returns primary + secondaries per §12, capped at 3 ("invoke the minimum set"), and both gather evidence. Secondaries are weighted at half, since §12 invokes them for independent evidence, not as equals. |
| Shared calculation engine | `DONE` | — | Swiss Ephemeris, local, no network |
| Domain-specific Koonji retrieval | `DONE (Tier 1)` | — | Now gated on §4-11 coverage. A rule whose subject house is outside the routed Rishi's coverage scores 0 and cannot be rescued by its affinity tag. |
| Source retrieval | `DONE` | — | 52,958 page vectors, authority-weighted |
| Rishi reasoning | `DONE (Phase 4)` | — | `RishiReport`: supporting, **weakening (required)**, assumptions, would_change_my_mind, scored confidence with reasons. Structure before prose, so the prose can be checked against it. |
| Cross-Rishi evidence comparison | `DONE (Phase 4)` | — | `synthesis_node` reports convergence and preserves disagreement. `sakshi` raises a `contradiction` finding when two reports disagree in sign. |
| Master synthesis | `DONE (Phase 4)` | — | `graph/nodes/synthesis.py`, deterministic. It arranges what the council said; it does not run a ninth opinion over the eight. |
| Uncertainty in the answer | `PARTIAL` | S | Each report now carries a scored confidence with stated reasons, and per-domain corroboration floors cap claims that do not meet them. **`rule.confidence` is still uniformly 0.5** — the confidence reported comes from the evidence graph, not from the rule, and that field remains unset. |

### ER §2 — the shared Rishivan Core

| Shared layer | Status | Effort | Note |
|---|---|---|---|
| Master corpus | `DONE` | — | 22 books, not divided between Rishis |
| Source registry | `PARTIAL` | S | `document` has slug/title/pages/language/status. No edition, rights, or SHA-256 hash. |
| Verified text | `PARTIAL` | L | Devanagari + translation + commentary are held separately per unit for BPHS. No human verification pass has been run; BP §3 stage 4 is unmet. |
| Ontology | `PARTIAL` | M | `astro/vocab.py` is a *fact-token* vocabulary, not the BP §4 five-level ontology (universe → school → concept → life domain → application). Levels 1, 2 and 5 are absent. |
| Koonji | `PARTIAL` | — | 376 rules, one book. See ER §14, BP §6. |
| Knowledge graph | `ABSENT` | L | BP §10/§11. Nothing. |
| Astronomy engine | `DONE` | — | |
| Chart engine | `PARTIAL` | M | D1, vargas, dashas, transits, panchanga, ashtakavarga all compute **for display**. Only D1 + from_moon/from_sun are tokenised for matching. |
| Evidence engine | `PARTIAL` | L | Source authority exists (`rag/authority.py`, 21 books hand-weighted). No contradiction detection, no confidence, no validation state. |
| Validation lab | `ABSENT` | XL | BP §15. Nothing. |

### ER §3 — the eight dimensions

`DONE`. `LIFE_DOMAIN_KEYS` in `council/domains.py` is byte-identical to ER §21, and
`RISHI_LIFE_DOMAINS` maps the repo's eight personas onto them, weighted, many-to-many —
per your instruction to keep the repo's Rishis and map them. A test asserts every client
domain has at least one persona rating it High (ER §20, no orphan domains).

### ER §4–11 — the eight Rishi definitions

**This is the largest and most consequential gap.** Each section gives four things:

| Per-Rishi element | Status | Effort |
|---|---|---|
| **Questions it owns** (question taxonomy) | `DONE (Tier 1)` | — |
| **Astrological coverage** (the concept/fact set) | `DONE (Tier 1)` | — |
| **Protocol** (ordered analysis checklist) | `PARTIAL` | L — transcribed into each constitution, but the answer is not yet assembled in protocol order |
| **Primary sources** (per-Rishi book set) | `DONE (Tier 1)` | — |

The concept sets, transcribed from the documents:

| Rishi | Houses | Planets / factors | Vargas | Cross-school |
|---|---|---|---|---|
| ATMA | 1 | Lagna lord, Sun, Moon, Nakshatra, dignity, strength, aspects, conjunctions | relevant | Jaimini: Atmakaraka, Karakamsha |
| PREMA | 7, 2, 8, 11 | 7th lord, Venus, Jupiter | **D9** | Darakaraka, Upapada, Arudha; KP; Nadi |
| ARTHA | 2, 5, 9, 10, 11, 1 | lords, dignity, Shadbala, Avastha, Ashtakavarga, benefic/malefic | **D2**, D10 | Jaimini; KP; Nadi |
| KARMA | 10, 1, 6, 2, 11 | lords, strength | **D10** | Jaimini; KP; Nadi |
| VANSH | 2, 3, 4, 5, 9 | lords, Karakas | **D7, D12** | Jaimini; Nadi |
| AAROGYA | 1, 6, 8, 12 | Sun, Moon, planetary strength | relevant | — |
| YATRA | 3, 4, 8, 9, 12 | Rahu, Ketu, lords | **D4** | Jaimini; Nadi; Prashna |
| DHARMA | 9, 12 | Jyotisha spiritual indicators | — | Jaimini Atmakaraka/Karakamsha |

Why this is the defect you observed: the houses in the rule base are near-uniformly
distributed (64–92 rules each), so a four-house coverage set selects a genuine
subset — roughly a quarter of the corpus — where the current `life_domains` tag does
not discriminate at all. BPHS 22.6 *"the native's father will be a king"* surfaced on
your marriage question because its domain tag reads "family" and Medhan owns family. Its
**concept is the 9th house**, which appears nowhere in PREMA's coverage. Concept overlap
rejects it; a domain tag cannot.

What is buildable from our corpus, per Rishi:

| Rishi | Parashari half | Blocked half |
|---|---|---|
| ATMA | houses, Sun/Moon, dignity, aspects | Atmakaraka/Karakamsha (`BLOCKED`, no Jaimini corpus + not in vocabulary) |
| PREMA | 7th/2nd/8th/11th, Venus, Jupiter | D9 (`BLOCKED`, no varga tokens), Darakaraka/Upapada (`BLOCKED`), KP (`BLOCKED`, no corpus) |
| ARTHA | 2/5/9/10/11 + lords | D2 (`BLOCKED`), Shadbala/Avastha (`BLOCKED`, 194 declines), benefic/malefic (`BLOCKED`, 195 declines) |
| KARMA | 10/1/6/2/11 + lords | D10 (`BLOCKED`) |
| VANSH | 2/3/4/5/9 + lords | D7, D12 (`BLOCKED`), Karakas (`BLOCKED`) |
| AAROGYA | 1/6/8/12, Sun, Moon | — buildable in full |
| YATRA | 3/4/8/9/12, Rahu/Ketu | D4 (`BLOCKED`) |
| DHARMA | 9th/12th indicators only | **the entire scripture corpus** (`BLOCKED`, see below) |

### ER §12 — questions that cross multiple Rishis

`DONE (Tier 1)`. All thirteen worked examples are asserted verbatim in
`tests/council/test_routing.py`, and both primary and secondary domains gather evidence.
Two of the thirteen are ambiguous in the document itself ("Atma/appropriate event Rishi",
"Artha/Karma") and are asserted loosely, which the tests say at each one.

The examples, for reference:

```
"Will I become a billionaire?"            Artha    → Karma + Atma + Yatra
"Should I move abroad?"                   Yatra    → Karma + Artha + Prema/Vansh
"How will my children be?"                Vansh    → Atma + Artha + Dharma
"What is my life purpose?"                Dharma   → Atma + Karma
"Why repeated relationship problems?"     Prema    → Atma + Dharma
…8 more
```

Current behaviour: one primary Rishi retrieves; `lens.py` adds at most **one** secondary
voice, chosen by *first match* rather than by relevance, gated at confidence ≥ 0.6, and
only to write extra prose. The governing rule — "invoke the minimum set that provides
independent, relevant evidence" — is not implemented in either direction: we never invoke
more than two, and the second one contributes no evidence.

### ER §13 — where numerology, palmistry, face reading, Vastu, Prashna, Muhurta belong

| Modality | Status | Effort | Note |
|---|---|---|---|
| Numerology | `PARTIAL` | S | `chart/local_numerology.py` computes mulank/bhagyaank and the classifier routes to it. 4 numerology books are ingested as pages. Not owned per ER §13's routing (Atma for identity, Artha for business…). |
| Prashna | `PARTIAL` | M | `chart/transit.py` can cast a chart for any moment, and the classifier has a `prashna` domain. No Prashna rule engine; 3 Prashna books are pages-only. |
| Muhurta | `PARTIAL` | M | `chart/panchang.py` gives Tithi/Vara/Rahu Kaal/hora. No electional rule engine; Muhurta Chintamani is pages-only. |
| Palmistry / Samudrika | `BLOCKED` | XL | No corpus, no image input. |
| Face reading | `BLOCKED` | XL | Same. |
| Vastu | `BLOCKED` | XL | No corpus. |

### ER §14 — what each Rishi's Koonji must hold

`ABSENT` as a structure. Effort `M`. The twelve required sections exist as scattered
fragments, none of them per-Rishi:

| Required | Where it lives now |
|---|---|
| Question taxonomy | `routing.QUESTION_KEYWORDS`, from §4-11 |
| Input requirements | nowhere |
| Analysis order | `constitution.protocol` — declared, not yet applied to the answer |
| Required concepts | `constitution.py` — **the Tier 1 fix** |
| Rule library | `rule` table, not partitioned by Rishi |
| Source mapping | `rule.source` — book/chapter/verse. `DONE` |
| Modifiers | extraction schema captures them; `match/engine.py` honours `cancel`. `PARTIAL` |
| Timing layer | `timing.activation_factors` extracted, published and **evaluated** against `dasha.*` tokens; a matched rule is labelled running / not running / no period recorded |
| Cross-Rishi triggers | nowhere |
| Output schema | nowhere (prose only) |
| Confidence | column exists, uniformly 0.5 |
| Forbidden claims | `match/safety.py` — global, not per-Rishi. `PARTIAL` |

### ER §15 — Book × Rishi weighted matrix

`DONE (Tier 1)`. Transcribed in `council/source_matrix.py` — 15 source families × 8
Rishis at the document's own High / Medium / Low / Very High, with all 23 ingested book
slugs mapped to a family, and applied as a multiplier on page authority at retrieval
time. Four slugs the document does not name inherit Phaladeepika's row, which the module
records as a judgement rather than hiding. The doc's own
caveat is met in spirit — per-rule affinity is derived rather than inherited from the book
(`knowledge/affinity/derive.py`) — but the book-level matrix itself is not transcribed.

### ER §16 — the Rishi Constitution template

`PARTIAL`, effort `S` for the rest. `council/constitution.py` holds the fields anything
reads: coverage (primary/supporting houses, planets, vargas), protocol, source families,
forbidden claims, plus two the document does not ask for and this corpus needs —
`unavailable_sources` and `blocked_concepts`. Still absent from §16's twenty:
`REQUIRED_INPUTS`, `EVIDENCE_POLICY`, `CONFIDENCE_POLICY`, `OUTPUT_SCHEMA`,
`VALIDATION_DATASET`, `VERSION`, `CROSS_RISHI_TRIGGERS`.

### ER §17 — Artha's ten-step wealth decision tree

`ABSENT`, effort `L` (and partly `BLOCKED`). Steps 1–3 (define wealth, baseline promise,
supporting houses) are expressible today. Step 4 (Dhana/Raja/Mahapurusha yogas) needs yoga
recognition, which does not exist. Steps 5–8 need strength, vargas and cross-school, all
blocked. Step 9 needs the validation lab.

### ER §18 — per-Rishi performance testing

`ABSENT`, effort `L`. The document names eight metrics: routing accuracy, calculation
accuracy, rule retrieval accuracy, source fidelity, reasoning accuracy, prediction
performance, hallucination rate, calibration. `tests/eval/run_eval.py` covers
classification and pipeline smoke, not any of these. Note that **routing accuracy is
measurable today** against ER §12's 13 examples, at effort `S`.

### ER §19 — the Master Rishi life map

`ABSENT`, effort `L`. Depends on cross-Rishi comparison and synthesis.

### ER §20 — no orphan questions

`PARTIAL`, effort `S`. A test asserts no client *domain* is orphaned. There is no test
that a *question* always routes somewhere, and no explicit "outside supported boundary"
answer path — an unroutable question currently falls back to `vyom` at uniform medium
weight, which looks like an answer rather than an admission.

### ER §21 — final naming directive

`DONE` by deliberate deviation, documented in `docs/client/README.md`: the eight client
keys are the annotation and join vocabulary; the repo's eight personas are the presentation
layer, mapped weightedly onto them. Your instruction, recorded.

---

## 3. Blueprint document

### BP §1 — the non-negotiable architecture

> Never build: PDF → embeddings → LLM → prediction.

`PARTIAL`. This is the honest answer: **both architectures are running side by side.**

The Koonji path (books → verses → rules → deterministic match → cited answer) is real and
covers BPHS vol 1. The forbidden path — PDF → embeddings → LLM — is what answers from the
other 21 books, because they have no rules. The orchestrator merges both into one prompt,
and today the 20 page excerpts outweigh the ~10 rules by volume.

### BP §2 — corpus acquisition universe

`PARTIAL`. 22 of the named source families are held. Missing families that the specs
depend on elsewhere: **Jaimini Sutras, KP Readers, Tajika, Bhagavad Gita/Upanishads,
Samudrika, Vastu, Brihat Samhita, astronomy corpus.** Acquisition, not engineering.

### BP §3 — the ten-stage ingestion workflow

| Stage | Status | Note |
|---|---|---|
| 1 Acquire, record rights | `PARTIAL` | no rights/licence metadata |
| 2 Preserve + SHA-256 | `ABSENT` | no hash stored |
| 3 OCR with coordinates | `DONE` | |
| 4 **Human verification** | `ABSENT` | BP's own warning: "never let unverified AI extraction become canonical". 376 rules are validator-clean and human-unread. |
| 5 Segment | `DONE` for BPHS, `ABSENT` for 21 books |
| 6 Normalize (original/translit/translation separate) | `DONE` for BPHS |
| 7 Classify tradition/school/domain/authority | `PARTIAL` | all 398 rules are `parashari`/`classical`; no authority tier on `rule` |
| 8 Extract rules + conditions + modifiers + exceptions | `DONE` for BPHS vol 1 |
| 9 Expert review | `ABSENT` | approval script exists; no expert has run it |
| 10 Publish versioned | `PARTIAL` | `rule.version` + `uq_rule_key_version` exist |

### BP §4 — the five-level ontology

`PARTIAL`, effort `M`. Level 3 (concept) is `astro/vocab.py`. Level 4 (life domain) is
`LIFE_DOMAIN_KEYS`. Levels 1 (universe), 2 (school/tradition) and 5 (question/application:
potential / timing / strength / compatibility / event / remedy) are absent — and level 5 is
what would let a "when" question be answered differently from a "whether" question.

### BP §5 — Book × domain × concept mapping

`PARTIAL`, effort `M`. Book-level slugs and hand-set authority exist. The doc requires
"every chapter/verse/rule mapped to its domain nodes"; we have per-rule `life_domains`
(free text, 105 distinct values over 376 rules) and no concept mapping.

### BP §6 — the Koonji rule format

`PARTIAL`, effort `S` for the missing fields. Field by field:

| BP §6 field | Status |
|---|---|
| `RULE_ID` | `DONE` — `rule_key` + `version` |
| `SCHOOL` | `DONE` — column exists (uniformly `parashari`) |
| `DOMAIN` | `PARTIAL` — free-text `life_domains`, uncontrolled |
| `CONCEPTS` | `ABSENT` — **never extracted**; derivable from atoms |
| `CONDITIONS` | `DONE` — machine-readable, compiled to `rule_atom` |
| `MODIFIERS` | `PARTIAL` — extracted; only `cancel` is honoured at match time |
| `TIMING` | `DONE` — `activation_factors` evaluated by `satisfies` against the running Vimshottari periods, all five levels |
| `EXCEPTIONS` | `DONE` — extracted and honoured by `applies()` |
| `RESULT` | `DONE` — `effects[]` with polarity/strength/statement |
| `SOURCE` | `DONE` — book, chapter, verse, page span |
| `AUTHORITY` | `ABSENT` — no S0–S5 tier on `rule` (`knowledge_item` has one) |
| `VALIDATION` | `ABSENT` |
| `VERSION` | `DONE` |

### BP §7 — rule families the engine must understand

| Family | Status | Note |
|---|---|---|
| Graha, Rashi, Bhava, Lagna | `DONE` | |
| Drishti | `DONE` | Parashari, explicitly named as a choice in `chart/relations.py` per BP §7's warning |
| Dignity | `DONE` | exaltation/debilitation/moolatrikona/own sign |
| Nakshatra | `PARTIAL` | computed and tokenised; no Tara relationships |
| Varga | `PARTIAL` | **computed for display, not tokenised** — no varga rule can match |
| Yoga | `ABSENT` | no yoga recognition. Blocks ER §17 and ARTHA/KARMA entirely. |
| Dasha | `PARTIAL` | computed exactly; never joined to rules |
| Transit | `PARTIAL` | computed; never joined to rules |
| Shadbala / Avastha | `ABSENT` | `BLOCKED` — vocabulary excludes it by decision (194 declines) |
| Ashtakavarga | `PARTIAL` | computed for display only |
| Jaimini | `BLOCKED` | no corpus, not in vocabulary |
| KP | `BLOCKED` | no corpus, not in vocabulary |
| Prashna | `PARTIAL` | chart yes, rules no |
| Tajika | `BLOCKED` | no corpus |
| Muhurta | `PARTIAL` | panchanga yes, electional rules no |
| Nadi | `PARTIAL` | Deva Keralam vol 1 ingested, pages-only |
| Cross-system comparison | `ABSENT` | |

### BP §8 — the twelve reasoning rules

| # | Rule | Status | Note |
|---|---|---|---|
| 1 | Never interpret one factor in isolation | `PARTIAL` | multi-atom conditions yes; no corroboration requirement |
| 2 | **Separate potential from timing** | `DONE` | timing atoms are moved out of `formation` at extraction AND evaluated at query time; the answer distinguishes a promise from a running period, and `active=None` keeps "no period recorded" distinct from "not running" |
| 3 | Separate calculation from interpretation | `DONE` | the strongest part of the build |
| 4 | Hierarchy of evidence | `PARTIAL` | page authority weights; no rule-level tier |
| 5 | Never mix schools silently | `PARTIAL` | `school` column exists; only one school present, so untested |
| 6 | Track conditions and exceptions | `DONE` | |
| 7 | Multiple confirmations for high-stakes | `ABSENT` | a single rule can carry an answer |
| 8 | Don't turn correlations into certainties | `PARTIAL` | prompt hedging + `match/safety.py`; no numeric confidence |
| 9 | Backtest before promotion | `ABSENT` | approval is human judgement, unmeasured |
| 10 | Source every canonical claim | `DONE` | chapter, verse, page span |
| 11 | Version every rule | `DONE` | |
| 12 | Preserve disagreements | `ABSENT` | no contradiction detection |

### BP §9 — the worked marriage example

The flow you pasted. Stage by stage:

| Stage | Status |
|---|---|
| User question | `DONE` |
| Intent = Marriage + Timing | `PARTIAL` — topic yes; a timing intent now reorders retrieval toward rules whose period is running, but does not yet compute the *window* (start/end dates) |
| Relevant concepts (7th/7L/Venus/Jupiter/D9/Darakaraka/Upapada) | `PARTIAL` — the Parashari half is now live (7th, 7th lord, Venus, Jupiter); D9 needs varga tokens and Darakaraka/Upapada are blocked |
| Select schools (Parashari + Jaimini + KP + Nadi) | `BLOCKED` — one school exists |
| Calculate chart facts | `DONE` |
| Retrieve Koonji rules | `DONE` |
| Apply conditions / modifiers / exceptions | `PARTIAL` — conditions and exceptions yes; non-cancelling modifiers ignored |
| Run timing engines | `ABSENT` |
| Compare signals (convergence / conflict) | `ABSENT` |
| Backtest-informed confidence | `ABSENT` |
| Master synthesis | `ABSENT` |
| LLM explains with traceability | `PARTIAL` — the UI panel cites; measured 0 of 6 rules cited in prose |

Roughly 4 of 12 stages.

### BP §10–11 — knowledge graph and three retrieval systems

`ABSENT` (graph), `PARTIAL` (retrieval). Effort `L`.

Vector: `DONE`. Structured SQL: `DONE` (`rule_atom` + `MATCHABLE_PREDICATE`). Graph:
nothing. The doc's example path — `7th Lord → Marriage → D9 → Darakaraka → Upapada → Dasha
→ Transit → Event Window` — is unanswerable, and three of its seven hops are blocked at the
vocabulary level regardless.

### BP §12 — source authority and conflict engine

`PARTIAL`, effort `M`. Book-level authority exists as a hand-set table. The S0–S5 tier
scheme is not applied to rules. Conflict storage and resolution policy: absent.

### BP §13 — deterministic calculation engine

`DONE`, with two gaps. Time/location/planets/lagna/zodiac/nakshatra/varga/dasha/transit/
panchanga/ashtakavarga all compute deterministically and locally. **Shadbala: absent.**
**Audit (BP's "every calculation stores inputs, configuration and engine version"):
absent** — nothing is persisted per calculation.

### BP §14 — other modalities as first-class

`PARTIAL` for numerology, `BLOCKED` for palmistry/face/Vastu. Covered under ER §13.

### BP §15 — the validation lab

`ABSENT` across all ten test layers. Effort `XL`. Rule unit tests, historical backtest,
blind test, temporal holdout, cross-school, calibration, ablation, adversarial, expert
review, regression suite.

One partial: `review_task` has an `is_blind_sample` column, so the schema anticipated
blind evaluation. Nothing populates it.

### BP §16 — birth-time rectification

`ABSENT`, effort `XL`. Not requested by the product yet.

### BP §17 — remedies, source-grounded only

`ABSENT`, effort `M`. `tejan` is the remedy persona with no remedy corpus; BPHS remedy
chapters route to destination B by triage. The doc requires a separate remedy corpus
recording which tradition recommends each practice.

### BP §18 — the LLM's job

`DONE` on the "must not" column, which is the important half. The LLM does not calculate,
does not invent placements, cannot override the matcher. Two "may" items unmet: *summarize
uncertainty* (no confidence to summarize) and *hide conflicts* (no conflicts detected).

### BP §19 — the production answer contract

`PARTIAL`, effort `L`. Of 14 required internal items:

```
 1 Question intent              DONE
 2 Chart/calculation facts      DONE
 3 Selected school(s)           PARTIAL   one school, never stated
 4 Relevant concepts            DONE      (Tier 1)
 5 Applied Koonji rules         DONE
 6 Conditions/modifiers         PARTIAL
 7 Exceptions                   DONE
 8 Source citations             DONE
 9 Cross-school agreement       ABSENT
10 Timing calculation           ABSENT
11 Evidence/validation level    ABSENT
12 Final synthesis              ABSENT
13 Uncertainty / caveats        PARTIAL
14 Human-readable explanation   DONE
```

7 of 14 present.

### BP §20 — implementation backlog

| Workstream | Definition of done | Status |
|---|---|---|
| Corpus | registry with provenance and rights | `PARTIAL` |
| OCR | verified text, page/verse aligned | `PARTIAL` (unverified) |
| Ontology | versioned taxonomy | `PARTIAL` |
| Koonji | IDs, conditions, exceptions, sources | `DONE` for one book |
| Graph | queryable | `ABSENT` |
| Calculator | reproducible, independently checked | `PARTIAL` (no independent check) |
| School engines | isolated and testable | `PARTIAL` (one school) |
| Router | questions → domains, concepts, source sets | `DONE (Tier 1)` |
| Evidence | source tier + validation state on rules | `ABSENT` |
| Backtesting | unseen datasets, blind framework | `ABSENT` |
| Synthesis | combines without merging doctrines | `ABSENT` |
| LLM | explains only what the engine establishes | `DONE` |
| Governance | auditable, reversible rule changes | `PARTIAL` |

### BP §21 — the gold standard rule

> If Rishivan cannot show how an important conclusion travels from user question →
> calculation → rule → source → validation → final explanation, the engine is not finished.

`PARTIAL`. The chain holds from question through calculation, rule and source: the UI
shows the citation, the verse, and the plain-language reason each rule fired. **The
validation link is entirely missing**, and by the doc's own test that means not finished.

### BP §22 — final directive

Not a requirement, but the sentence that judges the rest: *"the goal is not to possess the
world's largest folder of astrology PDFs."* Measured against it we hold 22 books and have
turned **one** of them into rules, so on the doc's own terms we are closer to the folder
than to the architecture. The build order it prescribes — corpus → registry → verified text
→ domain map → concepts → Koonji → graph → calculation → school engines → validation →
synthesis → LLM — is the order the sequencing in §5 follows, with one deviation: Koonji
came before the domain map and the concept layer, which is precisely the inversion this
document is about.

---

## 3b. Chart-understanding council architecture (added 2026-08-25)

Spec: `docs/superpowers/specs/2026-08-25-chart-understanding-council-architecture.md`.
Five phases; phase 1 is done.

| Blueprint § | Item | Status | Where |
|---|---|---|---|
| — | Council pipeline as a graph, every branch a tested edge | `DONE (Phase 1)` | `rishivan/graph/` — 133 tests, `council_consult` 564 → 81 lines |
| §6 | Chart-understanding engine — planet/house diagnosis before prose | `DONE (Phase 2)` | `rishivan/chartstate/` — 98 tests, `chart_state` node in the graph |
| §6 | Functional benefic/malefic — as diagnosis | `DONE (Phase 2)` | `chartstate/functional.py`, Parashari framework, namespaced |
| §6 | Functional benefic/malefic — as a Koonji predicate | `BLOCKED` | Needs a general kendra/trikona doctrine verse. The corpus holds only lagna-specific commentary (Bhavartha Ratnakara ch1); generalising it is the scope inflation the extractor's validator exists to catch. So `functional_nature` stays `derived` and unsatisfied, and rules resting on it still evaluate INDETERMINATE. **Corpus acquisition, not engineering.** |
| §6 | Shadbala / selected strength system | `PARTIAL` | `chartstate/strength.py` ships Sthana + Dig + affliction, `is_estimated=True`, scalar withheld from claims. Chesta and Kaala need ephemeris work not done here. The Koonji `strength`/`strength_band` predicates are still unemitted. |
| §7 | Varga engine — purpose, method, evidence tier per varga | `DONE (Phase 3)` | `rishivan/varga/policy.py` — all 16, method cited, tier assigned |
| §7 | Birth-time confidence gate on high-sensitivity vargas | `DONE (Phase 3)` | Floors derived from arc, not asserted. Per-chart boundary rescue keeps D9/D10 usable at quarter precision when the chart is safely mid-division. Withheld vargas carry a user-facing reason. |
| §8 | Promise → activation → trigger → peak → fading windows | `DONE (Phase 3)` | `rishivan/timing/windows.py`. `promise=False` returns every stage as None — a hard gate, not a low score. |
| §8 | Period → activated houses / karakas / significators | `DONE (Phase 3)` | `timing/activation.py` — owns > occupies > aspects, plus karaka houses and nakshatra dispositorship. Yogas still await Phase 4. |
| §11 | Eight Rishis as reasoning roles returning structured evidence | `ABSENT` (Phase 4) | The eight personas are a different taxonomy and write prose |
| §12 | Per-domain evidence hierarchies | `ABSENT` (Phase 4) | One retrieval path serves every question — the "generic scoring formula" §12 rejects |
| §19 | AnswerPlan / AllowedClaims gate, prediction ledger | `ABSENT` (Phase 5) | Also unblocks checkpointing: a generator in state cannot be serialised |

---

## 4. Blocked on acquisition or a vocabulary decision

Engineering cannot start on these. Listed by how much they unblock.

| Blocker | Unblocks | Kind |
|---|---|---|
| **benefic/malefic** as a vocabulary class | 195 declines — the single largest. ARTHA's coverage explicitly names "benefic/malefic influence" | vocabulary decision, `M` |
| **Divisional-chart tokens** | six of eight Rishis name a varga (D9 Prema, D2/D10 Artha, D10 Karma, D7/D12 Vansh, D4 Yatra). Charts already compute; only tokenising is missing | engineering, `M` |
| **Avastha / combustion** | 150 declines | vocabulary decision, `M` |
| **Shadbala / strength** | 44 declines; named in ARTHA and KARMA coverage | research + vocabulary, `L` — BP notes implementations genuinely disagree |
| **Yoga recognition** | ER §17 in full; ARTHA and KARMA coverage | engineering, `L` |
| **Jaimini corpus** (Sutras, commentaries) | Darakaraka, Upapada, Arudha, Karakamsha, Chara Dasha — named in 6 of 8 Rishi coverage lists | **acquisition** |
| **KP corpus** (Readers I–VI) | sub-lords, significators, KP timing — named in 4 Rishi coverage lists | **acquisition** |
| **Gita / Upanishads / Yoga Sutras** | **DHARMA Rishi's entire core corpus.** Right now Dharma can only speak from 9th/12th-house indicators, which ER §11 explicitly separates from scripture | **acquisition** |
| Tajika corpus | annual charts, Muntha, Sahams | **acquisition** |
| Samudrika, Vastu corpora | palmistry, face reading, Vastu modalities | **acquisition** |

---

## 5. Recommended sequencing

Ordered by evidence-per-unit-effort, given the corpus we hold.

**Tier 1 — DONE except extraction (`2a765f1`)**

1. **Extract BPHS vol 2.** 489 rule-destined units already triaged, zero extracted. ~34
   min, ~$0.78, roughly doubles the rule base. Nothing to design. `S` — **outstanding**
2. ~~Rishi Constitutions as objects~~ — `council/constitution.py`
3. ~~Concept-overlap relevance~~ — `rag/relevance.py`, coverage as a gate
4. ~~Routing test from ER §12's 13 examples~~ — `tests/council/test_routing.py`
5. ~~Transcribe ER §15's Book × Rishi matrix~~ — `council/source_matrix.py`

**Tier 2 — the doc's own priorities, moderate effort**

6. **Secondary Rishis contribute evidence** (ER §1, §12), not just a prose voice. `M`
7. **Tokenise divisional charts** — unblocks six Rishis' stated coverage; the charts
   already compute. `M`
8. ~~**Timing: join dasha to `timing.activation_factors`**~~ — `DONE`. The chart emits
   `dasha.{maha,antar,pratyantar,sookshma,prana}.lord`, the embedder publishes
   `activation`, and `satisfies` evaluates it. What remains is the *window*: a rule can
   now say its period is running, not when the period starts and ends.
9. **`CONCEPTS` and `AUTHORITY` on rules** (BP §6). `S`
10. **Answer contract** (BP §19): concepts, school, timing, uncertainty into the structure. `L`

**Tier 3 — larger, and partly gated**

11. Yoga recognition. `L`
12. Cross-Rishi comparison and master synthesis. `L`
13. Benefic/malefic + avastha in the vocabulary — biggest single yield increase, but a
    fact-engine change. `M`
14. Knowledge graph. `L`
15. Validation lab — required by BP §21 before any "finished" claim. `XL`

**Not startable without acquisition:** Jaimini, KP, Tajika, the Dharma scripture corpus,
Samudrika, Vastu.

---

## 6. The one-sentence version

The build implements BP §9's left half — question → intent → chart facts → Koonji
retrieval → exact condition test → cited answer — correctly and deterministically, for one
book. What it is missing is the **concept layer**: nothing in the system knows that a
marriage question needs the 7th house, Venus and D9, which is why relevance is decided by a
free-text tag and why the wrong rules reach the answer. Everything in Tier 1 exists to fix
that, and most of Tier 2 depends on it.
