# The council

Blueprint §11 and §12, as nodes.

## What this package is for

Before Phase 4, "the council" was one model call in one Rishi's voice, producing
prose. Prose cannot be audited: you cannot ask a paragraph which rule it rests
on, whether anything argued against it, or what would change its mind. So this
package makes those questions answerable by making them fields.

```
hierarchy.py        which evidence counts for this kind of question, and how much
rishis/contract.py  what a Rishi returns, and what it may not omit
rishis/roster.py    who is invited, and the gate that keeps the rest out
rishis/prompt.py    what each one is shown
rishis/sakshi.py    the auditor, and the bound that stops it looping
```

## The three decisions worth arguing with

**Rishis receive; they do not retrieve.** One `koonji_read` produces one
evidence graph and each Rishi is handed its slice. The alternative — every Rishi
calling `index.query` itself — is more flexible and destroys the determinism the
whole prefix is built on. The spec left this open (§13, decision 4); this is the
call, and it is reversible by giving `RishiRole` a retrieval budget.

**The names stay.** `agam`, `vyom`, `ritam` and the rest are annotated across the
whole corpus as `rishi_affinity`. Renaming them to `parashara`/`jaimini`/`kala`
would silently change what every one of those annotations means. What Phase 4
added is a *role* per persona, not a new taxonomy.

**Sakshi has no persona.** It audits; it never speaks in a voice. A ninth persona
would break `ALL_RISHI_NAMES` and the no-orphan-domain test for nothing gained.

## `weakening` is required

A `RishiReport` carrying supporting evidence and an empty `weakening` list is
rejected by the contract validator unless `abstained` is set.

This is the single most load-bearing line in the package. Every product on the
market suppresses disconfirming signal because it makes the answer messier, and
a prompt that asks nicely for counter-evidence gets it *most of the time* — where
"most of the time" means the reports that omit it are exactly the ones where the
model was most confident and least examined.

The escape hatch is deliberate and is not "leave it empty". A chart that
genuinely says one thing should say so *in* `weakening`: "no contrary indication
found, and here is what I looked for". That is a statement a reviewer can check.
Silence is not.

## The evidence gate

`route_rishis` invites a Rishi only when rules in a domain it may argue from
actually fired. The router proposes; the evidence disposes.

Inviting a Rishi whose subgraph is empty does not produce an empty report — it
produces confident-sounding filler, because a model asked for an opinion supplies
one. And the filler reads exactly like an opinion, which is why this is a gate
rather than a heuristic.

Capped at `MAX_RISHIS = 5`. The fifth marginal Rishi on a wealth question is
agreeing with the fourth, and agreement between two restatements of the same
evidence is what `evidence.py` already discounts — paying a model to generate it
does not make it independent.

## `Send` replaces the state

`Send(node, arg)` gives the target node `arg` **as** its state. It does not merge
with the outer state. A payload of `{"rishi": "medhan"}` produces a node where
every `state.get("reading")` returns `None`, silently, and the Rishi files a
confident report about a chart it never saw.

Measured on a scratch graph, not assumed. `RishiRole.reads` is what
`route_rishis` copies into the payload, and
`test_the_payload_carries_what_the_role_reads` pins it.

## Six of the auditor's seven hunts are code

| hunt | deterministic |
|---|---|
| a cancellation no report mentioned | yes |
| a claim below its domain's corroboration floor | yes |
| two reports disagreeing in sign | yes |
| a date asserted with no window behind it | yes |
| a house the hierarchy names that nobody examined | yes |
| a council that abstained wholesale | yes |
| an alternative explanation nobody proposed | no — the model's job |

Doing the six in code means the audit still works when the model call fails, and
it means each hunt has a test rather than a hope.

`route_after_sakshi` allows **one** re-examination. An unbounded critic loop is
how a graph hangs in production at 3 a.m., and the bound is a single comparison.

## Synthesis reports; it does not decide

Agreement between two Rishis is stated as agreement. Disagreement survives into
the prose with an explicit instruction not to split the difference — an average
is a position no Rishi held. The same argument `timing/query.py` makes about
dasha systems, for the same reason.

## What this package does not fix

Both are corpus problems, and no amount of graph work closes either:

- **Every rule is `status: candidate`.** None has been reviewed. Reports carry
  `reading_is_unreviewed` and every prompt says so.
- **`functional_nature` and `yogas`** have no general doctrine verses in the
  bridged corpus. Rules resting on them evaluate INDETERMINATE, and the auditor
  is told not to read that as an absent indication.
