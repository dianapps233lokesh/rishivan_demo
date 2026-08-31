# Rishivan — Council of Rishis (Demo)

A Vedic astrology consultation demo. Eight Rishi personas answer questions in
plain language, grounded in 15 classical texts and in charts computed with the
Swiss Ephemeris.

Self-contained: it depends on nothing from the main Rishivan backend and is
ready to deploy to Streamlit Community Cloud as its own repository.

---

## Three reading lanes

The app answers on one of three lanes, chosen with the **Reading lane** control
above the question box. All three compute the chart the same way — Swiss
Ephemeris owns every placement and every date in all of them.

| Lane | Calls | What grounds the answer |
|---|---|---|
| **Council** | classify + 8 Rishis + audit + narrate | Retrieved book pages and matched rules |
| **Direct — one call** | classify + read | The chart, plus the classical *method* written into the prompt |
| **Direct — two calls** | classify + reason + narrate | The same, split across two models |

**The two-call lane is the one to reach for when accuracy matters.** `pro`
(`gemini-3.1-pro-preview`) works out what the chart carries and returns it as a
structured verdict — the answer in a sentence, each computed factor paired with
the consequence it licenses, the periods that bear on it in exact dates, the
disagreements, a falsifier. A gate written in plain Python then removes anything
that does not trace back to a computed fact: a window whose dates the prompt
never printed, a past period, any window at all when the chart does not carry
the thing asked about. `flash` writes the answer from what survives and **never
sees the chart** — so it cannot assert a placement it was never shown, and
because ISO dates are converted to months before it is called, it cannot write a
day-exact forecast either.

What it costs: roughly double the latency, and `pro` tokens instead of `flash`
for the reasoning half. What it buys is visible in the app — open *What the
reasoning call decided* under any two-call answer to see the findings and,
below them, anything the gate removed before the narrator saw it.

Only the one-call lane's prompt pastes usefully into ChatGPT or Gemini for a
side-by-side comparison; the two-call lane asks for JSON. Both prompts come from
the same builder and differ only in their closing OUTPUT block, so the
comparison stays honest.

## What a question requires

Which facts a reading is built from is a **table**, not a hardcoded block order.
One document per (life domain × question kind), living in the MongoDB the app
already talks to, so what a marriage question needs can be changed without a
redeploy.

```bash
python -m scripts.seed_requirements --dry-run   # what would be written
python -m scripts.seed_requirements             # write it
python -m scripts.seed_requirements --check     # diff Mongo against the code
```

Each row names its facts in the **existing** `rishivan/astro/vocab.py` grammar —
`house.7.lord.house`, `d9.house.7.lord.house`, `from_moon.house.7.lord.house` —
validated at seed time, because a misspelled token is a requirement nobody can
satisfy and nobody notices. Most of a row is derived from
`CONSTITUTIONS[<key>]` rather than transcribed, so the houses a marriage reading
rests on come from `prema.primary_houses` and cannot drift from it.

Three things the table controls:

- **Which facts get computed and sent.** The domain decides. Before this it did
  not: `question_profile` keyed on question *kind* only and used the domain
  solely to build a log string, so a marriage timing question and a career
  timing question received byte-identical facts.
- **The order and the emphasis.** Requirements render in three bands — `RULE ON
  THIS`, `CORROBORATE`, `CONTEXT` — sorted inside each band by which step of the
  constitution's classical protocol they serve.
- **What is declared missing.** A requirement nothing can compute, or a
  mandatory one this chart does not yield, is stated to the model against the
  protocol step it served: *"step 4 (D9 confirmation): the D9's placements —
  required for this question, and this chart does not yield it."* The reading
  works that step from what it has instead of padding it.

If Mongo is unreachable the app runs on the built-in catalogue in
`council/requirements/catalog.py` — fully specified, and both the UI and the
trace say so, because a demo silently running on the fallback while somebody
edits Atlas is a confusing afternoon.

## What it does

- **Routes** each question to one of eight Rishis, and decides which chart to
  cast (natal / muhurta / prashna / general) in a single model call.
- **Computes** rather than guesses — birth charts, Vimshottari dashas to the
  pratyantar level, all five panchang limbs (tithi, vara, nakshatra, yoga,
  karana, each with the moment it gives way), the daily windows (Rahu Kaal,
  Yamaganda, Gulika, hora) and the muhurta tables (Choghadiya, Abhijit) come
  from the Swiss Ephemeris and are passed to the model as ground truth it may
  not alter. **The date is an input, never something recalled** — `FLG_MOSEPH`
  needs no data files and is valid for millennia either side of today, so
  nothing here depends on a training cutoff.
- **Retrieves** relevant pages from a 15-book corpus in Qdrant (40k+ passages),
  filtered to the books that Rishi is qualified to draw on.
- **Cites** real book titles and page numbers in the interface, and shows the
  source text, so any claim is checkable.
- **Remembers** the conversation, so a follow-up like "tell me more" continues
  with the same Rishi and opens the thread it offered.

---

## Deploying to Streamlit Community Cloud

### 1. Push this folder to GitHub as its own repository

```bash
cd rishivan_demo
git init -b main
git add .
git commit -m "Rishivan Council of Rishis demo"
git remote add origin git@github.com:<org>/<repo>.git
git push -u origin main
```

> Confirm `git status` shows no `.streamlit/secrets.toml` before committing.
> It is gitignored, but check — it holds live credentials.

### 2. Create the app

