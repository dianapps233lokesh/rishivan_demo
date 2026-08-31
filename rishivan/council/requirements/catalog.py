"""What each kind of question requires, composed rather than transcribed.

**This is the authored source AND the offline fallback.** `scripts/seed_requirements.py`
writes what is here into Mongo; `store.load` reads Mongo and falls back to here
when the cluster is silent. One authoring surface, two carriers, so the two
cannot disagree at birth — only after somebody edits Mongo, which is the point
of putting it there, and which `--check` reports.

**Most of a row is derived from the constitution, not typed out.**
`CONSTITUTIONS['prema']` already holds the houses a marriage question rests on,
the planets it names, the vargas it admits and the ten-step protocol it follows.
Restating any of that here would be a second copy to drift — the exact failure
`hierarchy.LIFE_DOMAIN_OF` was written to avoid. So `_from_constitution` reads
it, and `_DOMAIN_EXTRAS` holds only what the constitution cannot express: the
doshas, the karakas, the arudha.

**A requirement may name something nothing can compute.** That is deliberate and
is most of the value here. `prema`'s protocol step 5 is "Jaimini indicators" and
its `blocked_concepts` says Darakaraka and Upapada are unavailable — so the
requirement is listed, the producer registry has nothing for it, and the prompt
declares it missing. The alternative is a marriage reading that skips step 5 in
silence, which is what was happening.
"""

from __future__ import annotations

from rishivan.council.requirements.types import Requirement, RequirementSet

KINDS: tuple[str, ...] = ("when_will", "ok_on_date", "what_is_it_like", "which_option")
"""Mirrors `question_profile.QuestionKind`. Pinned by a test rather than
imported, so a kind added there without a requirement row here is a failure
somebody sees."""


FLOOR: tuple[Requirement, ...] = (
    Requirement("block.chart_table", step=1, mandatory=True, priority=1),
    Requirement("block.house_lords", step=1, mandatory=True, priority=1),
    Requirement("block.planet_condition", step=1, mandatory=True, priority=1),
    Requirement("block.dasha.current", step=7, mandatory=True, priority=1),
)
"""Present for every question and not negotiable, carried over verbatim from
`question_profile.FLOOR`'s argument: the placements say what the chart is, the
lords say who governs what, the condition says how strong any of it is, and the
running period says what is live. A reading missing any of the four is wrong in
a way that reads as fluent."""


_PER_KIND: dict[str, tuple[Requirement, ...]] = {
    "when_will": (
        Requirement("block.dasha.forward", step=7, mandatory=True, priority=1),
        # Band 1 and mandatory: for a "when" question this IS the answer's
        # ground. Printing every period and leaving the model to search them is
        # what produced a 2033 window when the chart's own 7th lord ruled a
        # pratyantardasha in 2027.
        Requirement("block.timing.candidates", step=7, mandatory=True, priority=1),
        # Already computed by `dasha.current_periods` and never sent. An
        # antardasha is ~18 months wide; a client asking "when" deserves the
        # level below it, and the arithmetic has been there all along.
        Requirement("block.dasha.pratyantar", step=7, mandatory=False, priority=2),
        Requirement("block.transits_slow", step=8, mandatory=True, priority=2),
        Requirement("block.sade_sati", step=8, mandatory=False, priority=3),
        Requirement("block.yogas", step=6, mandatory=False, priority=2),
    ),
    # No forward periods. A ten-year forecast is not an answer about tomorrow,
    # and sending one is how "can I travel tomorrow" was answered with 2027.
    "ok_on_date": (
        Requirement("block.panchang", step=8, mandatory=True, priority=1),
        # The classical instruments for choosing a time, crossed against the
        # inauspicious windows. Absent until now: a muhurta question got Rahu
        # Kaal and a chart, and the model supplied the judgement itself.
        Requirement("block.muhurta", step=8, mandatory=True, priority=1),
        Requirement("block.tara_bala", step=8, mandatory=True, priority=1),
        Requirement("block.chandra_bala", step=8, mandatory=True, priority=1),
        Requirement("block.transits_slow", step=8, mandatory=False, priority=3),
    ),
    # No transits, no forward periods. A temperament reading timed against a
    # transit becomes a forecast nobody asked for.
    "what_is_it_like": (
        Requirement("block.yogas", step=6, mandatory=True, priority=1),
        Requirement("block.conjunctions", step=6, mandatory=False, priority=2),
    ),
    "which_option": (
        Requirement("block.panchang", step=8, mandatory=True, priority=1),
        Requirement("block.muhurta", step=8, mandatory=True, priority=1),
        Requirement("block.transits_slow", step=8, mandatory=False, priority=2),
    ),
}


