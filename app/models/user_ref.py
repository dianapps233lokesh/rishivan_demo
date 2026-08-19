"""A metadata-only reference to the backend's `user` table.

`Rule.approved_by` and `ReviewTask.resolved_by` are foreign keys to `user.id`, and the
real `User` model lives in the production backend, not in this repo. Without something
named `user` in `Base.metadata`, SQLAlchemy cannot resolve those keys and *any* query
touching `rule` fails with:

    NoReferencedTableError: Foreign key associated with column 'rule.approved_by'
    could not find table 'user'

This is deliberately a bare `Table` with one column rather than a mapped class. The real
table has thirty-odd columns -- birth data, onboarding state, language preference -- and
a class declaring only `id` would look like a usable `User` model while silently
returning nothing for every other field. A `Table` cannot be mistaken for that: there is
no ORM entity to query, only enough schema for the foreign keys to resolve.

Do not add columns here. If this repo ever needs to read a user, port the real model.
"""

from sqlalchemy import BigInteger, Column, Table

from app.db.base import Base

user_table = Table(
    "user",
    Base.metadata,
    Column("id", BigInteger, primary_key=True),
)
"""Referenced by `rule.approved_by` and `review_task.resolved_by`."""
