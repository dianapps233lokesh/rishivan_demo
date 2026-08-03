"""Query-moment / transit chart computation.

For muhurta and prashna, the chart is cast at the moment of the query (or the
target moment the user is asking about), not at birth.  This module wraps the
existing ``compute_chart`` with a datetime → BirthData adapter.
"""

from __future__ import annotations

from datetime import datetime

from rishivan.chart.ephemeris import BirthData, Chart, compute_chart


# Default coordinates — New Delhi (used when the user doesn't specify location).
_DEFAULT_LAT = 28.6139
_DEFAULT_LON = 77.2090
_DEFAULT_PLACE = "Default (New Delhi)"
_DEFAULT_TZ = 5.5  # IST


def chart_for_moment(
    when: datetime | None = None,
    *,
    lat: float = _DEFAULT_LAT,
    lon: float = _DEFAULT_LON,
    place: str = _DEFAULT_PLACE,
    tz_offset: float = _DEFAULT_TZ,
) -> Chart:
    """Compute a sidereal chart for a specific moment in time.

    Parameters
    ----------
    when
        The local datetime to cast the chart for.  Defaults to ``now``.
    lat, lon
        Geographic coordinates.  Defaults to New Delhi.
    place
        Human-readable label.
    tz_offset
        Hours east of UTC (e.g. 5.5 for IST).
    """
    if when is None:
        when = datetime.now()

    birth = BirthData(
        year=when.year,
        month=when.month,
        day=when.day,
        hour=when.hour,
        minute=when.minute,
        second=when.second,
        tz_offset_hours=tz_offset,
        lat=lat,
        lon=lon,
        place=place,
    )
    return compute_chart(birth)


def transit_chart(
    *,
    lat: float = _DEFAULT_LAT,
    lon: float = _DEFAULT_LON,
    tz_offset: float = _DEFAULT_TZ,
) -> Chart:
    """Current-moment planetary positions (transit chart, right now)."""
    return chart_for_moment(lat=lat, lon=lon, tz_offset=tz_offset)
