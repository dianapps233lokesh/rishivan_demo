"""Bridge to the real P1 backend's chart engine — all 16 vargas, not just D1.

Used only when BACKEND_URL/BACKEND_DEMO_TOKEN are configured (see
rishivan.config); otherwise the caller falls back to this demo's own
Swiss Ephemeris D1-only computation, unchanged. Produces plain-language
fact strings in the same style as rishivan.chart.facts.derive_facts, so
they drop straight into the existing prompt/retrieval pipeline with no
other changes needed.
"""

from __future__ import annotations

import httpx

from rishivan.config import settings

VARGAS_FOR_DEMO = ("D1", "D9", "D10")
"""Rashi (whole chart), Navamsa (marriage/fortune), Dashamsha (career) — the
three vargas demo questions actually ask about. Fetching all 16 would be
correct but adds latency for no benefit today; add more codes here freely."""

REQUEST_TIMEOUT_S = 10.0


def available() -> bool:
    return bool(settings.BACKEND_URL and settings.BACKEND_DEMO_TOKEN)


def _varga_facts(payload: dict) -> list[str]:
    lines = [f"In your {payload['name']} ({payload['code']}):"]
    lines.append(
        f"Ascendant is {payload['ascendant']['sign']} "
        f"({payload['ascendant']['degree']})."
    )
    for planet in payload["planets"]:
        retro = " (retrograde)" if planet["retrograde"] else ""
        lines.append(
            f"{planet['name']} is in {planet['sign']} in the house "
            f"{planet['house']} ({planet['nakshatra']} nakshatra, "
            f"pada {planet['pada']}){retro}."
        )
    return lines


def fetch_real_chart_facts() -> list[str] | None:
    """Real varga facts from the P1 backend, or None if unavailable.

    Birth details must already have been submitted for the fixed demo user
    via the main repo's onboarding flow / scripts/seed_demo_user.py — this
    only reads, it never submits birth details itself.
    """
    if not available():
        return None

    facts: list[str] = []
    try:
        with httpx.Client(
            base_url=settings.BACKEND_URL,
            headers={"Authorization": f"Bearer {settings.BACKEND_DEMO_TOKEN}"},
            timeout=REQUEST_TIMEOUT_S,
        ) as client:
            for code in VARGAS_FOR_DEMO:
                response = client.get(f"/api/v1/charts/varga/{code}")
                if response.status_code != 200:
                    continue
                facts.extend(_varga_facts(response.json()["data"]))
    except httpx.HTTPError:
        return None

    return facts or None
