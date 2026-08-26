"""Koonji — the knowledge engine: books -> rules -> firing on a chart.

Scope is deliberately the engine only. Rishis, UI and billing sit on top of
this later and are not imported from here.

The through-line, restated in every planning document and enforced structurally
in this package: move work out of the model and into deterministic, versioned,
compiled artifacts.

    urf.py        the frame — 7 assertion kinds, closed. Everything else grows.
    registry.py   the open registries. Additive only, ever.
    corpus.py     the ingested books -> passages with context
    convert.py    the earlier extractor's output -> the frame, no model calls
    emit.py       Rule -> the YAML a reviewer edits. Inverse of parse_rule.
    pipeline.py   books -> rule files, both paths, through one compiler gate
    question.py   the parsed question — closed envelope, open payload
    router.py     text -> QuestionSpec -> the retrieval filter
    facts.py      Chart -> ground fact atoms
    vm.py         antecedent evaluation + derivation tiers
    index.py      atom -> rules, exhaustive set-containment retrieval
    compiler.py   YAML rule sources -> a signed, content-addressed bundle
    evidence.py   firings -> claims, with restatements discounted
    engine.py     the whole path, wired

The filter deserves a word, because it is the one place where being clever
costs recall. `index.query` narrows by domain, school and status before it looks
at a single chart atom, and every narrowing is a chance to exclude a rule that
should have fired — invisibly, because an answer missing a rule still reads
fine. So the filter is built to fail open: an untagged rule survives every
domain filter, an unrouted question reads the whole corpus, and a filter that
admits nothing at all is widened and the widening recorded.

No module here calls a language model. Extraction is quarantined in `extract.py`
(orchestration) and `client.py` (the only networked thing in the package), and
neither runs in the serving path. `extract.py` takes its client by injection, so
a pod that never extracts never imports `google.genai`.

Books become rules two ways, and they meet at the same gate:

    convert   already-extracted JSONL -> documents    deterministic, free
    extract   the verses, re-read      -> documents    six model calls a passage
                                    |
                    compile (9 passes) + emit/parse round trip
                                    |
                            rules/converted/*.yaml     status: candidate
                                    |
                                 reviewer
                                    |
                                 production

Neither generator decides what is a rule. The compiler does, and what it drops
is printed with the diagnostic that dropped it.
"""
