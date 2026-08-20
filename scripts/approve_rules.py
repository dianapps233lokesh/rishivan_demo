"""Approve rules so they can reach a user. The one gate that matters.

    uv run python -m scripts.approve_rules --report
    uv run python -m scripts.approve_rules --chapter 26 --dry-run
    uv run python -m scripts.approve_rules --chapter 26 --reviewer 1

`MATCHABLE_PREDICATE` is `status = 'parsed' AND approved_at IS NOT NULL AND deleted_at IS
NULL`, so until a rule is approved here it is invisible to the matcher no matter how well
the matcher works. That is the whole point: 376 rules passed a deterministic validator, and
a validator is evidence rather than proof. This repo has already seen its validator be
wrong -- it once relabelled every empty formation as `category: timing`, which let six
definitional verses through as valid rules.

So approval is deliberately awkward in two ways:

* **It is per chapter, never "all".** A reviewer approving 376 rules in one command has not
  reviewed 376 rules. `--chapter` forces the work to be done in reviewable batches, and
  `--report` shows which batches are outstanding.
* **It records who.** `approved_by` takes a real user id. An approval with no owner is
  indistinguishable from an auto-approval, which is the thing this gate exists to prevent.

There is no bulk unapprove because there is no need to be quick about it; `--revoke`
handles one chapter at a time by the same rule.
"""

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from rishivan.db.session import async_session_factory
from rishivan.models.knowledge.rule import Rule


async def report(session) -> None:
    """Approval state per chapter, so a reviewer can see what is outstanding.

    Aggregated in Python rather than in SQL. Grouping by a JSONB path expression needs the
    identical expression in GROUP BY, and pairing it with a numeric ORDER BY cast produced
    `column "rule.source" must appear in the GROUP BY clause`. At 398 rows the SQL saves
    nothing worth that.
    """
    rows = await session.execute(
        select(Rule.source["chapter"].astext, Rule.approved_at).where(
            Rule.status == "parsed", Rule.deleted_at.is_(None)
        )
    )
    tally: dict[str, list[int]] = {}
    for chapter, approved_at in rows:
        counts = tally.setdefault(chapter or "?", [0, 0])
        counts[0] += 1
        counts[1] += 1 if approved_at is not None else 0

    def order(chapter: str) -> tuple[int, str]:
        return (int(chapter), "") if chapter.isdigit() else (10**6, chapter)

    print(f"{'chapter':>8}  {'approved':>8}  {'total':>6}")
    total = approved = 0
    for chapter in sorted(tally, key=order):
        count, ok = tally[chapter]
        print(f"{chapter:>8}  {ok:>8}  {count:>6}")
        total += count
        approved += ok
    print(f"{'ALL':>8}  {approved:>8}  {total:>6}")
    if approved == 0:
        print("\nnothing is approved, so match_chart returns nothing. That is correct "
              "until a human has read some of it.")


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="approve extracted rules for use")
    parser.add_argument("--report", action="store_true", help="show approval state")
    parser.add_argument("--chapter", help="approve one chapter's rules")
    parser.add_argument(
        "--all",
        dest="approve_all",
        action="store_true",
        help="approve EVERY parsed rule at once. This is a bulk enablement, not a "
        "review, and the printed record says so",
    )
    parser.add_argument("--revoke", action="store_true", help="unapprove instead")
    parser.add_argument(
        "--reviewer",
        type=int,
        help="user id doing the approving; required unless --dry-run",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    async with async_session_factory() as session:
        if args.report or not (args.chapter or args.approve_all):
            await report(session)
            if not (args.chapter or args.approve_all):
                return 0

        if not args.revoke and args.reviewer is None and not args.dry_run:
            parser.error(
                "--reviewer is required to approve: an approval with no owner is "
                "indistinguishable from an auto-approval"
            )

        conditions = [Rule.status == "parsed", Rule.deleted_at.is_(None)]
        if not args.approve_all:
            conditions.append(Rule.source["chapter"].astext == str(args.chapter))
        rules = list(
            (await session.execute(select(Rule).where(*conditions))).scalars()
        )
        if not rules:
            print(f"no parsed rules in chapter {args.chapter}")
            return 1
        if args.approve_all and not args.revoke:
            # Said plainly rather than buried. These rules passed a deterministic
            # validator at 90% precision; a validator is evidence, not proof, and this
            # repo has already seen its own validator be wrong. Approving in bulk means
            # accepting that ~1 in 10 may be defective.
            print(
                f"BULK APPROVAL of {len(rules)} rules without per-chapter review. "
                f"These passed the validator at ~90% measured precision, so expect "
                f"roughly {len(rules) // 10} defective rules to become user-visible."
            )

        for rule in rules:
            rule.approved_at = None if args.revoke else datetime.now(UTC)
            rule.approved_by = None if args.revoke else args.reviewer

        verb = "revoked" if args.revoke else "approved"
        scope = "ALL chapters" if args.approve_all else f"chapter {args.chapter}"
        print(f"{verb} {len(rules)} rules in {scope}")
        if args.dry_run:
            print("dry run: rolling back")
            await session.rollback()
        else:
            await session.commit()
            print("committed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
