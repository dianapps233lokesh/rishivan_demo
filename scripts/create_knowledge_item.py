"""Create the destination-B tables (`knowledge_item`, `unit_triage`) if absent.

    uv run python -m scripts.create_knowledge_item
    uv run python -m scripts.create_knowledge_item --sql

A script rather than an Alembic revision because the backend repo owns this database's
schema, and vendoring migrations would mean two things claiming that ownership. Built
from the model's own metadata so it cannot drift, and idempotent.

**The backend must still add the matching revision** before this table reaches any
environment it migrates; `--sql` prints the DDL to paste in.
"""

import argparse
import asyncio
import sys

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateIndex, CreateTable

from rishivan.db.session import engine
from rishivan.models.knowledge.item import KnowledgeItem
from rishivan.models.knowledge.triage import UnitTriage

TABLES = (KnowledgeItem.__table__, UnitTriage.__table__)


def print_ddl() -> None:
    from sqlalchemy.dialects import postgresql

    dialect = postgresql.dialect()
    for table in TABLES:
        print(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in table.indexes:
            print(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
        print()


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="create the destination-B tables if absent")
    parser.add_argument("--sql", action="store_true", help="print DDL and exit")
    args = parser.parse_args(argv)

    if args.sql:
        print_ddl()
        return 0

    created_any = False
    async with engine.begin() as conn:
        for table in TABLES:
            existed = await conn.run_sync(
                lambda sync_conn, name=table.name: inspect(sync_conn).has_table(name)
            )
            await conn.run_sync(
                table.metadata.create_all, tables=[table], checkfirst=True
            )
            count = (
                await conn.execute(text(f"select count(*) from {table.name}"))
            ).scalar()
            created_any = created_any or not existed
            print(
                f"{table.name}: {'already existed' if existed else 'CREATED'}; "
                f"rows={count}; columns={len(table.columns)}; "
                f"indexes={len(table.indexes)}"
            )

    if created_any:
        print(
            "reminder: add the matching Alembic revision in rishivan_python "
            "(--sql prints the DDL)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
