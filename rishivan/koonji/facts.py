"""koonji.facts - the fact compiler. Chart -> a canonical ground fact set.

This is the stage that makes everything downstream fast, and it is the piece
the first architecture draft was missing. A `Chart` is a nested struct; rules
match against a flat, sorted set of interned integers.

Three design rules, and the reasoning matters more than the code:

1. **Continuous values are bucketed for the index, exact values retained for
   evaluation.** `sav_band(bhava.10, strong)` is indexed; `sav_bindu(bhava.10)
   = 31` stays in a side table. The index yields a *superset* of candidates and
   the VM prunes it with exact arithmetic. False positives are free. False
   negatives are not, and that asymmetry drives every choice here.

2. **Derived subjects are materialised, not resolved at match time.** "the lord
   of the 2nd sits in the 11th" is stored as a first-class atom under the
   subject `lord.bhava.02`, alongside the same atom under `graha.venus`. Costs
   roughly 4,000 atoms instead of 800; buys pure set membership for every rule
   match, with no join.

3. **Atoms are interned to integers against the bundle's table.** Both the
   chart's fact set and every rule's precondition core speak the same integer
   vocabulary, so there is no string comparison anywhere in the hot path.

And one rule about honesty: a quantity this stack cannot compute is declared
`undecidable`, never omitted. An omitted atom reads downstream as "the rule did
not apply", which is a false negative wearing an answer's clothes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping, Optional

from rishivan.chart.dasha import current_periods
from rishivan.chart.ephemeris import Chart
from rishivan.chart.relations import DEFAULT_ASPECTS, SPECIAL_ASPECTS, dignity_of
from rishivan.chart.vendor.ashtakavarga import SUBJECTS as AV_SUBJECTS
from rishivan.chart.vendor.ashtakavarga import compute_ashtakavarga
from rishivan.chart.vendor.varga import varga_sign
from rishivan.koonji.registry import (
    BANDS,
    DUSTHANAS,
    KARAKAS,
    KENDRAS,
    RASHIS,
    TRIKONAS,
    UPACHAYAS,
)

#: Vargas flattened into atoms. The full shodashavarga cross-product would
#: roughly triple the fact set for divisions almost no rule cites; these six are
#: the ones classical rules actually name.
#:   D2 wealth · D7 children · D9 marriage/strength · D10 career
#:   D12 parents · D30 affliction
EMITTED_VARGAS = ("D2", "D7", "D9", "D10", "D12", "D30")

#: Combustion arcs in degrees of elongation from the Sun, Parashari values.
#: Mercury and Venus take a tighter arc when retrograde. The nodes have no
#: disc and are never combust.
COMBUSTION_ARC = {
    "moon": (12.0, 12.0),
    "mars": (17.0, 17.0),
    "mercury": (14.0, 12.0),
    "jupiter": (11.0, 11.0),
    "venus": (10.0, 8.0),
    "saturn": (15.0, 15.0),
}

#: Predicates this stack cannot decide. Declared, never silently omitted.
#: Shadbala is six weighted components (sthana, dig, kala, chesta, naisargika,
#: drik) and the chart layer computes none of them. Until it does, any rule
#: resting on planetary strength is INDETERMINATE rather than NOT_APPLICABLE -
#: the engine says "I could not tell", which is a different and honest answer.
UNDECIDABLE_PREDICATES = frozenset({"strength", "strength_band"})

#: SAV bindu thresholds per house. 28 is the average (337/12); the bands are
#: the conventional weak/strong split around it.
SAV_BANDS = ((25, "very_weak"), (28, "weak"), (31, "moderate"), (34, "strong"))


def atom_name(predicate: str, *args: str) -> str:
    """The canonical wire form of a ground atom. Argument order is significant
    and comes from the predicate's registry signature."""
    return f"{predicate}({','.join(args)})"


