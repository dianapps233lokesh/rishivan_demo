"""Load an extraction artefact into the rule base.

    uv run python -m scripts.load_koonji koonji-bphs-vol1.json --dry-run
    uv run python -m scripts.load_koonji koonji-bphs-vol1.json --book bphs-gcsharma-vol1

Accepts either the streaming JSONL checkpoint or the final JSON array, because a run that
was interrupted only has the former.

Nothing loaded here is approved. `MATCHABLE_PREDICATE` requires `approved_at IS NOT
NULL`, and this script always leaves it null, so the rules are queryable by a reviewer
and unreachable by a user until someone approves them deliberately.
"""

import argparse
import asyncio
import json
import sys

from app.db.session import async_session_factory
from app.knowledge.compile.persist import load_rules

MAX_FAILURES_SHOWN = 25


def read_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        if path.endswith(".jsonl"):
            return [json.loads(line) for line in handle if line.strip()]
        return json.load(handle)


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="load extracted Koonji rules")
    parser.add_argument("path")
    parser.add_argument("--book", default="bphs-gcsharma-vol1")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be written, then roll back",
    )
    args = parser.parse_args(argv)

    rows = read_rows(args.path)
    print(f"{len(rows)} extraction rows from {args.path}")

    async with async_session_factory() as session:
        report = await load_rules(session, rows=rows, book_slug=args.book)
        print(report.line())
        for failure in report.failures[:MAX_FAILURES_SHOWN]:
            print(f"  refused {failure}", file=sys.stderr)
        remaining = len(report.failures) - MAX_FAILURES_SHOWN
        if remaining > 0:
            print(f"  ... and {remaining} more", file=sys.stderr)

        if args.dry_run:
            print("dry run: rolling back")
            await session.rollback()
        else:
            await session.commit()
            print(
                "committed. Every rule has approved_at=NULL, so none is matchable yet — "
                "review and approve before exporting."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
