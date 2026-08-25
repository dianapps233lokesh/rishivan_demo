"""Dispositor and nakshatra-lord chains, both cycle-safe.

A dispositor chain walks "who owns the sign this planet sits in, and who owns
the sign *that* planet sits in" until it reaches a planet in its own sign. Two
things make it worth its own module:

**It does not always terminate on its own.** Mutual disposition - Sun in Cancer
with Moon in Leo - is a 2-cycle, and longer rings occur. A walker without a
visited set does not fail, it *hangs*, which is the worst way for this to go
wrong: no error, no answer, a request that never returns.

**A cycle is a finding, not an error.** Parivartana is a real and much-discussed
configuration. So `Chain` reports `cycle=True` and returns the ring rather than
raising, and the caller decides what it means.

The nakshatra chain is the same walk over `NAKSHATRA_LORDS`, and the Nakshatra
Rishi (§11) reasons over precisely it.
"""

from __future__ import annotations

from dataclasses import dataclass

from rishivan.astro.constants import RASHI_LORDS, RASHIS
from rishivan.chart.ephemeris import Chart

#: How many hops before we conclude something is wrong with the tables rather
#: than with the chart. Nine grahas cannot produce a simple path longer than
#: nine, so anything past that is a bug, not an exotic chart.
_MAX_HOPS = 16


@dataclass(frozen=True, slots=True)
class Chain:
    """A walk, and whether it closed on itself."""

    path: tuple[str, ...]
    terminus: str
    cycle: bool
    """True when the walk returned to a planet already on the path. Parivartana
    is a real configuration, so this is reported rather than raised - and the
    path is the ring, so the caller can name the planets involved."""


def _bare(graha: str) -> str:
    return graha.removeprefix("graha.").lower()


def _position(chart: Chart, graha: str):
    bare = _bare(graha)
    for name, p in chart.planets.items():
        if name.lower() == bare:
            return p
    raise KeyError(f"{graha!r} is not in this chart")


def dispositor_of(chart: Chart, graha: str) -> str:
    """The lord of the sign this graha occupies."""
    rashi = _position(chart, graha).rashi
    return f"graha.{RASHI_LORDS[RASHIS.index(rashi)]}"


def nakshatra_lord_of(chart: Chart, graha: str) -> str:
    """The Vimshottari lord of the nakshatra this graha occupies."""
    from rishivan.chart.ephemeris import NAKSHATRAS, NAKSHATRA_LORDS

    nakshatra = _position(chart, graha).nakshatra
    return f"graha.{NAKSHATRA_LORDS[NAKSHATRAS.index(nakshatra)].lower()}"


def _walk(chart: Chart, graha: str, step) -> Chain:
    """Follow `step` from `graha` until it repeats or runs out.

    The visited set is the whole point. Without it a mutual pair loops forever;
    with it, the loop is detected on the second visit and reported.
    """
    path: list[str] = []
    seen: set[str] = set()
    current = graha

    for _ in range(_MAX_HOPS):
        if current in seen:
            return Chain(path=tuple(path), terminus=path[-1], cycle=True)
        path.append(current)
        seen.add(current)
        nxt = step(chart, current)
        if nxt == current:
            # Self-disposition: a planet in its own sign. A cycle of one, and
            # the natural terminus of most chains.
            return Chain(path=tuple(path), terminus=current, cycle=True)
        current = nxt

    raise RuntimeError(
        f"dispositor walk from {graha!r} exceeded {_MAX_HOPS} hops - the lord "
        f"tables are inconsistent, which is a bug here and not an exotic chart"
    )


def dispositor_chain(chart: Chart, graha: str) -> Chain:
    return _walk(chart, graha, dispositor_of)


def nakshatra_lord_chain(chart: Chart, graha: str) -> Chain:
    return _walk(chart, graha, nakshatra_lord_of)