@dataclass(slots=True)
class AtomTable:
    """Interns atom names to dense integers.

    The bundle owns the canonical table, built at compile time from every atom
    any rule mentions. At serve time the fact compiler looks up against it and
    drops what it does not find: an atom no rule references cannot change which
    rules fire, so interning it would be pure cost.

    **A dataclass rather than a plain class, and that is not cosmetic.**
    LangGraph's checkpointer serialises dataclasses and refuses plain classes
    outright - `Type is not msgpack serializable`. `FactSet` holds one of these
    and `Reading` holds a `FactSet`, so this single plain class made the entire
    graph state unpersistable. Measured, after removing the generator turned out
    to be necessary and not sufficient.
    """

    _to_id: dict[str, int] = field(default_factory=dict)
    _to_name: list[str] = field(default_factory=list)

    def __init__(self, names: Iterable[str] = ()) -> None:
        # Hand-written rather than generated, to keep the positional
        # `AtomTable(names)` constructor every call site already uses. The
        # generated one would take `_to_id` first and break all of them.
        self._to_id = {}
        self._to_name = []
        for n in names:
            self.intern(n)

    def intern(self, name: str) -> int:
        existing = self._to_id.get(name)
        if existing is not None:
            return existing
        new_id = len(self._to_name)
        self._to_id[name] = new_id
        self._to_name.append(name)
        return new_id

    def lookup(self, name: str) -> Optional[int]:
        return self._to_id.get(name)

    def name(self, atom_id: int) -> str:
        return self._to_name[atom_id]

    def names(self) -> tuple[str, ...]:
        return tuple(self._to_name)

    def __len__(self) -> int:
        return len(self._to_name)

    def __contains__(self, name: object) -> bool:
        return name in self._to_id


@dataclass(frozen=True, slots=True)
class FactSet:
    """Everything true about one chart, in the vocabulary rules are written in."""

    atoms: frozenset[int]
    table: AtomTable

    #: Exact continuous values, keyed `predicate(subject)`. The VM reads these
    #: for numeric comparisons the index could only approximate.
    exact: Mapping[str, float] = field(default_factory=dict)

    #: Derived subject reference -> the graha it resolves to for this chart.
    subjects: Mapping[str, str] = field(default_factory=dict)

    #: graha -> every reference that names it, itself included.
    aliases: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    #: Predicates this chart could not decide. A rule depending on one of these
    #: is INDETERMINATE, which is not the same as not applicable.
    undecidable: frozenset[str] = frozenset()

    #: Observables actually available. A Prasna rule requiring `breath` is not
    #: servable from a chart alone and must never be improvised into one.
    observables: frozenset[str] = frozenset({"chart"})

    when: Optional[datetime] = None

    def has(self, predicate: str, *args: str) -> bool:
        atom_id = self.table.lookup(atom_name(predicate, *args))
        return atom_id is not None and atom_id in self.atoms

    def atom_names(self) -> set[str]:
        return {self.table.name(i) for i in self.atoms}

    def resolve(self, subject: str) -> str:
        """A subject reference -> the graha it names on this chart."""
        return self.subjects.get(subject, subject)


class _Builder:
    def __init__(self, table: AtomTable, grow: bool) -> None:
        self.table = table
        self.grow = grow
        self.ids: set[int] = set()

    def add(self, predicate: str, *args: str) -> None:
        name = atom_name(predicate, *args)
        if self.grow:
            self.ids.add(self.table.intern(name))
        else:
            atom_id = self.table.lookup(name)
            if atom_id is not None:
                self.ids.add(atom_id)


def _band_for(value: float, thresholds: tuple[tuple[int, str], ...]) -> str:
    for limit, name in thresholds:
        if value < limit:
            return name
    return BANDS[-1]


