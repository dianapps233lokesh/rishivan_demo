"""Books to rule files. Both paths, and the gate they share.

    convert   corpus JSONL  -> rule docs           (deterministic, no model)
    extract   corpus JSONL  -> rule docs           (six model calls per passage)
                    |
                    +--> compile (9 passes) --> keep what compiles --> YAML
                                                         |
                                                    reviewer
                                                         |
                                                 status: production

The two paths differ only in how a document is produced. Everything after is
identical, and deliberately so: the deterministic converter is the cheap way to
find out whether the compiler, the registry and the lints survive contact with a
real corpus, and any problem it exposes is a problem the model path would have
hit too, at three orders of magnitude more cost.

**Nothing is written that does not compile.** The compiler is the arbiter, not
the producer - a converter that dropped rules on its own reasoning would slowly
grow a second, undocumented copy of the compiler's rules. So documents go
through all nine passes, the ones with errors are dropped with their diagnostic
attached, and only the survivors reach disk.

**Nothing is written as `production`.** Every rule that leaves here is
`candidate`, and the serving default excludes candidates. The path from
candidate to production runs through a person.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from rishivan.koonji.compiler import CompileResult, Diagnostic, compile_rules
from rishivan.koonji.convert import ConversionReport, convert_corpus
from rishivan.koonji.corpus import Unit, load_corpus, to_passages
from rishivan.koonji.emit import round_trips, write_grouped
from rishivan.koonji.registry import Registry, seed_registry
from rishivan.koonji.urf import Rule

DEFAULT_OUT = Path(__file__).parent / "rules"


@dataclass(slots=True)
class GateReport:
    """What survived the compiler, and what did not."""

    submitted: int = 0
    compiled: int = 0
    dropped: dict[str, str] = field(default_factory=dict)
    """rule_id -> the first diagnostic that killed it."""

    round_trip_failures: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def kept(self) -> int:
        return self.compiled - len(self.round_trip_failures)

    def __str__(self) -> str:
        lines = [f"{self.submitted} documents -> {self.kept} rules written"]
        if self.dropped:
            lines.append(f"\n{len(self.dropped)} dropped by the compiler:")
            for rule_id, why in list(self.dropped.items())[:12]:
                lines.append(f"  {rule_id}")
                lines.append(f"      {why[:120]}")
            if len(self.dropped) > 12:
                lines.append(f"  ... and {len(self.dropped) - 12} more")
        if self.round_trip_failures:
            lines.append(f"\n{len(self.round_trip_failures)} failed the emit/parse "
                         f"round trip and were withheld:")
            for rule_id, why in list(self.round_trip_failures.items())[:8]:
                lines.append(f"  {rule_id}: {why[:100]}")
        if self.warnings:
            lines.append(f"\n{len(self.warnings)} warnings:")
            for w in self.warnings[:8]:
                lines.append(f"  {w[:140]}")
        return "\n".join(lines)


CORPUS_WIDE = "<corpus>"
"""The rule_id the compiler uses for diagnostics that belong to no single rule.