On [share.streamlit.io](https://share.streamlit.io) → **New app**:

| Field | Value |
|---|---|
| Repository | `<org>/<repo>` |
| Branch | `main` |
| Main file path | `streamlit_app.py` |

### 3. Add the secrets

**Settings → Secrets**, pasted as TOML. See
`.streamlit/secrets.toml.example` for the full template.

Required:

```toml
QDRANT_URL = "https://<cluster>.qdrant.io"
QDRANT_API_KEY = "..."
VECTOR_COLLECTION = "rishivan_docs"
```

Then Vertex AI (needs billing enabled):

```toml
GCP_PROJECT_ID = "..."
GCP_LOCATION = "global"
GCP_SERVICE_ACCOUNT_EMAIL = "svc@project.iam.gserviceaccount.com"
GCP_PRIVATE_KEY_ID = "..."
GCP_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n"
```

`GCP_PRIVATE_KEY` must stay on one line with literal `\n` escapes, exactly as
it appears in the service-account JSON. The app converts them.

If anything required is missing the app says which key, on screen, instead of
failing somewhere in the pipeline.

---

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # then fill it in
streamlit run streamlit_app.py
```

Environment variables work too, if you prefer a `.env`-style setup — settings
read Streamlit secrets first, then the environment.

---

## Layout

```
streamlit_app.py            # entry point: input, streaming answer, citations
requirements.txt
scripts/                    # the pipeline, one command per stage
.streamlit/
  config.toml               # dark theme matching the app's styling
  secrets.toml.example      # template (the real file is gitignored)
rishivan/
  config.py                 # secrets/env settings, with a startup check
  astro/                    # the fact vocabulary — the join key, single source of truth
  db/                       # SQLAlchemy engine and declarative base
  models/                   # ORM tables: books, units, rules, atoms, triage
  knowledge/                # offline: book -> rule base
    bridge/                 # pages -> chapters -> verses
    triage/                 # rule-bearing verse, or not
    extract/                # verse -> structured rule (the one AI step) + validator
    compile/                # condition -> indexed atoms, then load to Postgres
    affinity/               # rule -> Rishi weights
    match/                  # exact condition test, plus the safety gate
  chart/                    # Swiss Ephemeris: placements, facts, tokens, dignity, dasha
    jaimini.py              #   chara karakas and the arudha padas (Upapada)
    dosha.py                #   Mangal (Kuja) dosha, from lagna, Moon and Venus
  rag/                      # Qdrant store, page retrieval, rule retrieval and ranking
  council/                  # classifier, orchestrator, personas, prompts
    requirements/           #   what each question requires: Mongo + a code fallback
      catalog.py            #     the authored source, composed from the constitutions
      store.py              #     the loader, and which carrier it used
      producers.py          #     one requirement key -> one block of prompt text
    direct_prompt.py        #   the direct lanes' prompt: one builder, two tails
    analyse.py              #   the pro call -> a structured verdict
    verdict.py              #   that verdict's shape, and the gate over it
    narrate_verdict.py      #   the flash call -> prose, from the verdict alone
```

---

## Notes for whoever demos this

- **~20-25 seconds per answer**, and roughly double that on the two-call lane,
  because the reasoning call has to finish before a word can be streamed.
  Streaming starts near the end, so it feels longer than it is. Worth mentioning
  before it is noticed.
- **The two-call lane needs `gemini-3.1-pro-preview` enabled** on the Vertex
  project. If it is not, every reasoning call fails and the lane says so rather
  than quietly answering from the one-call prompt.
- **Daily timings default to New Delhi.** There is no city selector yet, so
  Rahu Kaal, sunrise and every muhurta window are wrong for other cities. Say so
  if asked — the arithmetic is right, the coordinates are assumed.
- **Muhurta is a table, not the model's opinion.** Choghadiya and Abhijit are
  computed and then crossed against Rahu Kaal, Yamaganda and Gulika, so a "good"
  hour sitting inside an inauspicious window is reported as colliding rather
  than recommended. The engine ranks and gives reasons; it never returns a bare
  yes or no, because the reason is the part a seeker can act on.
- **No scripture in the corpus.** The app is explicitly barred from quoting the
  Gita or the Upanishads, because it does not have them and any quotation would
  be invented. Frame this as an honesty guarantee.
- **15 of the blueprint's 22 knowledge layers are not ingested** — numerology,
  Vastu, dreams, Lal Kitab, KP, Jaimini. Roadmap, not defect.
- **First load is slow.** Streamlit Cloud builds `pyswisseph` on cold start;
  expect a couple of minutes on the very first deploy.

---

## Data it expects

**Two** Qdrant collections, both 768-dimension. The app only reads; ingestion
lives in the main Rishivan backend and in `scripts/`.

| Collection | Holds | Payload keys |
|---|---|---|
| `rishivan_docs` | book pages, for passage retrieval | `document_id`, `page_number`, `element_index`, `book_slug`, `book_domain` |
| `rishivan_docs_rules` | compiled Koonji rules, for exact matching | `rule_key`, `condition`, `effects`, `source`, `life_domains`, `rishi_affinity`, `modifiers`, `exceptions`, `remedies`, `activation`, `school`, `rule_category`, `tier` |

The rules collection name is derived, not configured: `VECTOR_COLLECTION` plus
`_rules`. Setting `VECTOR_COLLECTION` alone points both lanes at the right place.

### The rules collection must be current

`activation` — the atoms that say WHEN a rule fires — was added after some
collections were built. A collection missing it still answers, and every rule
silently reports "no activating period", so no reading can distinguish a natal
promise from a period running today.

Re-publish it from a machine that can reach **both** Postgres and Qdrant (the
embedder reads approved rules from Postgres; Streamlit Cloud never touches it):

```bash
python -m scripts.embed_rules --dry-run   # check the count first
python -m scripts.embed_rules
```

Verify in the deployed app: ask a "when" question and open the rules panel. It
must read *"N of them record an activating period"*. If it says *"No rule in
this collection records an activating period"*, the collection is stale.