def _elongation(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def compile_facts(
    chart: Chart,
    *,
    when: Optional[datetime] = None,
    table: Optional[AtomTable] = None,
    grow: bool = True,
    vargas: Iterable[str] = EMITTED_VARGAS,
) -> FactSet:
    """Flatten a chart into its ground fact set.

    `grow=False` pins the vocabulary to an existing table - the serving path,
    where the bundle's table is authoritative and unknown atoms are dropped.

    `vargas` names the divisions to emit. It defaults to the historic six so
    that every existing caller gets a byte-identical fact set; `varga.select`
    narrows or widens it per request. Emitting all sixteen unconditionally would
    be 16 x 9 atoms most questions never match, which is why the selection runs
    before compilation rather than filtering after it.

    D1 is ignored if passed: it is the rashi chart itself, already carried by
    `occupies_rashi`, and emitting it as a division would double every
    placement.
    """
    table = table if table is not None else AtomTable()
    when = when or datetime.now()
    b = _Builder(table, grow)

    lower = {name.lower(): p for name, p in chart.planets.items()}

    # -- subject references ------------------------------------------------
    # Every way a rule can name a body, resolved once. `lord.bhava.10` is not a
    # lookup performed at match time; it becomes part of the atom itself.
    subjects: dict[str, str] = {}
    aliases: dict[str, list[str]] = {f"graha.{g}": [f"graha.{g}"] for g in lower}

    for house, lord in chart.house_lords.items():
        ref = f"lord.bhava.{house:02d}"
        graha = f"graha.{lord.lower()}"
        subjects[ref] = graha
        aliases[graha].append(ref)

    for karaka, graha_name in KARAKAS.items():
        ref = f"karaka.{karaka}"
        graha = f"graha.{graha_name}"
        if graha in aliases:
            subjects[ref] = graha
            aliases[graha].append(ref)

    def refs(graha_name: str) -> tuple[str, ...]:
        return tuple(aliases[f"graha.{graha_name}"])

    # -- placement, condition, house groups --------------------------------
    for name, p in lower.items():
        house = f"bhava.{p.house:02d}"
        rashi = f"rashi.{p.rashi.lower()}"
        dignity = dignity_of(name, p.rashi.lower())
        sun = lower["sun"]
        arc = COMBUSTION_ARC.get(name)
        combust = bool(
            arc
            and _elongation(p.longitude, sun.longitude)
            < (arc[1] if p.retrograde else arc[0])
        )
        d9_same = varga_sign("D9", p.longitude) == p.rashi_index

        for ref in refs(name):
            b.add("occupies_bhava", ref, house)
            b.add("occupies_rashi", ref, rashi)
            b.add("in_nakshatra", ref, f"nakshatra.{p.nakshatra.lower().replace(' ', '_')}")
            b.add("dignity", ref, f"dignity.{dignity or 'neutral'}")
            if p.retrograde:
                b.add("retrograde", ref)
            if combust:
                b.add("combust", ref)
            if d9_same:
                b.add("vargottama", ref)
            if p.house in KENDRAS:
                b.add("in_kendra", ref)
            if p.house in TRIKONAS:
                b.add("in_trikona", ref)
            if p.house in DUSTHANAS:
                b.add("in_dusthana", ref)
            if p.house in UPACHAYAS:
                b.add("in_upachaya", ref)

    # -- relations ---------------------------------------------------------
    # Conjunction is whole-sign: two bodies in one rashi. BPHS is a whole-sign
    # text throughout, and an orb model answers differently.
    for name, p in lower.items():
        for other, q in lower.items():
            if name == other:
                continue
            if p.house == q.house:
                for r1 in refs(name):
                    for r2 in refs(other):
                        b.add("conjunct", r1, r2)
                        b.add("same_bhava", r1, r2)

    # Parivartana: each in a sign the other lords.
    for name, p in lower.items():
        for other, q in lower.items():
            if name == other:
                continue
            if (
                chart.house_lords.get(p.house, "").lower() == other
                and chart.house_lords.get(q.house, "").lower() == name
            ):
                for r1 in refs(name):
                    for r2 in refs(other):
                        b.add("exchange", r1, r2)

    # Parashari graha drishti. Everything aspects the 7th from itself; Mars adds
    # the 4th and 8th, Jupiter the 5th and 9th, Saturn the 3rd and 10th.
    occupants: dict[int, list[str]] = {}
    for name, p in lower.items():
        occupants.setdefault(p.house, []).append(name)

    for name, p in lower.items():
        for offset in SPECIAL_ASPECTS.get(name, DEFAULT_ASPECTS):
            target_house = ((p.house - 1 + offset - 1) % 12) + 1
            for ref in refs(name):
                b.add("aspects", ref, f"bhava.{target_house:02d}")
                # A verse may name the aspected planet rather than the house, so
                # both forms are emitted and neither reading is lost.
                for other in occupants.get(target_house, ()):
                    if other == name:
                        continue
                    for r2 in refs(other):
                        b.add("aspects", ref, r2)

    # Relative house position. Classical rules are stated as "in the 2nd, 4th,
    # 10th or 12th from it" far more often than as absolute houses, so the atom
    # is emitted in the form the verse uses rather than making every such rule
    # do arithmetic the index cannot see through.
    for name, p in lower.items():
        for other, q in lower.items():
            if name == other:
                continue
            distance = ((q.house - p.house) % 12) + 1
            for r1 in refs(name):
                for r2 in refs(other):
                    b.add("house_distance", r1, r2, f"dist.{distance:02d}")

    # Whole-sign house signs. `bhava_in_rashi(bhava.01, ...)` is the lagna, which
    # is what every functional-nature derivation keys off.
    for house in range(1, 13):
        sign = RASHIS[(chart.lagna_rashi_index + house - 1) % 12]
        b.add("bhava_in_rashi", f"bhava.{house:02d}", f"rashi.{sign}")

    # Houses counted from the Moon and the Sun. Chandra lagna and Surya lagna are
    # the two alternative reference points classical texts actually use, and a
    # verse meaning "the 7th from the Moon" that gets stored as "the 7th" fires
    # on the wrong charts forever without ever looking wrong.
    for reference, origin in (
        ("lagna", chart.lagna_rashi_index),
        ("moon", lower["moon"].rashi_index),
        ("sun", lower["sun"].rashi_index),
    ):
        for name, p in lower.items():
            house = (p.rashi_index - origin) % 12 + 1
            for ref in refs(name):
                b.add("occupies_bhava_from", ref, f"bhava.{house:02d}", f"ref.{reference}")

    # -- vargas ------------------------------------------------------------
    for code in vargas:
        if code == "D1":
            continue
        varga_id = f"varga.{code.lower()}"
        for name, p in lower.items():
            sign_index = varga_sign(code, p.longitude)
            sign = RASHIS[sign_index]
            varga_dignity = dignity_of(name, sign)
            for ref in refs(name):
                b.add("varga_occupies", varga_id, ref, f"rashi.{sign}")
                if varga_dignity:
                    b.add("varga_dignity", varga_id, ref, f"dignity.{varga_dignity}")

    # -- timing ------------------------------------------------------------
    for level, period in current_periods(chart, when).items():
        if period is None:
            continue
        for ref in refs(period.lord.lower()):
            b.add("dasha_active", "dasha_system.vimshottari", ref, f"level.{level}")

    # -- Ashtakavarga ------------------------------------------------------
    # A real, well-defined support measure, and explicitly NOT Shadbala. Keeping
    # them separate matters: conflating a bindu count with planetary strength
    # would give a rule that cites Shadbala an answer drawn from something else.
    exact: dict[str, float] = {}
    av = compute_ashtakavarga(
        {s: lower[s].rashi_index for s in AV_SUBJECTS}, chart.lagna_rashi_index
    )
    for house in range(1, 13):
        sign_index = (chart.lagna_rashi_index + house - 1) % 12
        bindus = av.sav[sign_index]
        bhava = f"bhava.{house:02d}"
        exact[f"sav_bindu({bhava})"] = float(bindus)
        b.add("sav_band", bhava, f"band.{_band_for(bindus, SAV_BANDS)}")

    for house in range(1, 13):
        exact[f"occupant_count(bhava.{house:02d})"] = float(len(occupants.get(house, ())))

    return FactSet(
        atoms=frozenset(b.ids),
        table=table,
        exact=exact,
        subjects=subjects,
        aliases={g: tuple(refs) for g, refs in aliases.items()},
        undecidable=UNDECIDABLE_PREDICATES,
        observables=frozenset({"chart", "query_time"}),
        when=when,
    )
