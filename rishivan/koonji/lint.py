"""koonji.lint - the quality gate that catches what review misses.

A reviewer reads a rule and asks whether it says what the verse says. That is
necessary and it is not sufficient, because it cannot see behaviour. A rule that
fires on a quarter of humanity reads perfectly well on the page.

So every rule is run against a reference corpus of synthetic charts and judged
on what it actually does. The design calls for a hundred thousand charts
spanning 1900-2050 across global latitudes; the default here is smaller so it
runs in CI in seconds, and the number is a parameter rather than a constant
because the useful version of this is the big one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Optional

from rishivan.chart.ephemeris import BirthData, Chart, compute_chart
from rishivan.koonji.bundle import Bundle
from rishivan.koonji.index import RETRIEVABLE
from rishivan.koonji.vm import Outcome, execute, run_derivations

#: Above this, a rule is not diagnostic. It is usually a missing precondition.
HIGH_FIRE_RATE = 0.25

#: Two rules that always fire together are one rule, or a duplicate extraction
#: from restated verses. Either way the evidence graph must not count them twice.
CO_FIRE_CORRELATION = 0.95

DEFAULT_CORPUS_SIZE = 400


@dataclass(slots=True)
class LintFinding:
    lint: str
    rule_id: str
    message: str
    severity: str = "warning"


@dataclass(slots=True)
class LintReport:
    charts: int
    fire_rate: dict[str, float] = field(default_factory=dict)
    outcomes: dict[str, dict[str, int]] = field(default_factory=dict)
    findings: list[LintFinding] = field(default_factory=list)

    def by_rule(self, rule_id: str) -> list[LintFinding]:
        return [f for f in self.findings if f.rule_id == rule_id]

    @property
    def problems(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity != "info"]

    @property
    def clean(self) -> bool:
        return not self.problems


def reference_corpus(
    size: int = DEFAULT_CORPUS_SIZE,
    *,
    start_year: int = 1900,
    end_year: int = 2050,
) -> list[Chart]:
    """Synthetic charts spread over time, longitude and latitude.

    Deterministic on purpose - a lint suite whose corpus changes between runs
    reports drift that is its own fault. The spread uses coprime strides rather
    than a random generator so the sample stays even without a seed.
    """
    charts: list[Chart] = []
    span_days = (end_year - start_year) * 365
    epoch = datetime(start_year, 1, 1)
    for i in range(size):
        moment = epoch + timedelta(days=(i * 4691) % span_days, minutes=(i * 337) % 1440)
        # Latitudes weighted toward inhabited bands; longitudes spread evenly.
        lat = -55.0 + ((i * 37) % 111)
        lon = -180.0 + ((i * 73) % 360)
        charts.append(compute_chart(BirthData(
            year=moment.year, month=moment.month, day=moment.day,
            hour=moment.hour, minute=moment.minute,
            tz_offset_hours=round(lon / 15.0, 2), lat=lat, lon=lon,
        )))
    return charts


def lint_bundle(
    bundle: Bundle,
    charts: Optional[Iterable[Chart]] = None,
    *,
    size: int = DEFAULT_CORPUS_SIZE,
    when: Optional[datetime] = None,
) -> LintReport:
    charts = list(charts) if charts is not None else reference_corpus(size)
    when = when or datetime(2026, 1, 1)
    registry = bundle.registry
    derivations = bundle.derivations()
    # Only rules retrieval can return are scored. A definition "fires" on every
    # chart by construction, and reporting that as a high fire rate is noise
    # that teaches a reviewer to ignore the lint.
    scored = [r for r in bundle.rules if r.assertion in RETRIEVABLE]

    report = LintReport(charts=len(charts))
    counts = {r.rule_id: {o.value: 0 for o in Outcome} for r in scored}
    fired_sets: dict[str, set[int]] = {r.rule_id: set() for r in scored}

    for n, chart in enumerate(charts):
        facts = bundle.index.facts_for(chart, when=when)
        facts = run_derivations(derivations, facts, registry)
        for firing in execute(scored, facts, registry):
            counts[firing.rule_id][firing.outcome.value] += 1
            if firing.outcome is Outcome.FIRED:
                fired_sets[firing.rule_id].add(n)

    total = len(charts)
    for rule in scored:
        fired = len(fired_sets[rule.rule_id])
        rate = fired / total if total else 0.0
        report.fire_rate[rule.rule_id] = rate
        report.outcomes[rule.rule_id] = counts[rule.rule_id]

        withheld = counts[rule.rule_id][Outcome.WITHHELD.value]
        if withheld == total and total:
            # Withheld is not "did not fire". The rule is doing exactly what it
            # was marked to do, and reporting it as dead would train a reviewer
            # to un-mark it.
            report.findings.append(LintFinding(
                "withheld", rule.rule_id,
                "never reaches the serving path - restricted at extraction or "
                "requires an observable this product cannot capture. Expected.",
                severity="info",
            ))
        elif rate == 0.0:
            report.findings.append(LintFinding(
                "never_fires", rule.rule_id,
                f"fired on none of {total} reference charts - either "
                f"over-constrained by a transcription error, or genuinely rarer "
                f"than 1 in {total}. Re-run against a larger corpus before "
                f"concluding it is broken; you cannot see this from the text.",
            ))
        elif rate > HIGH_FIRE_RATE:
            report.findings.append(LintFinding(
                "high_fire_rate", rule.rule_id,
                f"fires on {rate:.0%} of charts - a rule that applies to a "
                f"quarter of humanity is not diagnostic; usually a missing "
                f"precondition",
            ))

        indeterminate = counts[rule.rule_id][Outcome.INDETERMINATE.value]
        if indeterminate == total and total:
            report.findings.append(LintFinding(
                "always_indeterminate", rule.rule_id,
                "never decidable on any reference chart - it depends on a "
                "quantity this stack does not compute, so it can never "
                "contribute to an answer",
            ))

        # A cancellation clause that never triggers is dead code wearing the
        # costume of a safety net, which is worse than having no safety net.
        if rule.qualifiers.targets_rule and fired == 0:
            report.findings.append(LintFinding(
                "dead_clause", rule.rule_id,
                f"{rule.qualifiers.modality.value} clause targeting "
                f"{rule.qualifiers.targets_rule} never triggers",
            ))

    # Co-firing. Two rules that always fire together are one rule.
    ids = [r.rule_id for r in scored]
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            sa, sb = fired_sets[a], fired_sets[b]
            if not sa or not sb:
                continue
            jaccard = len(sa & sb) / len(sa | sb)
            if jaccard >= CO_FIRE_CORRELATION:
                report.findings.append(LintFinding(
                    "co_fire", a,
                    f"fires with {b} on {jaccard:.0%} of the charts either "
                    f"fires on - one rule, a duplicate extraction, or a "
                    f"restatement that must carry a `restates` edge or the "
                    f"evidence graph will count it twice",
                ))
    return report
