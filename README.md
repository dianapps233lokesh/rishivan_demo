# Rishivan — Council of Rishis (Demo)

A Vedic astrology consultation demo. Eight Rishi personas answer questions in
plain language, grounded in 15 classical texts and in charts computed with the
Swiss Ephemeris.

Self-contained: it depends on nothing from the main Rishivan backend and is
ready to deploy to Streamlit Community Cloud as its own repository.

---

## What it does

- **Routes** each question to one of eight Rishis, and decides which chart to
  cast (natal / muhurta / prashna / general) in a single model call.
- **Computes** rather than guesses — birth charts, Vimshottari dashas, and
  daily windows (Rahu Kaal, Yamaganda, Gulika, hora) come from the Swiss
  Ephemeris and are passed to the model as ground truth it may not alter.
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
  rag/                      # Qdrant store, page retrieval, rule retrieval and ranking
  council/                  # classifier, orchestrator, personas, prompts
```

---

## Notes for whoever demos this

- **~20-25 seconds per answer.** Streaming starts near the end, so it feels
  longer than it is. Worth mentioning before it is noticed.
- **Daily timings default to New Delhi.** There is no city selector yet, so
  Rahu Kaal and sunrise are wrong for other cities. Say so if asked.
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
