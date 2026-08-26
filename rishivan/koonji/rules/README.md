# Rule sources

Rules are code. They live in Git, are reviewed as pull requests, and are compiled
by `koonji.compiler` into a signed bundle. They are not edited in a web form
against a live database — a knowledge base you cannot diff, blame, revert and
test is one you cannot defend when an astrologer asks why a rule fired.

## Status of this directory

These are **seed rules for the walking skeleton**, not a corpus.

Every `quote:` below is verbatim from this repository's own ingested corpus
(`koonji-bphs-vol1.jsonl`, `koonji/bphs-vol2.jsonl`) with its real chapter and
verse locator. Nothing here is paraphrased and nothing is invented — a fabricated
citation is the single most damaging failure this system can produce, so the
rule was to author only from text actually on disk.

Every rule is `status: candidate`. None has been read by a qualified Jyotish
reviewer, and the compiler refuses to let an unreviewed rule be `production`.
That gate is not decoration: reviewer throughput is the real bottleneck on this
corpus, and `candidate` is the honest state until someone signs.

To serve these, a caller has to ask for them explicitly:

```python
engine.read(chart, statuses=frozenset({"production", "candidate"}))
```

## Known gaps in the seed set

- **No `derive_fact` rule.** Derivation tiers are implemented and tested
  (`tests/koonji/test_vm.py::TestDerivations`), but no defensible source verse
  for temporary friendship or functional nature could be located in the corpus
  on disk. Saravali — the text that states the friendship derivation cleanly —
  is not among the ingested files. Authoring one from memory would have meant
  inventing a locator, so the seed set has none.
- **No named yoga.** Same reason: the Gaja Kesari and Panch Mahapurusha verses
  did not surface in the ingested text.
- **No Shadbala.** The chart layer does not compute it, so rules resting on
  planetary strength evaluate to INDETERMINATE rather than silently failing.

## Authoring format

```yaml
id: BOOK.DOMAIN.SHORTNAME.NNNN     # stable forever; new version, never an edit
version: 1.0.0
status: candidate                  # production requires a reviewer
school: school.parashari
assertion: assert_claim            # one of the seven kinds
domains: {domain.wealth: 0.95}

source:
  book: bphs
  edition: bphs-gcsharma-vol1
  locator: ch23.v13
  quote: "…"                       # must appear verbatim in the passage
  authority_tier: S0
  restates: []                     # drives the independence factor
  review: {reviewer: RB-001, reviewed_at: 2026-08-23}

when:                              # a boolean tree over registered predicates
  all:
    - occupies_bhava: {subject: 10th lord, bhava: 11}

indicates:
  claim: wealth.accumulation
  polarity: positive
  magnitude: strong
  text: "…"
```

Aliases resolve at compile time: `Guru`, `Brihaspati` and `Jup` all become
`graha.jupiter`; `2nd lord`, `lord of the 2nd` and `dhana lord` all become
`lord.bhava.02`. An unresolvable symbol is a hard error, never a guess.

---

## Two tracks

This directory holds rules from two sources, and they never share a file.

```
rules/parashari/    hand-written, eight rules, the walking skeleton
rules/converted/    ~1,100 rules, GENERATED - overwritten on every run
rules/extracted/    written by the model path, also GENERATED
```

A hand edit inside a generated file vanishes the next time the generator runs,
so promotion out of `candidate` happens by **moving** a rule into a reviewed
file, never by editing `status:` in place.

Everything in both generated directories is `status: candidate`. The serving
default is production-only, so none of it reaches a user until somebody signs.

## Generating them

```bash
python -m rishivan.koonji corpus                 # what books are loadable
python -m rishivan.koonji convert                # JSONL -> YAML, no model calls
python -m rishivan.koonji extract --limit 20     # six model calls per passage
python -m rishivan.koonji restatements           # which rules are one rule
python -m rishivan.koonji lint --charts 400      # fire rate, never-fires, co-fire
python -m rishivan.koonji ask --date 1990-01-01 --candidate \
       --question "will I be wealthy?"
```

`convert` reads the earlier extractor's output, which is already on disk and
already paid for. It costs nothing to run and is the fastest way to find out
whether the compiler, the registry and the lints survive a real corpus — every
problem it exposes is one the model path would hit too, at a thousand times the
cost.

Neither generator decides what is a rule. Both emit documents, the compiler runs
all nine passes over them, and only what compiles **and** survives an
emit/parse round trip reaches disk. What was dropped is printed, with the
diagnostic that dropped it.

## What the corpus looks like today

`convert` over all eleven books: **3,093 units → 1,113 documents → 1,109 rules.**
The four it loses are unsatisfiable and the contradiction pass says so.

The lints over 150 reference charts then report ~190 rules firing on more than a
quarter of charts, ~103 that never fire, and ~2,100 co-firing pairs. That is not
a defect in the lints — it is what an unreviewed machine-converted corpus looks
like, and it is the reviewer's worklist. `restatements` groups 857 of those rules
into 222 sets that say the same thing; each set is one piece of evidence, not
several, and the independence factor depends on somebody confirming that.
