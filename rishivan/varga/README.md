# Varga policy — which divisions may speak

Blueprint §7: *"Do not use every Varga merely because it exists."* And:
*"The engine should not present false precision."*

Sixteen divisions are computable. Which ones a question actually gets depends on
its domain and on how much of the birth time is genuinely known.

## The problem this solves

`BirthData` records `hour`/`minute`/`second` and says **nothing about
precision** — which is the input the whole no-false-precision discipline needs.

D60's arc is **0.5°**. Hour-level uncertainty moves the ascendant about
**7.5°** — fifteen divisions. A D60 reading on a time recorded as "12:00" is
noise wearing a decimal point.

So precision is inferred from how *round* the recorded time is (`4:37` was read
off something; `12:00` and `4:30` were rounded; `00:00` is what a form defaults
to when nobody typed anything, and reads as UNKNOWN), and the caller may
override — which is what a rectified chart does.

## The gate is arithmetic

`min_confidence_for_arc(arc)` returns the coarsest confidence whose ascendant
uncertainty fits inside one division. Written as arithmetic rather than a lookup
table, so adding D81 needs no judgement call.

| Varga | Arc | Needs |
|---|---|---|
| D1 | 30.00° | HOUR |
| D2 | 15.00° | HOUR |
| D3 | 10.00° | HOUR |
| D4 | 7.50° | HOUR |
| D7 | 4.29° | QUARTER |
| D9 | 3.33° | MINUTE |
| D10 | 3.00° | MINUTE |
| D12–D45 | 2.50°–0.67° | MINUTE |
| D60 | 0.50° | MINUTE |

**Even D1 needs a known hour.** An UNKNOWN time is ~180° of ascendant
uncertainty — the lagna could be any of twelve signs, so nothing house-based
survives it. What does survive is the sign layer: planets in rashis, dispositors,
conjunctions. The blueprint's "D1 always primary" is a claim about that layer.

## The rescue, and why it exists

A blunt floor is wrong in the other direction. D9 and D10 are **mandatory**
cross-checks, and both need MINUTE — so a blunt gate withholds them from anyone
who says "half past four", which is most people.

But the uncertainty only bites when a body sits near a division boundary. One
step below the floor, `select_vargas` checks *this* chart: if every graha and the
ascendant clear the nearest edge by more than the uncertainty, the varga is
admitted and the answer says on what basis. Two steps below, never — a rescue is
for the margin, not for an unknown birth time.

## Withholding is the product

```python
select_vargas(chart, "domain.career", BirthConfidence.HOUR)
# selected : D1
# withheld : D10 (Dashamsha) needs a birth time known to the minute; yours is
#            recorded to the hour, which could move it by 7.5° against a 3.00°
#            division. I have not used it.
```

That sentence is not an error path. It is a thing no astrology app says, and it
cannot be said by a pipeline that silently drops the varga.

## Every policy cites its method

Divisional schemes are exactly where authorities diverge — D30 alone has three
common constructions — so `method_source` is required. A policy naming a method
it cannot cite is a policy nobody can check.

`Usage.VALIDATED_ONLY` (D27) is **not served**. The blueprint says "use only with
validated methodology"; until that validation exists, the honest reading is: not
yet.
