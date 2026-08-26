# Timing — a first-class subsystem

Blueprint §8: *"Timing is a first-class subsystem, not an afterthought."*

```
promise → activation → trigger → peak → fading
```

## The promise gate

**`promise=False` returns every stage as `None`.** Not a low confidence. None.

This is the whole point of the module. The dasha arithmetic *always* yields a
period, so a pipeline that starts from the periods will always produce a date —
which is the most common way an astrology product invents a prediction. Starting
from the promise is what makes the honest answer reachable:

> The chart carries no promise for career, so there is no window to give. A
> period would be arithmetic, not a prediction.

The promise comes from the Koonji reading, where it is a fired rule with a
citation. This module *times* a promise; it does not adjudicate one.

## The stages

| Stage | Vimshottari level |
|---|---|
| activation | the mahadasha whose lord activates the domain |
| trigger | an antardasha inside it whose lord also does |
| peak | the pratyantar inside the trigger that does the same |
| fading | the tail of the activation after the trigger closes |

Each narrows the one above: the mahadasha says the decade, the antardasha the
year, the pratyantar the months. Exact boundaries come from `chart/dasha.py`,
which already walks five levels — nothing here re-derives them.

```
Saturn mahadasha activates the 6th, 7th, 10th, 11th — Aug 2026 – Aug 2036.
Saturn antardasha sharpens it — Aug 2026 – Feb 2027.
Rahu pratyantar is the sharpest of it — Aug 2026 – Sep 2026.
The activation runs on afterwards, fading — Feb 2027 – Aug 2036.
```

## Activation is the join

Without it, "Saturn mahadasha" is a fact about the calendar rather than about the
question. Three ranked ties — **owns** > **occupies** > **aspects** — plus two
that travel with the graha regardless of placement: its karaka houses, and any
graha sitting in a nakshatra it lords.

A house tied two ways keeps the stronger tie. An unmapped domain activates
nothing: a period that activates everything activates nothing, and defaulting to
"yes" is how a timing engine produces a window for any question asked of it.

## Systems are not blended

`TimingReport.by_system` keeps each dasha system under its own key and
`agreement()` *reports* concurrence rather than folding it in. Two systems
agreeing is evidence a reviewer can weigh; two averaged is a number nobody can
check, endorsed by no tradition.

## Two guards that earned themselves

**`DateRange` refuses an inverted span.** It caught a real logic error during
development: the peak search was filtered by membership in the antardasha rather
than by the *clipped* trigger, so a pratyantar entirely before the horizon
produced a window running backwards.

**Nothing reads the clock.** A backtest asks about 1998 and a Prashna asks about
a stated moment. An engine that quietly answers about today is wrong in a way
that produces plausible output.
