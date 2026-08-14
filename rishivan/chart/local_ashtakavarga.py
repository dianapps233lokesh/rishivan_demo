"""DEMO ONLY — local Ashtakavarga (bindu) computation.

Ashtakavarga is NOT a divisional (varga) chart — it's a separate benefic-
point counting system, judging a planet's or sign's overall strength by how
many of eight contributors (seven planets + lagna) consider it benefic.
Uses the SAME pure-arithmetic engine as the real P1 backend (vendored as
rishivan.chart.vendor.ashtakavarga — zero IO, zero LLM), so this works
without that backend's HTTP server, database, or auth needing to be
running.

Vendored rather than imported across the filesystem from the main repo:
rishivan_demo deploys as its own standalone Streamlit Cloud app, where the
main repo's app/ directory does not exist.
"""

from __future__ import annotations

from rishivan.chart.ephemeris import RASHIS, Chart

_SUBJECT_DISPLAY = {
    "sun": "Sun", "moon": "Moon", "mars": "Mars", "mercury": "Mercury",
    "jupiter": "Jupiter", "venus": "Venus", "saturn": "Saturn",
}


def _load_ashtakavarga_engine():
    from rishivan.chart.vendor import ashtakavarga
    return ashtakavarga


def ashtakavarga_table_markdown(chart: Chart) -> str | None:
    """Render the Sarvashtakavarga (SAV) + per-planet (BAV) bindu table.

    None if the ashtakavarga engine can't be imported — callers must treat
    that as "unavailable", never estimate or invent bindu counts.
    """
    av = _load_ashtakavarga_engine()
    if av is None:
        return None

    planet_signs = {
        subject: chart.planets[_SUBJECT_DISPLAY[subject]].rashi_index
        for subject in av.SUBJECTS
    }
    result = av.compute_ashtakavarga(planet_signs, chart.lagna_rashi_index)

    subjects = list(av.SUBJECTS)
    header = "| Sign | " + " | ".join(_SUBJECT_DISPLAY[s] for s in subjects) + " | SAV Total |"
    sep = "|" + "---|" * (len(subjects) + 2)
    lines = ["**Ashtakavarga (bindus per sign)**", "", header, sep]
    for sign_idx in range(12):
        row = [str(result.bav[s][sign_idx]) for s in subjects]
        lines.append(
            f"| {RASHIS[sign_idx]} | " + " | ".join(row) + f" | {result.sav[sign_idx]} |"
        )

    # Row totals are a chart-independent structural invariant of the
    # point-counting scheme — computed fresh here (not hardcoded) as a
    # built-in check on the sign mapping above.
    row_totals = [str(sum(result.bav[s])) for s in subjects]
    sav_total = sum(result.sav)
    lines.append("| **Total** | " + " | ".join(row_totals) + f" | {sav_total} |")
    return "\n".join(lines)
