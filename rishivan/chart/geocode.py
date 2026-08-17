"""Live place-name -> latitude/longitude, via OpenStreetMap Nominatim.

DEMO ONLY, and unlike the chart engines, this call goes over the network —
the user explicitly chose live geocoding over an offline city table, which
means every lookup depends on Nominatim's public service being reachable.
Failures degrade to "keep whatever lat/lon is already there," never a
silent wrong coordinate.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_USER_AGENT = "rishivan-demo/1.0 (astrology birth-chart lookup)"

# Manual cache, not functools.lru_cache: a failed lookup (transient network
# blip, momentary Nominatim rate-limit) must be retried on the next attempt,
# not locked in for the rest of the process — lru_cache would memoize None
# just as permanently as a real result.
_cache: dict[str, tuple[float, float]] = {}


def geocode_place(place: str) -> tuple[float, float] | None:
    """Resolve a free-text place name to (lat, lon), or None if it can't be found."""
    place = (place or "").strip()
    if not place:
        return None
    if place in _cache:
        return _cache[place]
    try:
        import ssl

        import certifi
        from geopy.geocoders import Nominatim

        # Some local Python installs (notably python.org/Homebrew builds on
        # macOS) ship without the system CA bundle wired up, so the stdlib
        # urllib client geopy uses underneath fails every HTTPS request with
        # CERTIFICATE_VERIFY_FAILED — pinning certifi's bundle here sidesteps
        # that regardless of how the interpreter itself was installed.
        ctx = ssl.create_default_context(cafile=certifi.where())
        geolocator = Nominatim(user_agent=_USER_AGENT, timeout=6, ssl_context=ctx)
        location = geolocator.geocode(place)
    except Exception as exc:  # noqa: BLE001 — network/service failure, not our bug
        logger.warning("Geocoding failed for %r: %s", place, exc)
        return None
    if location is None:
        return None
    result = (round(location.latitude, 4), round(location.longitude, 4))
    _cache[place] = result
    return result
