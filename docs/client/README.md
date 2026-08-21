# Client specifications

The two documents this pipeline implements. Vendored because every design decision in
`docs/superpowers/plans/` cites them by section, and a plan whose authority lives in
someone's Downloads folder cannot be checked by the next engineer.

- `blueprint-master-implementation.pdf` — the engine architecture.
  §1 the non-negotiable architecture ("never build PDF → embeddings → LLM → prediction"),
  §6 the Koonji rule format, §7 rule families and the warning that aspect models are
  school-specific, §8 the twelve reasoning rules, §11 three retrieval systems,
  §12 source tiers S0–S5, §15 the validation lab, §18 what the LLM may and may not do,
  §19 the production answer contract, §21 the gold-standard traceability rule.

- `eight-rishis-domain-ownership.pdf` — the Rishi division.
  §3 the eight dimensions, §9 Aarogya's forbidden claims, §12 questions that cross
  multiple Rishis, §13 where numerology/palmistry/muhurta belong, §14 what each Rishi's
  Koonji must hold, §15 the weighted Book × Rishi matrix, §20 "no orphan questions",
  §21 the final naming directive.

## Note on Rishi naming

§21 names the client's eight Rishis ATMA, PREMA, ARTHA, KARMA, VANSH, AAROGYA, YATRA,
DHARMA. This repo keeps its own eight persona names — Agam, Vyom, Dhruvan, Ritam, Tejan,
Medhan, Tattvan, Pragnav — and maps them onto the client's eight through
`RISHI_LIFE_DOMAINS` in `rishivan/council/domains.py`.

That was a deliberate decision, not an oversight. The two sets are different taxonomies
under the same count: `medhan` alone spans three client dimensions, `dhruvan` spans two,
and `vyom`/`ritam`/`tejan` are technique lenses rather than life domains. So the mapping
is weighted and many-to-many, which is how the client expresses its own Book × Rishi
matrix in §15. Extracted rules are annotated with the client's keys, because that is what
the corpus is annotated against; personas reach them through the map.
