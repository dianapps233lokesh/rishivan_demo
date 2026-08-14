"""DEMO ONLY — local numerology (mulank/bhagyaank) computation.

Same reasoning as local_varga.py: the pure-arithmetic numerology engine
(vendored as rishivan.chart.vendor.numbers — zero IO, zero DB) computes
these from the date of birth alone, without any backend server, database,
or auth needing to be running.
"""

from __future__ import annotations

from datetime import date

from rishivan.chart.ephemeris import BirthData, Chart


def _load_numerology_engine():
    from rishivan.chart.vendor import numbers
    return numbers


def numerology_table_markdown(birth: BirthData, chart: Chart | None = None) -> str | None:
    """Render Mulank and Bhagyaank as a markdown table.

    None if the numerology engine can't be imported — callers must treat
    that as "unavailable", never guess at the numbers.
    """
    numbers = _load_numerology_engine()
    if numbers is None:
        return None

    dob = date(birth.year, birth.month, birth.day)
    lines = [
        "**Numerology**",
        "",
        "| Number | Value |",
        "|---|---|",
        f"| Mulank (birth number) | {numbers.mulank(dob)} |",
        f"| Bhagyaank (destiny number) | {numbers.bhagyaank(dob)} |",
    ]
    if chart is not None:
        moon = chart.planets["Moon"]
        lines.append(f"| Moon Rashi | {moon.rashi} |")
        lines.append(f"| Birth Nakshatra | {moon.nakshatra} (pada {moon.pada}) |")
    return "\n".join(lines)
