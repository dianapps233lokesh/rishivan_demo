"""Write each rule's Rishi affinity vector, derived from its life domains.

    uv run python -m scripts.enrich_affinity --dry-run
    uv run python -m scripts.enrich_affinity

Separate from extraction on purpose: affinity follows from the rule, not the verse, so
re-tuning is a second-long pass over the database rather than a 34-minute re-read of the
book. Idempotent — it rewrites every vector from the current keyword table.
"""

import argparse
import asyncio
import collections

from sqlalchemy import select

from rishivan.db.session import async_session_factory
from rishivan.knowledge.affinity.derive import affinity_for, unrouted_domains
from rishivan.models.knowledge.rule import Rule


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="derive per-rule Rishi affinity")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    async with async_session_factory() as session:
        rules = list(
            (
                await session.execute(
                    select(Rule).where(Rule.deleted_at.is_(None))
                )
            ).scalars()
        )
        reach: collections.Counter = collections.Counter()
        unrouted = unrouted_domains([rule.life_domains or [] for rule in rules])
        changed = 0
        without = 0

        for rule in rules:
            weights = affinity_for(rule.life_domains)
            if not weights:
                without += 1
            # keys, not the dict: updating with a dict SUMS the float weights
            # and reports 178.6 rules for atma instead of 179.
            reach.update(weights.keys())
            effect = dict(rule.effect or {})
            if effect.get("rishi_affinity") != weights:
                effect["rishi_affinity"] = weights
                rule.effect = effect
                changed += 1

        print(f"{len(rules)} rules; {changed} affinity vectors written")
        print(f"rules with no derivable affinity: {without}")
        if unrouted:
            print(f"UNROUTED domain values ({len(unrouted)}): {sorted(unrouted)}")
            print("  each one is a rule no Rishi can cite; extend LIFE_DOMAIN_KEYWORDS")
        print("\nrules reachable per Rishi:")
        for rishi, count in reach.most_common():
            print(f"  {count:>4}  {rishi}")

        if args.dry_run:
            print("\ndry run: rolling back")
            await session.rollback()
        else:
            await session.commit()
            print("\ncommitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
