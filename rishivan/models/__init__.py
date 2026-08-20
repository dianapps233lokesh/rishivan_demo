"""Model registry — trimmed for the demo.

**This is the one file that deliberately diverges from the backend's copy.**

In `rishivan_python` this module imports every model so that all of them register
on `Base.metadata` for Alembic autogenerate. The demo has no Alembic: the backend
owns the schema, and the bridge only reads and writes tables that already exist in
`rishivan_dev_local` (migrated there to revision 0017). So the registry's whole
reason for existing does not apply, and importing `billing`, `conversation`,
`admin`, `auth` or `astro` here would only drag their modules — and their own
dependencies — into a repo that has no use for them.

If a future demo feature needs one of those models, add just that import. Do not
restore the backend's full list: the point of the trim is that the demo stays
dependency-light.
"""

from rishivan.models import document  # noqa: F401
from rishivan.models.knowledge import (  # noqa: F401
    affinity,
    book,
    chapter,
    page,
    rule,
    run,
    unit,
)
