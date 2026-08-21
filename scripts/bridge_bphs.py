"""Bridge BPHS from the POC ingestion layer into the knowledge pipeline.

    uv run python -m scripts.bridge_bphs
    uv run python -m scripts.bridge_bphs --volume bphs-gcsharma-vol1 --dry-run

Deterministic and idempotent: no LLM call, and a second run inserts nothing.

Some orphaned verses are genuine — BPHS prints six chapter-final verses with no English
rendering, several as bare Sanskrit formulae — so those units are flagged `needs_review`
rather than refused. What is refused is a *regression*: exceeding `--max-violations`
means the bridge has started severing pairings that were intact. The zero-tolerance gate
lives on the hand-checked golden set, `make gate-adjacency`.
"""

import argparse
import asyncio
import sys

from rishivan.db.session import async_session_factory
from rishivan.knowledge.bridge.persist import bridge_book
from rishivan.models.knowledge.affinity import RISHI_KEYS, WEIGHT_HIGH

BPHS_VOLUMES: tuple[tuple[str, str], ...] = (
    ("bphs-gcsharma-vol1", "Brihat Parasara Hora Shastra"),
    ("bphs-gcsharma-vol2", "Brihat Parasara Hora Shastra"),
)

BPHS_RISHI_WEIGHTS: dict[str, float] = {key: WEIGHT_HIGH for key in RISHI_KEYS}
"""BPHS is the one source family the client's matrix rates High for all eight
Rishis, which is exactly why it is the pilot book: a single volume pair exercises
the whole affinity vector rather than one corner of it."""

MAX_VIOLATIONS_SHOWN = 20

BASELINE_VIOLATIONS = 6
"""Orphaned verses known to be genuine in BPHS: 4 in vol 1, 2 in vol 2.

Each is a chapter's final verse that the book prints with no English rendering,
several in the Shadbala chapters set as bare Sanskrit formulae. Measured, not
assumed — see docs/reports/2026-08-18-m1-bphs-bridge.md. Exceeding this means the
bridge has regressed and started severing pairings that were intact, so it fails.
Lower it if the count ever drops; never raise it to make a run pass.
"""


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bridge BPHS into the knowledge layer (deterministic, no LLM)"
    )
    parser.add_argument("--volume", help="bridge only this document slug")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be written, then roll back",
    )
    parser.add_argument(
        "--max-violations",
        type=int,
        default=BASELINE_VIOLATIONS,
        help=(
            "fail if orphaned verses exceed this count "
            f"(default {BASELINE_VIOLATIONS}, the known-genuine baseline)"
        ),
    )
    args = parser.parse_args(argv)

    targets = [
        (slug, title)
        for slug, title in BPHS_VOLUMES
        if args.volume is None or slug == args.volume
    ]
    if not targets:
        known = ", ".join(slug for slug, _ in BPHS_VOLUMES)
        print(f"no such volume {args.volume!r}; known: {known}", file=sys.stderr)
        return 2

    total_violations = 0
    async with async_session_factory() as session:
        for slug, title in targets:
            report = await bridge_book(
                session,
                document_slug=slug,
                book_title=title,
                rishi_weights=BPHS_RISHI_WEIGHTS,
                source_authority_tier="S0",
            )
            print(
                f"{slug}: chapters={report.chapters} pages={report.pages} "
                f"elements={report.elements} units={report.units} "
                f"inserted={report.inserted} skipped={report.skipped} "
                f"inferred_refs={report.inferred_verse_refs} "
                f"ref_disagreements={report.ref_disagreements} "
                f"collapsed_dupes={report.collapsed_duplicates} "
                f"violations={len(report.violations)}"
            )
            for violation in report.violations[:MAX_VIOLATIONS_SHOWN]:
                print(f"  orphan {violation}".replace("\n", " / "), file=sys.stderr)
            remaining = len(report.violations) - MAX_VIOLATIONS_SHOWN
            if remaining > 0:
                print(f"  ... and {remaining} more", file=sys.stderr)
            total_violations += len(report.violations)

        if total_violations > args.max_violations:
            print(
                f"rolled back: {total_violations} orphaned verses exceeds the "
                f"baseline of {args.max_violations} — the bridge has regressed and "
                f"is severing pairings that were previously intact",
                file=sys.stderr,
            )
            await session.rollback()
            return 1
        if total_violations:
            print(
                f"{total_violations} orphaned verses, within the baseline of "
                f"{args.max_violations}; flagged needs_review"
            )
        if args.dry_run:
            print("dry run: rolling back")
            await session.rollback()
            return 0
        await session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