Cross-rule passes - duplicate ids, claim polarity - report against the corpus.
Those cannot be dropped around, so they are surfaced rather than silently
turning into a dropped rule that was never the problem.
"""


def _rule_id_of(diagnostic: Diagnostic) -> str:
    rule_id = diagnostic.rule_id
    return "" if rule_id in ("", CORPUS_WIDE, "<unnamed>") else rule_id


def gate(
    docs: list[dict[str, Any]],
    registry: Registry,
    *,
    check_round_trip: bool = True,
) -> tuple[list[Rule], GateReport, CompileResult]:
    """Compile, drop what fails, and refuse to write what cannot be read back."""
    report = GateReport(submitted=len(docs))
    result = compile_rules(docs, registry)

    fatal: dict[str, str] = {}
    for diagnostic in result.errors:
        rule_id = _rule_id_of(diagnostic)
        message = str(diagnostic)
        if rule_id:
            fatal.setdefault(rule_id, message)
        else:
            # A corpus-level error names no rule. It cannot be dropped around,
            # so it is surfaced rather than swallowed.
            report.warnings.append(f"corpus-level: {message}")

    report.warnings.extend(str(w) for w in result.warnings)
    report.dropped = fatal

    kept: list[Rule] = []
    for rule in result.rules:
        if rule.rule_id in fatal:
            continue
        if check_round_trip:
            ok, why = round_trips(rule, registry)
            if not ok:
                report.round_trip_failures[rule.rule_id] = why or "unknown"
                continue
        kept.append(rule)

    report.compiled = len(result.rules) - len(fatal)
    return kept, report, result


# ==========================================================================
# The deterministic path
# ==========================================================================


@dataclass(slots=True)
class ConvertRun:
    conversion: ConversionReport
    gate: GateReport
    written: list[Path] = field(default_factory=list)
    elapsed_s: float = 0.0

    def __str__(self) -> str:
        files = "\n".join(f"  {p}" for p in self.written)
        return (f"{self.conversion}\n\n{self.gate}\n\n"
                f"written in {self.elapsed_s:.1f}s:\n{files}")


def convert_books(
    *,
    out_dir: Path | str = DEFAULT_OUT,
    books: Optional[Iterable[str]] = None,
    registry: Optional[Registry] = None,
    limit: Optional[int] = None,
    write: bool = True,
) -> ConvertRun:
    """The already-extracted corpus, through the frame and onto disk.

    Writes into `<out_dir>/converted/` rather than alongside the hand-written
    rules. Machine output and reviewed hand-authored material should never share
    a file: the generated file is overwritten on every run, and a hand edit made
    inside it would vanish without trace.

    Reads the LEGACY corpus, which is the only thing it has ever converted: this
    function turns the old extractor's output into the frame, and the old
    extractor wrote one row per rule. The bridged corpus that `extract` now
    reads is one row per verse and carries no `rule` key at all, so pointing
    this at it produces nothing and says so only in the count.
    """
    started = time.perf_counter()
    registry = registry or seed_registry()

    units = load_corpus(books=books, legacy=True)
    if limit:
        units = units[:limit]

    conversion = convert_corpus(units)
    rules, report, _ = gate(conversion.docs, registry)

    written: list[Path] = []
    if write and rules:
        written = write_grouped(
            rules,
            Path(out_dir) / "converted",
            header=(
                "GENERATED - do not edit by hand.\n"
                "  python -m rishivan.koonji convert\n"
                "\n"
                "Converted from the earlier extractor's output by convert.py. Every\n"
                "rule here is `candidate`: it compiled, it round-trips, and no\n"
                "Jyotish reviewer has read it. Promotion to `production` is a\n"
                "human act, and it happens by moving the rule into a reviewed file,\n"
                "not by editing the status in place - this file is overwritten."
            ),
        )

    return ConvertRun(
        conversion=conversion, gate=report, written=written,
        elapsed_s=time.perf_counter() - started,
    )


# ==========================================================================
# The model path
# ==========================================================================


@dataclass(slots=True)
class ExtractRun:
    passages: int = 0
    candidates: int = 0
    blocked: int = 0
    disagreements: int = 0
    calls: int = 0
    gate: Optional[GateReport] = None
    written: list[Path] = field(default_factory=list)
    queue: list[tuple[float, str, str]] = field(default_factory=list)
    """(priority, rule_id, passage_id) - the reviewer's worklist, worst first."""

    unbuildable: list[str] = field(default_factory=list)
    """Documents the model produced that the frame refused. Every one is either
    a prompt bug or a missing predicate - never nothing."""

    failures: dict[str, str] = field(default_factory=dict)
    elapsed_s: float = 0.0

    def __str__(self) -> str:
        lines = [
            f"{self.passages} passages · {self.calls} model calls · "
            f"{self.elapsed_s:.1f}s",
            f"{self.candidates} candidates · {self.blocked} blocked by validation · "
            f"{self.disagreements} extractor disagreements",
        ]
        if self.unbuildable:
            lines.append(f"\n{len(self.unbuildable)} documents would not build "
                         f"as rules:")
            for why in self.unbuildable[:8]:
                # Not truncated hard: a pydantic message puts the allowed values
                # at the END, and a 150-char slice cut them off - which sent me
                # looking for a bug in the frame that was not there.
                lines.append("  " + why.replace("\n", " ")[:400])
        if self.failures:
            lines.append(f"\n{len(self.failures)} passages errored:")
            for pid, why in list(self.failures.items())[:8]:
                lines.append(f"  {pid}: {why[:100]}")
        if self.gate:
            lines.append("")
            lines.append(str(self.gate))
        if self.written:
            lines.append("\nwritten:")
            lines.extend(f"  {p}" for p in self.written)
        return "\n".join(lines)


