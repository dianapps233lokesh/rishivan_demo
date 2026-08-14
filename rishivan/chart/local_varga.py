"""DEMO ONLY — local divisional (varga) chart computation.

Uses the SAME pure-arithmetic sign-mapping formulas as the real P1 backend
(vendored as rishivan.chart.vendor.varga — zero IO, zero LLM), so D9/D10/etc.
compute correctly without that backend's HTTP server, database, or auth
needing to be running. Also more correct than calling that backend: the
remote varga endpoint answers for a fixed demo user, not for whatever birth
details were just typed into this demo's own form.

Vendored rather than imported across the filesystem from the main repo:
rishivan_demo deploys as its own standalone Streamlit Cloud app, where the
main repo's app/ directory does not exist.
"""

from __future__ import annotations

from rishivan.chart.ephemeris import NAKSHATRA_ARC, NAKSHATRAS, PADA_ARC, RASHIS, Chart

_PLANET_ORDER = [
    "Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu",
]


def _load_varga_engine():
    from rishivan.chart.vendor import varga
    return varga


def _nakshatra_of(longitude: float) -> tuple[str, int]:
    idx = int(longitude // NAKSHATRA_ARC) % 27
    pada = int((longitude % NAKSHATRA_ARC) // PADA_ARC) + 1
    return NAKSHATRAS[idx], pada


def _varga_positions(chart: Chart, code: str):
    """Shared per-planet varga computation.

    Returns (lagna_sign_idx, {name: (sign_idx, house, nakshatra, pada)}), or
    None if the varga engine can't be imported or doesn't know `code`.
    """
    varga = _load_varga_engine()
    if varga is None or code not in varga.VARGA_REGISTRY:
        return None

    asc_lon = varga.varga_longitude(code, chart.ascendant_longitude)
    lagna_sign = int(asc_lon // 30.0) % 12

    positions = {}
    for name in _PLANET_ORDER:
        p = chart.planets[name]
        v_lon = varga.varga_longitude(code, p.longitude)
        sign_idx = int(v_lon // 30.0) % 12
        house = (sign_idx - lagna_sign) % 12 + 1
        nakshatra, pada = _nakshatra_of(v_lon)
        positions[name] = (sign_idx, house, nakshatra, pada)
    return lagna_sign, positions


def varga_table_markdown(chart: Chart, code: str) -> str | None:
    """Render one divisional chart as a markdown table, computed locally.

    None if the varga engine can't be imported or doesn't know `code` —
    callers must treat that as "unavailable", never fall back to the D1
    table mislabelled as this code.
    """
    varga = _load_varga_engine()
    if varga is None or code not in varga.VARGA_REGISTRY:
        return None
    positions_result = _varga_positions(chart, code)
    if positions_result is None:
        return None
    lagna_sign, positions = positions_result

    spec = varga.VARGA_REGISTRY[code]
    asc_lon = varga.varga_longitude(code, chart.ascendant_longitude)

    lines = [
        f"**{spec.name} ({code})**",
        f"**Ascendant:** {RASHIS[lagna_sign]} ({asc_lon % 30:.2f}°)",
        "",
        "| Planet | Sign | House | Nakshatra | Pada | Retrograde |",
        "|---|---|---|---|---|---|",
    ]
    for name in _PLANET_ORDER:
        sign_idx, house, nakshatra, pada = positions[name]
        p = chart.planets[name]
        lines.append(
            f"| {name} | {RASHIS[sign_idx]} | {house} | {nakshatra} | {pada} | "
            f"{'Yes' if p.retrograde else 'No'} |"
        )
    return "\n".join(lines)


def varga_facts(chart: Chart, code: str) -> list[str] | None:
    """Plain-language D9/D10/etc. placements — ground truth for the Rishi
    to interpret, computed with the same local, zero-IO engine as
    varga_table_markdown. None if the varga engine is unavailable or
    doesn't know `code`; callers should treat that as "no data", never
    substitute a different varga's placements.
    """
    varga = _load_varga_engine()
    if varga is None or code not in varga.VARGA_REGISTRY:
        return None
    positions_result = _varga_positions(chart, code)
    if positions_result is None:
        return None
    lagna_sign, positions = positions_result

    spec = varga.VARGA_REGISTRY[code]
    facts = [f"In your {spec.name} ({code}): Ascendant is {RASHIS[lagna_sign]}."]
    for name in _PLANET_ORDER:
        sign_idx, house, nakshatra, pada = positions[name]
        retro = " (retrograde)" if chart.planets[name].retrograde else ""
        facts.append(
            f"{spec.name} ({code}): {name} is in {RASHIS[sign_idx]} in the house "
            f"{house} ({nakshatra} nakshatra, pada {pada}){retro}."
        )
    return facts