_DOMAIN_EXTRAS: dict[str, tuple[Requirement, ...]] = {
    "domain.relationship": (
        # §5 "7th house/lord, Venus, Jupiter where relevant". Mangal dosha is
        # not in the constitution's vocabulary and is the first thing any
        # classical marriage reading checks.
        Requirement("block.kuja_dosha", step=6, mandatory=True, priority=1),
        # Chandra lagna. A 7th judged only from the lagna is half the reading.
        Requirement("from_moon.house.7.lord.house", step=2, priority=2),
        # Protocol step 5, blocked by `prema.blocked_concepts` until the
        # computation exists. Listed so its absence is declared, not silent.
        Requirement("karaka.dara", step=5, priority=2),
        Requirement("from_arudha_lagna.house.12", step=5, priority=2),
    ),
    "domain.progeny": (
        Requirement("karaka.putra", step=5, priority=2),
        Requirement("from_moon.house.5.lord.house", step=2, priority=2),
    ),
    "domain.career": (
        Requirement("block.ashtakavarga.house.10", step=4, priority=2),
        Requirement("from_moon.house.10.lord.house", step=2, priority=2),
    ),
    "domain.wealth": (
        Requirement("block.ashtakavarga.house.2", step=4, priority=2),
        Requirement("block.ashtakavarga.house.11", step=4, priority=2),
    ),
    "domain.health": (
        Requirement("block.kuja_dosha", step=6, mandatory=False, priority=2),
        Requirement("from_moon.house.6.lord.house", step=2, priority=2),
    ),
    "domain.longevity": (
        Requirement("from_moon.house.8.lord.house", step=2, priority=2),
    ),
}
"""What a constitution cannot express, per domain.

Deliberately thin. Anything derivable from `primary_houses`, `supporting_houses`,
`planets` or `vargas` belongs in `_from_constitution` and not here — a row
duplicated from the constitution is a row that will disagree with it.
"""


def _from_constitution(domain: str) -> tuple[Requirement, ...]:
    """The requirements the constitution already implies.

    Primary houses are what the verdict rests on, so they band 1 and are
    mandatory; supporting houses are context and band 2. Each admitted varga
    contributes its own lagna lord and the lord of the domain's primary house
    within it — which is what "D9 confirmation" means as a step, and what a raw
    dump of D9 placements never quite says.
    """
    from rishivan.council.direct_prompt import constitution_for

    constitution = constitution_for(domain)
    out: list[Requirement] = []

    for house in sorted(constitution.primary_houses):
        out.append(Requirement(f"block.house.{house}", step=1,
                               mandatory=True, priority=1))
        out.append(Requirement(f"house.{house}.lord.house", step=1,
                               mandatory=True, priority=1))
        # Jupiter and Saturn read together, over the house the question rests on.
        # Band 3 rather than 1: it times an activation, it does not establish a
        # promise, and a chart with no promise has nothing for it to time.
        out.append(Requirement(f"block.transit.double.{house}", step=8,
                               priority=3))
    for house in sorted(constitution.supporting_houses):
        out.append(Requirement(f"block.house.{house}", step=3, priority=2))

    for planet in sorted(constitution.planets):
        out.append(Requirement(f"planet.{planet.lower()}.dignity", step=2,
                               mandatory=True, priority=1))

    for code in sorted(constitution.vargas):
        scope = code.lower()
        out.append(Requirement(f"{scope}.house.1.lord.house", step=4,
                               mandatory=True, priority=2))
        for house in sorted(constitution.primary_houses):
            out.append(Requirement(f"{scope}.house.{house}.lord.house", step=4,
                                   mandatory=True, priority=2))
        out.append(Requirement(f"block.varga.{scope}", step=4,
                               mandatory=True, priority=2))
        out.append(Requirement(f"block.varga_confirms.{scope}", step=4,
                               priority=2))

    return tuple(out)


def _dedupe(requirements) -> tuple[Requirement, ...]:
    """One entry per key, keeping the strongest claim on it.

    A key can arrive from the floor, the kind and the domain at once — the 7th
    house is both `prema`'s primary house and, for a timing question, something
    the transit step wants. Keeping the lowest priority number and the strongest
    mandatory flag means a fact demoted by one source cannot quietly lose the
    band another source gave it.
    """
    best: dict[str, Requirement] = {}
    for requirement in requirements:
        current = best.get(requirement.key)
        if current is None:
            best[requirement.key] = requirement
            continue
        best[requirement.key] = Requirement(
            key=requirement.key,
            step=min(current.step or 99, requirement.step or 99),
            mandatory=current.mandatory or requirement.mandatory,
            priority=min(current.priority, requirement.priority),
        )
    return tuple(sorted(best.values(), key=lambda r: (r.priority, r.step, r.key)))


def requirement_set(domain: str, kind: str) -> RequirementSet:
    """One (domain, kind) pair, fully expanded."""
    from rishivan.council.hierarchy import LIFE_DOMAIN_OF

    keys = LIFE_DOMAIN_OF.get(domain or "", ())
    return RequirementSet(
        domain=domain,
        kind=kind,
        constitution=keys[0] if keys else "atma",
        requires=_dedupe(
            FLOOR
            + _PER_KIND.get(kind, ())
            + _from_constitution(domain)
            + _DOMAIN_EXTRAS.get(domain, ())
        ),
    )


def catalogue() -> dict[str, RequirementSet]:
    """Every (domain, kind) pair, keyed by `doc_id`.

    Includes the empty domain, which is what an unroutable question reaches -
    `constitution_for("")` falls back to atma, so the row is the whole-chart
    reading rather than nothing.
    """
    from rishivan.council.hierarchy import LIFE_DOMAIN_OF

    domains = ("",) + tuple(sorted(LIFE_DOMAIN_OF))
    return {
        f"{domain}:{kind}": requirement_set(domain, kind)
        for domain in domains
        for kind in KINDS
    }


def invalid_keys() -> tuple[str, ...]:
    """Token keys the vocabulary does not recognise.

    Block keys are exempt: they name a rendered block rather than a chart token,
    and their existence is checked against the producer registry instead. Run at
    seed time and asserted by a test, because a misspelled token is a
    requirement nobody can satisfy and nobody notices.
    """
    from rishivan.astro.vocab import is_valid_fact_key

    bad = {
        requirement.key
        for entry in catalogue().values()
        for requirement in entry.requires
        if not requirement.is_block and not is_valid_fact_key(requirement.key)
    }
    return tuple(sorted(bad))
