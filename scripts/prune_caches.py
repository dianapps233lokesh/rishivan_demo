"""List and delete leftover Vertex context caches.

    uv run python -m scripts.prune_caches
    uv run python -m scripts.prune_caches --delete

Cache storage bills per token-hour, so one the runner failed to delete keeps costing
until its TTL expires. Uses a direct client: `caches.delete` through the Helicone
gateway returns `500 Body has already been used`, which is how the first leak happened.
"""

import argparse

from rishivan.knowledge.extract.runner import build_admin_client


def main() -> int:
    parser = argparse.ArgumentParser(description="list or delete context caches")
    parser.add_argument("--delete", action="store_true", help="actually delete them")
    args = parser.parse_args()

    client = build_admin_client()
    caches = list(client.caches.list())
    if not caches:
        print("no caches")
        return 0
    for cache in caches:
        tokens = cache.usage_metadata.total_token_count if cache.usage_metadata else 0
        print(f"{cache.display_name or '(unnamed)':24s} {tokens:>8,d} tokens  "
              f"expires {cache.expire_time}  {cache.name}")
        if args.delete:
            client.caches.delete(name=cache.name)
            print("  deleted")
    if not args.delete:
        print(f"\n{len(caches)} cache(s); pass --delete to remove")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
