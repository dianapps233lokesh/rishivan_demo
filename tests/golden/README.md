# Golden fixtures

## `bphs_adjacency.json` — M1's hard gate

120 Sutra Units sampled from BPHS vol 1 and vol 2, used by
`tests/knowledge/bridge/test_adjacency_gate.py` (`make gate-adjacency`).

Regenerate with:

```bash
uv run python -m scripts.build_golden_units --per-volume 60
```

### Why the sample is not random

A random sample of BPHS units would be mostly easy cases — one verse, one page,
a numbered translation directly beneath — and **a broken bridge would pass it.**
The sample is therefore stratified toward the three things that actually break:

| Stratum | Count | What it guards |
|---|---|---|
| Grouped verse ranges (`12-14`) | 80 | The merge path: BPHS sets several verses as separate blocks under one shared translation |
| Page-spanning units | 80 | Reflow surviving a running head between a verse and its translation |
| Vol 2's `।।` delimiter | 60 | The branch that would otherwise infer 57% of vol 2's verse numbers instead of reading them |
| Simple single-verse, single-page | 40 | The ordinary path, so a gate of only hard cases does not leave the common case unguarded |

(Strata overlap; the counts are not disjoint.)

### The independent cross-check

The strongest assertion in the gate is not the adjacency count — it is
`test_devanagari_and_english_refs_agree`. A unit's reference is derived from
Devanagari markers in the shloka, while the translation carries its own label in
Latin digits. Those are **two independent readings of the same number**, so
agreement is evidence the pairing is correct that does not originate from the
pairing code itself.

Corpus-wide measurement: 963 units carry both, agreement **96.99%**. The 29
disagreements are mostly the OCR confusing Devanagari **१ (1) with ९ (9)** —
`९२` read where `१२` was printed. Those units are flagged `needs_review` rather
than silently corrected, because choosing a winner would overwrite the book.

Vol 2 almost never labels its translations, so only 5 of its units are
cross-checkable. **Vol 2's verse numbering rests on Devanagari markers with no
second opinion**, which is the single largest unquantified risk in the pilot.

### Hand-check status

> **Not yet hand-checked.** The fixture as committed is generator output plus the
> automated cross-check above. A fixture produced by the code it tests only proves
> that code is self-consistent, so the gate is not fully earned until a human has
> read each unit against the scanned page.

When the hand-check is done, record here:

- units read: _____
- corrected: _____
- deleted: _____

The corrected-plus-deleted count over units read **is the bridge's true error
rate**, and it belongs in `docs/reports/2026-08-18-m1-bphs-bridge.md`.
