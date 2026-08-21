"""Remove the labels the POC extractor prepended to every element's content.

Rows arrive shaped like::

    [Heading: Brihat Parasara Hora Shastra 197] | Original Content: | शिरो ॥१२॥

Neither label is part of the book. `[Heading: ...]` is the page's running head,
duplicated onto every element on that page; `Original Content:` is a field label
from the extractor's own JSON. Left in place, the first puts a running head
inside a verse and inside every citation quoting it, and the second corrupts the
Devanagari a reviewer has to compare against the scan.
"""

import re

_HEADING_PREFIX = re.compile(r"^\s*\[Heading:[^\]]*\]\s*\|?\s*")
_ORIGINAL_CONTENT = re.compile(r"^\s*Original Content\s*:\s*\|?\s*", re.IGNORECASE)


def strip_ingestion_prefixes(raw: str) -> str:
    """Strip the POC's `[Heading: ...]` and `Original Content:` labels.

    Idempotent: applying it twice equals applying it once. That matters because
    the bridge is re-runnable, so it may meet rows that a previous run already
    cleaned, and a second pass must not start eating real text.
    """
    if not raw:
        return ""
    text = _HEADING_PREFIX.sub("", raw)
    text = _ORIGINAL_CONTENT.sub("", text)
    return text.strip()
