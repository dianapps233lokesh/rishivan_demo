"""Fire the Koonji on a real birth chart and show the whole chain.

    python -m rishivan.koonji fire   --date 1990-01-01 --time 12:00 --tz 5.5 \
                                     --lat 28.6139 --lon 77.2090 --candidate
    python -m rishivan.koonji ask    --date 1990-01-01 --candidate \
                                     --question "will I be wealthy?"
    python -m rishivan.koonji trace  --date 1990-01-01 ... --json
    python -m rishivan.koonji compile
    python -m rishivan.koonji lint    --charts 2000

    python -m rishivan.koonji corpus                    what books are loadable
    python -m rishivan.koonji convert                   JSONL -> compiled YAML
    python -m rishivan.koonji extract --limit 20        six model calls a passage
    python -m rishivan.koonji restatements              which rules are one rule

`fire` is the M0 acceptance test made permanent: post a birth date, see which
rules fired and why, with the verse each one came from.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from rishivan.chart.ephemeris import BirthData, compute_chart, summarize
from rishivan.koonji.compiler import compile_path
from rishivan.koonji.engine import DEFAULT_RULES_DIR, Engine
from rishivan.koonji.lint import lint_bundle
from rishivan.koonji.question import InputKind
from rishivan.koonji.registry import seed_registry
from rishivan.koonji.vm import Outcome

_OUTCOME_MARK = {
    Outcome.FIRED: "FIRED",
    Outcome.CANCELLED: "CANCELLED",
    Outcome.INDETERMINATE: "UNKNOWN",
    Outcome.WITHHELD: "WITHHELD",
    Outcome.NOT_APPLICABLE: "-",
}


def _birth(args) -> BirthData:
    date = datetime.strptime(args.date, "%Y-%m-%d")
    hour, minute = (int(x) for x in args.time.split(":"))
    return BirthData(
        year=date.year, month=date.month, day=date.day,
        hour=hour, minute=minute, tz_offset_hours=args.tz,
        lat=args.lat, lon=args.lon, place=args.place,
    )


def _statuses(args) -> frozenset[str]:
    # Candidate rules are unreviewed. Serving them has to be an explicit act.
    return frozenset({"production", "candidate"} if args.candidate else {"production"})


def _engine(args) -> Engine:
    return Engine.from_rules(args.rules)


def cmd_fire(args) -> int:
    engine = _engine(args)
    chart = compute_chart(_birth(args))
    when = datetime.strptime(args.when, "%Y-%m-%d") if args.when else datetime.now()
    reading = engine.read(
        chart, when=when,
        domains=set(args.domain) if args.domain else None,
        statuses=_statuses(args),
    )

    if args.chart:
        print(summarize(chart))
        print()

    print(f"bundle {reading.bundle_id}  ·  {engine.bundle.manifest.rule_count} rules "
          f"·  {len(reading.facts.atoms)} fact atoms  ·  {reading.elapsed_ms:.1f} ms")
    print(f"retrieval proposed {reading.considered} of "
          f"{engine.bundle.manifest.rule_count}\n")

    rules = engine.bundle.by_id()
    for firing in sorted(reading.firings, key=lambda f: (f.outcome.value, f.rule_id)):
        if firing.outcome is Outcome.NOT_APPLICABLE and not args.verbose:
            continue
        rule = rules.get(firing.rule_id)
        cite = f"{rule.provenance.book_id} {rule.provenance.locator}" if rule else ""
        print(f"  {_OUTCOME_MARK[firing.outcome]:<10} {firing.rule_id}   [{cite}]")
        if firing.reason:
            print(f"             {firing.reason}")
        if rule and args.verbose:
            print(f"             \"{rule.provenance.quoted_text.strip()[:150]}\"")

    print()
    if reading.insufficient:
        print("  INSUFFICIENT EVIDENCE")
        print("  The classical material examined does not speak clearly here.")
        print("  Saying so is the answer. This interaction would not be billed.")
        return 0

    for claim in reading.claims:
        flag = " (counter-evidence present)" if claim.has_counterevidence else ""
        print(f"  {claim.claim_id}  {claim.confidence:.2f}  {claim.phrasing}{flag}")
        print(f"      {claim.independent_sources} independent source(s)"
              + ("  · requires dasha activation" if claim.requires_activation else ""))
        for s in claim.support:
            tag = "" if s.independent else "  (restatement, discounted)"
            print(f"      + {s.rule_id}  w={s.effective_weight:.3f}  [{s.citation}]{tag}")
        for s in claim.against:
            print(f"      - {s.rule_id}  w={s.effective_weight:.3f}  [{s.citation}]")
    return 0


def cmd_ask(args) -> int:
    """The whole path from a sentence, with the filter shown at every step.

    `fire` takes `--domain` from the command line and answers. `ask` takes a
    question and has to work out what to look at, which is where every
    interesting failure lives - so it prints the routing, the filter and the
    scope counts before it prints a single claim.
    """
    engine = _engine(args)
    chart = compute_chart(_birth(args))
    when = datetime.strptime(args.when, "%Y-%m-%d") if args.when else datetime.now()
    response = engine.answer(
        args.question, chart, when=when,
        available={InputKind.BIRTH_PROFILE},
        statuses=_statuses(args),
    )
    spec = response.spec

    print(f'  "{spec.raw}"\n')
    print(f"  turn       {spec.turn_type.value}")
    print(f"  mode       {spec.mode.value}")
    print(f"  confidence {spec.parse_confidence:.2f}")
    if spec.flags:
        print(f"  flags      {', '.join(f.flag_id for f in spec.flags)}")
    print(f"  routing    {', '.join(spec.routing.domains) or '(none matched)'}")
    print(f"             {spec.routing.reason}")

    if response.reading is None:
        print(f"\n  {response.outcome.upper()}")
        if response.message:
            print(f"  {response.message}")
        return 0

    reading = response.reading
    plan = response.plan
    print(f"\n  filter     domains={sorted(plan.domains) if plan.domains else 'ALL'}"
          f"  schools={sorted(plan.schools) if plan.schools else 'ALL'}"
          f"  statuses={sorted(plan.statuses)}"
          f"  min_weight={plan.min_domain_weight}")
    if reading.widened:
        print("             WIDENED - the filter admitted no rules, so the whole "
              "corpus was read")
    print(f"  scope      {reading.scoped} variants in scope  ->  "
          f"{reading.considered} rules considered  ->  "
          f"{sum(1 for f in reading.firings if f.counts)} fired")
    print(f"  facts      {len(reading.facts.atoms)} atoms "
          f"({reading.derived_atoms} derived)  ·  {reading.elapsed_ms:.1f} ms\n")

    if reading.insufficient:
        print("  INSUFFICIENT EVIDENCE")
        print("  The classical material examined does not speak clearly here.")
        return 0

    rules = engine.bundle.by_id()
    for claim in reading.claims:
        print(f"  {claim.claim_id}  {claim.confidence:.2f}  {claim.phrasing}")
        for s in claim.support:
            rule = rules.get(s.rule_id)
            weights = rule.domains if rule else {}
            tags = " ".join(f"{d.removeprefix('domain.')}={w}" for d, w in weights.items())
            print(f"      + {s.rule_id}  w={s.effective_weight:.3f}  "
                  f"[{s.citation}]  {tags}")
        for s in claim.against:
            print(f"      - {s.rule_id}  w={s.effective_weight:.3f}  [{s.citation}]")
    return 0


def cmd_trace(args) -> int:
    engine = _engine(args)
    chart = compute_chart(_birth(args))
    when = datetime.strptime(args.when, "%Y-%m-%d") if args.when else datetime.now()
    reading = engine.read(chart, when=when, statuses=_statuses(args))
    print(json.dumps(engine.trace(reading), indent=2))
    return 0


def cmd_corpus(args) -> int:
    """What is actually on disk, before anything tries to extract from it."""
    from rishivan.koonji.corpus import load_corpus, survey, to_passages

    units = load_corpus(books=args.book or None)
    print(survey(units))
    passages = list(to_passages(units))
    with_context = sum(1 for p in passages if p.context)
    print(f"\n{len(passages)} passages · {with_context} carry preceding context")
    if args.sample:
        for p in passages[: args.sample]:
            print(f"\n  {p.passage_id}")
            print(f"    {p.text[:200]}")
    return 0


def cmd_convert(args) -> int:
    """The already-extracted corpus into the frame. No model calls, no spend."""
    from rishivan.koonji.pipeline import convert_books

    run = convert_books(
        out_dir=args.rules, books=args.book or None,
        limit=args.limit, write=not args.dry_run,
    )
    print(run.conversion)
    print()
    print(run.gate)
    if args.dry_run:
        print("\n(dry run - nothing written)")
    else:
        print(f"\nwritten in {run.elapsed_s:.1f}s:")
        for path in run.written:
            print(f"  {path}")
    return 0


def cmd_extract(args) -> int:
    """Re-read the verses with a model. This one costs money."""
    from rishivan.koonji.client import Budget, RecordingClient, VertexClient
    from rishivan.koonji.pipeline import extract_books

    budget = Budget(max_calls=args.max_calls)
    client = VertexClient(budget=budget, default_model=args.fast_model)
    if args.record:
        client = RecordingClient(client, args.record)

    def tick(i, total, result):
        note = result.skipped or f"{len(result.candidates)} candidate(s)"
        print(f"  [{i}/{total}] {result.passage.passage_id}  {note}")

    run = extract_books(
        client, out_dir=args.rules, books=args.book or None, limit=args.limit,
        write=not args.dry_run, fast_model=args.fast_model,
        deep_model=args.deep_model, on_passage=tick if args.verbose else None,
        workers=args.workers, single_call=args.single_call,
    )
    print()
    print(run)
    print(f"\nbudget: {budget}")
    if run.queue:
        print(f"\nreview queue, worst first ({len(run.queue)}):")
        for priority, rule_id, passage_id in run.queue[:20]:
            print(f"  {priority:5.2f}  {rule_id:38} {passage_id}")
    return 0


def cmd_restatements(args) -> int:
    """Rules that say the same thing. Three paraphrases are one source."""
    from rishivan.koonji.pipeline import detect_restatements

    groups = detect_restatements(_engine(args).bundle.rules)
    total = sum(len(ids) for ids in groups.values())
    print(f"{len(groups)} groups covering {total} rules\n")
    for signature, ids in sorted(groups.items(), key=lambda kv: -len(kv[1]))[: args.limit]:
        print(f"  {len(ids)} rules  [{signature[:70]}]")
        for rule_id in ids:
            print(f"      {rule_id}")
    return 0


def cmd_compile(args) -> int:
    result = compile_path(args.rules, seed_registry())
    for d in result.diagnostics:
        print(d, file=sys.stderr if d.severity == "error" else sys.stdout)
    if not result.ok:
        print(f"\n{len(result.errors)} error(s)", file=sys.stderr)
        return 1
    stats = result.index.stats() if result.index else {}
    print(f"compiled {len(result.rules)} rules  ·  {stats}")
    return 0


def cmd_lint(args) -> int:
    report = lint_bundle(_engine(args).bundle, size=args.charts)
    print(f"{report.charts} reference charts\n")
    for rule_id, rate in sorted(report.fire_rate.items(), key=lambda kv: -kv[1]):
        print(f"  {rate:7.2%}  {rule_id}")
    print()
    for finding in report.findings:
        print(f"  [{finding.severity}/{finding.lint}] {finding.rule_id}")
        print(f"      {finding.message}")
    return 0 if report.clean else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rishivan.koonji", description=__doc__)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    def birth_args(p):
        p.add_argument("--date", required=True, help="YYYY-MM-DD")
        p.add_argument("--time", default="12:00", help="HH:MM local")
        p.add_argument("--tz", type=float, default=5.5)
        p.add_argument("--lat", type=float, default=28.6139)
        p.add_argument("--lon", type=float, default=77.2090)
        p.add_argument("--place", default="")
        p.add_argument("--when", help="evaluate timing as of YYYY-MM-DD")
        p.add_argument("--candidate", action="store_true",
                       help="also serve unreviewed candidate rules")

    fire = sub.add_parser("fire", help="fire the corpus on a chart")
    birth_args(fire)
    fire.add_argument("--domain", action="append", help="restrict to a domain")
    fire.add_argument("--chart", action="store_true", help="print the chart too")
    fire.add_argument("-v", "--verbose", action="store_true")
    fire.set_defaults(func=cmd_fire)

    ask = sub.add_parser("ask", help="route a question, then fire what it selects")
    birth_args(ask)
    ask.add_argument("--question", required=True)
    ask.set_defaults(func=cmd_ask)

    trace = sub.add_parser("trace", help="the full audit chain as JSON")
    birth_args(trace)
    trace.set_defaults(func=cmd_trace)

    comp = sub.add_parser("compile", help="run every compiler pass")
    comp.set_defaults(func=cmd_compile)

    corpus = sub.add_parser("corpus", help="what books are loadable")
    corpus.add_argument("--book", action="append", help="restrict to a book id")
    corpus.add_argument("--sample", type=int, default=0, help="print N passages")
    corpus.set_defaults(func=cmd_corpus)

    conv = sub.add_parser("convert", help="already-extracted corpus -> rule YAML")
    conv.add_argument("--book", action="append")
    conv.add_argument("--limit", type=int, help="only the first N units")
    conv.add_argument("--dry-run", action="store_true")
    conv.set_defaults(func=cmd_convert)

    ext = sub.add_parser("extract", help="re-read the verses with a model (costs money)")
    ext.add_argument("--book", action="append")
    ext.add_argument("--limit", type=int, default=20,
                     help="passages to process. Defaults low on purpose; "
                          "0 means the whole book.")
    ext.add_argument("--max-calls", type=int, default=200,
                     help="hard ceiling on model calls. 0 disables it.")
    ext.add_argument("--fast-model", default="gemini-2.5-flash")
    ext.add_argument("--deep-model", default="gemini-2.5-pro")
    ext.add_argument("--single-call", action="store_true",
                     help="one call per passage: no classify, no dual extraction, no verifier. For when review is manual.")
    ext.add_argument("--workers", type=int, default=1,
                     help="concurrent passages. 1 (default) for a proving run")
    ext.add_argument("--record", help="write every exchange to this JSONL file")
    ext.add_argument("--dry-run", action="store_true")
    ext.add_argument("-v", "--verbose", action="store_true")
    ext.set_defaults(func=cmd_extract)

    rest = sub.add_parser("restatements", help="rules that are one rule")
    rest.add_argument("--limit", type=int, default=15)
    rest.set_defaults(func=cmd_restatements)

    lint = sub.add_parser("lint", help="behavioural lints over a reference corpus")
    lint.add_argument("--charts", type=int, default=400)
    lint.set_defaults(func=cmd_lint)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