def extract_books(
    client,
    *,
    out_dir: Path | str = DEFAULT_OUT,
    books: Optional[Iterable[str]] = None,
    registry: Optional[Registry] = None,
    limit: Optional[int] = None,
    write: bool = True,
    fast_model: str = "gemini-2.5-flash",
    deep_model: str = "gemini-2.5-pro",
    on_passage: Optional[Callable[[int, int, Any], None]] = None,
) -> ExtractRun:
    """Re-read the verses with a model, six calls at a time.

    Sequential on purpose. The bottleneck is the provider's rate limit, not this
    process, and a sequential loop that can be stopped with ctrl-c after
    forty passages is worth more during a proving run than a pool that has to be
    drained. Parallelise when the proving run is clean and the volume is real.

    A passage that raises does not stop the run - it is recorded in `failures`
    and the next one starts. Losing four hundred passages to one malformed
    response is the failure mode that makes people stop trusting the pipeline.
    """
    from rishivan.koonji.extract import Extractor

    started = time.perf_counter()
    registry = registry or seed_registry()

    units = load_corpus(books=books)
    passages = list(to_passages(units))
    if limit:
        passages = passages[:limit]

    extractor = Extractor(client, registry, fast_model=fast_model, deep_model=deep_model)
    run = ExtractRun(passages=len(passages))
    docs: list[dict[str, Any]] = []

    from rishivan.koonji.emit import emit_doc

    budget = getattr(client, "budget", None)

    for i, passage in enumerate(passages, start=1):
        before = budget.calls if budget is not None else 0
        try:
            result = extractor.process(passage)
        except Exception as exc:  # noqa: BLE001 - one passage must not end the run
            run.failures[passage.passage_id] = f"{type(exc).__name__}: {exc}"
            # A passage that raised still spent whatever it spent before it
            # raised. Counting only successful passages under-reports the bill
            # in exactly the situation where it is climbing.
            if budget is not None:
                run.calls += budget.calls - before
            continue

        run.calls += (
            budget.calls - before if budget is not None else result.usage.calls
        )
        run.unbuildable.extend(result.unbuildable)
        run.disagreements += len(result.disagreements)
        blocked = set(result.blocked)
        run.blocked += len(blocked)

        for priority, candidate in result.queue():
            rule_id = candidate.rule.rule_id
            run.queue.append((priority, rule_id, passage.passage_id))
            if rule_id in blocked:
                # A blocked candidate is a reviewer's problem, not a rule. It
                # stays in the queue and never reaches a rule file.
                continue
            run.candidates += 1
            docs.append(emit_doc(candidate.rule))

        if on_passage is not None:
            on_passage(i, len(passages), result)

    run.queue.sort(key=lambda row: -row[0])

    rules, report, _ = gate(docs, registry)
    run.gate = report
    if write and rules:
        run.written = write_grouped(
            rules,
            Path(out_dir) / "extracted",
            header=(
                "GENERATED - do not edit by hand.\n"
                "  python -m rishivan.koonji extract\n"
                "\n"
                "Extracted by the six-call pipeline in extract.py, then compiled and\n"
                "round-tripped. Candidates that failed validation are NOT here -\n"
                "they are in the review queue. Nothing here has been read by a\n"
                "reviewer either; `candidate` means exactly that."
            ),
        )

    run.elapsed_s = time.perf_counter() - started
    return run


# ==========================================================================
# Restatements
# ==========================================================================


def detect_restatements(rules: Iterable[Rule]) -> dict[str, list[str]]:
    """Rules sharing an antecedent, grouped. The lineage edge, computed.

    Two rules with the same conditions saying the same thing are one piece of
    evidence, not two - and the cross-book case is the one that matters, because
    BPHS and Jataka Parijata restating each other is exactly what an unaware
    confidence calculation counts twice.

    This proposes; it does not write. `restates` goes into a rule's provenance
    only once somebody has agreed the two really are the same statement.
    """
    from collections import defaultdict

    from rishivan.koonji.urf import project_tcode

    buckets: dict[tuple[str, str], list[str]] = defaultdict(list)
    for rule in rules:
        if rule.antecedent.expr is None:
            continue
        signature = (
            project_tcode(rule),
            _antecedent_signature(rule),
        )
        buckets[signature].append(rule.rule_id)

    return {
        f"{tcode}|{sig[:60]}": sorted(ids)
        for (tcode, sig), ids in buckets.items()
        if len(ids) > 1
    }


def _antecedent_signature(rule: Rule) -> str:
    """A canonical string for the conditions, order-independent.

    Sorted, so that two rules whose atoms were extracted in different orders
    still collide. Without the sort this finds only restatements that happen to
    have been written down the same way, which is the easy half.
    """
    from rishivan.koonji.urf import iter_leaves

    parts = sorted(
        f"{call.predicate}({','.join(f'{k}={v}' for k, v in sorted(call.args.items()))})"
        + ("!" if call.negated else "")
        for call in iter_leaves(rule.antecedent.expr)
    )
    return ";".join(parts)
