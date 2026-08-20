"""Extract a small sample of Koonji rules for human review, then stop.

Writes nothing to the `rule` table. The point is to put real extractions in front of a
person before spending on 1,144 units -- the two hard gates (verse pairing, generated
tests) and the >=0.90 precision target all depend on a human confirming the output is
what the book actually says.

    uv run python -m scripts.extract_sample --limit 12
    uv run python -m scripts.extract_sample --limit 12 --json output.json

Writes `output.json` in the repo root by default: a review artefact belongs somewhere a
person can open, not in a temp directory that the next reboot clears.
"""

import argparse
import asyncio
import json
import time

from rishivan.db.session import async_session_factory
from rishivan.knowledge.extract.runner import run_extraction


def verdict(extracted) -> str:
    """DECLINED is not a third grade of failure. It means the extractor read the verse,
    found the vocabulary could not express it, and said so with a reason -- the correct
    outcome for BPHS's methodology, shadbala and benefic/malefic verses. It is reported
    separately so precision is measured over rules that were actually attempted."""
    if extracted.declined:
        return "DECLINED" if extracted.ok else "DECLINED (no reason given)"
    return "VALID" if extracted.ok else "INVALID"


def render(extracted) -> str:
    rule = extracted.rule
    lines = [
        f"── ch{extracted.chapter}.{extracted.verse_ref}  "
        f"[{verdict(extracted)}]  "
        f"category={rule.get('rule_category')}",
        f"   key       : {rule.get('rule_key')}",
        f"   verse     : {(extracted.translation or '')[:200]}",
        f"   formation : {json.dumps(rule.get('formation') or {})}",
    ]
    timing = (rule.get("timing") or {}).get("activation_factors") or {}
    if timing.get("atoms"):
        lines.append(f"   timing    : {json.dumps(timing)}")
    for effect in rule.get("effects") or []:
        lines.append(
            f"   effect    : [{effect.get('polarity')}/{effect.get('strength')}] "
            f"{effect.get('statement')}"
        )
    for modifier in rule.get("modifiers") or []:
        lines.append(
            f"   modifier  : {modifier.get('kind')} "
            f"{json.dumps(modifier.get('condition') or {})}"
        )
    for exception in rule.get("exceptions") or []:
        lines.append(
            f"   exception : {exception.get('statement') or json.dumps(exception.get('condition') or {})}"
            f"{'  (from commentary)' if exception.get('from_commentary') else ''}"
        )
    for remedy in rule.get("remedies") or []:
        lines.append(f"   remedy    : {remedy}")
    if rule.get("out_of_scope_reason"):
        lines.append(f"   out_of_scope: {rule['out_of_scope_reason']}")
    if not extracted.ok:
        for problem in extracted.validation.problems:
            lines.append(f"   ! {problem}")
    return "\n".join(lines)


def as_row(extracted) -> dict:
    """The review artefact's row shape, shared by the checkpoint and the final JSON so
    the two cannot describe the same rule differently."""
    return {
        "unit_id": extracted.unit_id,
        "chapter": extracted.chapter,
        "verse_ref": extracted.verse_ref,
        "verdict": verdict(extracted),
        "valid": extracted.ok,
        "translation": extracted.translation,
        "problems": [str(p) for p in extracted.validation.problems],
        "rule": extracted.rule,
    }


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="extract a review sample")
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--book", default="bphs-gcsharma-vol1")
    parser.add_argument(
        "--nth",
        type=int,
        default=1,
        help="which unit within each chapter to sample (default 1). Raise it to probe "
        "the body of the chapter instead of its 'now I explain to you...' preamble",
    )
    parser.add_argument(
        "--all",
        dest="whole_book",
        action="store_true",
        help="extract EVERY rule-destined unit in the book instead of one per chapter. "
        "Without this the run is a per-chapter review sample, which is why a run given "
        "--limit 2000 once covered 30 units and exited looking successful",
    )
    parser.add_argument(
        "--checkpoint",
        default="",
        help="append each result to this JSONL as it is produced, so a run that dies "
        "at unit 484 of 485 keeps the 483 calls it already paid for",
    )
    parser.add_argument(
        "--json",
        dest="json_path",
        default="output.json",
        help="where to write the raw JSON for review (default: output.json in the "
        "repo root, so a reviewer can find it without hunting through /tmp)",
    )
    args = parser.parse_args(argv)

    handle = open(args.checkpoint, "a", encoding="utf-8") if args.checkpoint else None
    seen: set[int] = set()
    started = time.monotonic()
    total = [0]

    def announce(units: int) -> None:
        total[0] = units
        print(f"units to extract: {units}", flush=True)

    def checkpoint(extracted, report) -> None:
        """Write-through plus one progress line per unit.

        Both halves matter for a run this long. A whole-book run that prints nothing
        until it finishes is indistinguishable from a hung one, and without the JSONL a
        crash at unit 484 of 485 throws away 483 calls that were already paid for.
        Every line carries the running precision, so a run that starts degrading is
        visible while it is still cheap to stop.
        """
        if extracted.unit_id not in seen:
            seen.add(extracted.unit_id)
            done = len(seen)
            elapsed = time.monotonic() - started
            rate = done / elapsed if elapsed else 0
            remaining = (total[0] - done) / rate if rate and total[0] else 0
            print(
                f"[{done:>4}/{total[0]}] ch{extracted.chapter}.{extracted.verse_ref:<9} "
                f"rules={report.rules:<4} valid={report.valid:<4} "
                f"declined={report.declined:<4} invalid={report.invalid:<3} "
                f"prec={report.precision:>4.0%}  "
                f"{elapsed / 60:>5.1f}m elapsed, ~{remaining / 60:.0f}m left",
                flush=True,
            )
        if handle is not None:
            handle.write(json.dumps(as_row(extracted), ensure_ascii=False) + "\n")
            handle.flush()

    try:
        async with async_session_factory() as session:
            report = await run_extraction(
                session,
                book_slug=args.book,
                limit=args.limit,
                offset=args.offset,
                nth=None if args.whole_book else args.nth,
                on_result=checkpoint,
                on_start=announce,
            )
    finally:
        if handle is not None:
            handle.close()

    print()
    # A whole-book run has already streamed one line per unit; re-rendering 800 rules
    # here would bury the summary and the failures under it.
    if not args.whole_book:
        for extracted in report.extracted:
            print(render(extracted))
            print()
    for failure in report.failures:
        print(f"CALL FAILED  {failure}")
    print(report.line())

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as handle:
            json.dump(
                [as_row(e) for e in report.extracted],
                handle,
                ensure_ascii=False,
                indent=2,
            )
        print(f"wrote {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
