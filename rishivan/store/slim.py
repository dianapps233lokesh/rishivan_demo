"""Make a trace small enough to keep, without making it unusable.

A raw trace for one temperament question measured **222 KB**, and the Atlas
free tier is 512 MB — about 2,300 turns before writes start failing, with no
warning before they do. So the trace is trimmed before it is stored.

**What is dropped, and why it is recoverable.** 186 KB of that 222 was
`koonji.claims`, and inside it the `quote` field: the full verse text, carried
on every one of 122 support edges. The rule id is right beside it, and the rule
holds the verse — so the quote is a copy of the corpus inside the telemetry
database, and dropping it loses nothing that cannot be looked up.

**What is capped, and said out loud.** Firings and claims are capped, and the
document records how many there were. A truncated list that does not say it was
truncated reads as a complete one, and someone will later compute a statistic
over it.

**What is never dropped:** rule ids, citations, confidences, bands, what was
cancelled by what, counter-evidence, and every field of the answer plan. Those
are the reasons the trace exists.
"""

from __future__ import annotations

MAX_FIRINGS = 60
MAX_CLAIMS = 25
MAX_SUPPORTS = 8
"""Per claim. The strongest few carry the argument; the twentieth restatement
of one verse is what the evidence graph already discounts to zero."""


def _support(edge: dict) -> dict:
    """One support edge without its quote.

    `quote` was 517 of the ~600 bytes. The rule id stays, and the rule holds
    the verse, so this is a pointer replacing a copy.
    """
    return {
        "rule": edge.get("rule"),
        "citation": edge.get("citation"),
        "weight": edge.get("weight"),
        "independent": edge.get("independent"),
        "cluster": edge.get("cluster"),
    }


def _claim(claim: dict) -> dict:
    support = claim.get("support") or []
    against = claim.get("against") or []
    out = {
        "claim": claim.get("claim"),
        "confidence": claim.get("confidence"),
        "band": claim.get("band"),
        "independent_sources": claim.get("independent_sources"),
        "corroboration_met": claim.get("corroboration_met"),
        "requires_activation": claim.get("requires_activation"),
        "support": [_support(e) for e in support[:MAX_SUPPORTS]],
        # Counter-evidence is never capped away. It is the half every product
        # drops, and dropping it here would be dropping it at the last place
        # anyone could still check.
        "against": [_support(e) for e in against],
    }
    if len(support) > MAX_SUPPORTS:
        out["support_total"] = len(support)
    return out


def slim_koonji(trace: dict | None) -> dict | None:
    """The rule engine's audit chain, minus the corpus text."""
    if not trace:
        return None
    firings = trace.get("firings") or []
    claims = trace.get("claims") or []
    out = {
        "bundle_id": trace.get("bundle_id"),
        "registry": trace.get("registry"),
        "evaluated_at": trace.get("evaluated_at"),
        "elapsed_ms": trace.get("elapsed_ms"),
        "facts": trace.get("facts"),
        "retrieval": trace.get("retrieval"),
        "question": trace.get("question"),
        "firings": firings[:MAX_FIRINGS],
        "claims": [_claim(c) for c in claims[:MAX_CLAIMS]],
    }
    # Said out loud. A truncated list that does not admit it reads as a
    # complete one, and someone computes a statistic over it later.
    if len(firings) > MAX_FIRINGS:
        out["firings_total"] = len(firings)
    if len(claims) > MAX_CLAIMS:
        out["claims_total"] = len(claims)
    return out


def slim_trace(trace: dict) -> dict:
    """A whole trace, ready to store."""
    out = dict(trace)
    out["koonji"] = slim_koonji(trace.get("koonji"))
    return out
