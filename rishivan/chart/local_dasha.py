"""DEMO ONLY — Vimshottari Dasha table, for direct "show me my dasha" requests.

Pure arithmetic on the natal chart already computed (rishivan.chart.dasha),
so this works identically whether birth data came from the local Swiss
Ephemeris calc or the real P1 backend's varga facts.
"""

from __future__ import annotations

from datetime import datetime

from rishivan.chart.dasha import current_periods, mahadasha_timeline
from rishivan.chart.ephemeris import Chart


def dasha_table_markdown(chart: Chart, when: datetime | None = None) -> str | None:
    """Render the full Vimshottari Mahadasha timeline, with the currently
    running maha/antar/pratyantar periods marked, as a markdown table.

    None only if the chart has no Moon placement to derive the sequence
    from — callers should treat that as "unavailable", not substitute a
    different chart's timeline.
    """
    if chart is None or "Moon" not in chart.planets:
        return None
    when = when or datetime.now()

    timeline = mahadasha_timeline(chart)
    if not timeline:
        return None
    cur = current_periods(chart, when)

    lines = [
        "**Vimshottari Mahadasha Timeline**",
        "",
        "| Lord | Start | End | Status |",
        "|---|---|---|---|",
    ]
    for p in timeline:
        status = "**running**" if p.contains(when) else (
            "past" if p.end <= when else "upcoming"
        )
        lines.append(
            f"| {p.lord} | {p.start.date().isoformat()} | "
            f"{p.end.date().isoformat()} | {status} |"
        )

    if cur["antar"]:
        a = cur["antar"]
        lines.append("")
        lines.append(
            f"**Current Antardasha:** {a.lord} — "
            f"{a.start.date().isoformat()} to {a.end.date().isoformat()}"
        )
    if cur["pratyantar"]:
        pr = cur["pratyantar"]
        lines.append(
            f"**Current Pratyantardasha:** {pr.lord} — "
            f"{pr.start.date().isoformat()} to {pr.end.date().isoformat()}"
        )
    return "\n".join(lines)
