"""The Shodashavarga — sixteen divisional charts, all pure arithmetic on a longitude.

VENDORED from the main repo's app/astro/kundli/varga.py — see
rishivan/chart/vendor/__init__.py for why. Keep this in sync manually.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

MOVABLE, FIXED, DUAL = 0, 1, 2

ARIES, TAURUS, GEMINI, CANCER, LEO, VIRGO = 0, 1, 2, 3, 4, 5
LIBRA, SCORPIO, SAGITTARIUS, CAPRICORN, AQUARIUS, PISCES = 6, 7, 8, 9, 10, 11


def _is_odd_sign(sign: int) -> bool:
    """Aries is the 1st sign and therefore odd; index 0 is odd."""
    return sign % 2 == 0


def _mobility(sign: int) -> int:
    return sign % 3


def _element(sign: int) -> int:
    """0 fiery, 1 earthy, 2 airy, 3 watery — Aries is fiery."""
    return sign % 4


def amsha_index(longitude: float, divisor: int) -> int:
    """Index of the amsha within the sign, 0..divisor-1.

    Integer arithmetic on the float's exact ratio. Dividing by a precomputed
    30/n arc width is wrong at boundaries where that width rounds up.
    """
    numerator, denominator = (longitude % 30.0).as_integer_ratio()
    return min(numerator * divisor // (denominator * 30), divisor - 1)


def _stepped(divisor: int, start: Callable[[int], int], step: int = 1):
    """Uniform division whose images advance by `step` signs from a computed start."""

    def sign_of(longitude: float) -> int:
        sign = int(longitude // 30.0) % 12
        return (start(sign) + amsha_index(longitude, divisor) * step) % 12

    return sign_of


def _hora(longitude: float) -> int:
    sign = int(longitude // 30.0) % 12
    first_half = amsha_index(longitude, 2) == 0
    if _is_odd_sign(sign):
        return LEO if first_half else CANCER
    return CANCER if first_half else LEO


_TRIMSHAMSHA_ODD = (
    (5.0, ARIES),
    (10.0, AQUARIUS),
    (18.0, SAGITTARIUS),
    (25.0, GEMINI),
    (30.0, LIBRA),
)
_TRIMSHAMSHA_EVEN = (
    (5.0, TAURUS),
    (12.0, VIRGO),
    (20.0, PISCES),
    (25.0, CAPRICORN),
    (30.0, SCORPIO),
)


def _trimshamsha(longitude: float) -> int:
    sign = int(longitude // 30.0) % 12
    degree = longitude % 30.0
    table = _TRIMSHAMSHA_ODD if _is_odd_sign(sign) else _TRIMSHAMSHA_EVEN
    for upper, target in table:
        if degree < upper:
            return target
    return table[-1][1]


def _by_mobility(movable: int, fixed: int, dual: int) -> Callable[[int], int]:
    """Start at an absolute sign chosen by the natal sign's mobility."""
    table = {MOVABLE: movable, FIXED: fixed, DUAL: dual}
    return lambda sign: table[_mobility(sign)]


def _offset_by_mobility(movable: int, fixed: int, dual: int) -> Callable[[int], int]:
    """Start at a sign counted *from the natal sign*, by its mobility.

    Distinct from _by_mobility: navamsa's "movable starts from itself" means
    Cancer's navamsas begin at Cancer, not at Aries. Using an absolute table
    is right only for the first three signs.
    """
    table = {MOVABLE: movable, FIXED: fixed, DUAL: dual}
    return lambda sign: sign + table[_mobility(sign)]


def _by_element(
    fiery: int, earthy: int, airy: int, watery: int
) -> Callable[[int], int]:
    table = {0: fiery, 1: earthy, 2: airy, 3: watery}
    return lambda sign: table[_element(sign)]


def _by_parity(odd: int, even: int) -> Callable[[int], int]:
    return lambda sign: odd if _is_odd_sign(sign) else even


def _offset_by_parity(odd_offset: int, even_offset: int) -> Callable[[int], int]:
    return lambda sign: sign + (odd_offset if _is_odd_sign(sign) else even_offset)


@dataclass(frozen=True, slots=True)
class VargaSpec:
    """One divisional chart: its UI copy, its divisor, and its sign mapping."""

    code: str
    name: str
    subtitle: str
    divisor: int
    sign_of: Callable[[float], int]
    expected_images: int


_SPECS = (
    VargaSpec("D1", "Rashi chart", "Chart of Lagna", 1, _stepped(1, lambda s: s), 12),
    VargaSpec("D2", "Hora chart", "Wealth and resources", 2, _hora, 2),
    VargaSpec(
        "D3",
        "Drekkana chart",
        "Siblings and courage",
        3,
        _stepped(3, lambda s: s, step=4),
        12,
    ),
    VargaSpec(
        "D4",
        "Chaturthamsha chart",
        "Home and fortune",
        4,
        _stepped(4, lambda s: s, step=3),
        12,
    ),
    VargaSpec(
        "D7",
        "Saptamsha chart",
        "Children and progeny",
        7,
        _stepped(7, _offset_by_parity(0, 6)),
        12,
    ),
    VargaSpec(
        "D9",
        "Navamsa chart",
        "Chart of fortune",
        9,
        # movable -> the sign itself, fixed -> the 9th from it, dual -> the 5th
        _stepped(9, _offset_by_mobility(0, 8, 4)),
        12,
    ),
    VargaSpec(
        "D10",
        "Dashamsha chart",
        "Career and status",
        10,
        _stepped(10, _offset_by_parity(0, 8)),
        12,
    ),
    VargaSpec(
        "D12",
        "Dwadashamsha chart",
        "Parents and lineage",
        12,
        _stepped(12, lambda s: s),
        12,
    ),
    VargaSpec(
        "D16",
        "Shodashamsha chart",
        "Vehicles and comforts",
        16,
        _stepped(16, _by_mobility(ARIES, LEO, SAGITTARIUS)),
        12,
    ),
    VargaSpec(
        "D20",
        "Vimshamsha chart",
        "Spiritual practice",
        20,
        _stepped(20, _by_mobility(ARIES, SAGITTARIUS, LEO)),
        12,
    ),
    VargaSpec(
        "D24",
        "Chaturvimshamsha chart",
        "Learning and knowledge",
        24,
        _stepped(24, _by_parity(LEO, CANCER)),
        12,
    ),
    VargaSpec(
        "D27",
        "Bhamsha chart",
        "Strengths and weaknesses",
        27,
        _stepped(27, _by_element(ARIES, CANCER, LIBRA, CAPRICORN)),
        12,
    ),
    VargaSpec(
        "D30", "Trimshamsha chart", "Misfortunes and evils", 30, _trimshamsha, 10
    ),
    VargaSpec(
        "D40",
        "Khavedamsha chart",
        "Maternal legacy",
        40,
        _stepped(40, _by_parity(ARIES, LIBRA)),
        12,
    ),
    VargaSpec(
        "D45",
        "Akshavedamsha chart",
        "Paternal legacy",
        45,
        _stepped(45, _by_mobility(ARIES, LEO, SAGITTARIUS)),
        12,
    ),
    VargaSpec(
        "D60",
        "Shashtiamsha chart",
        "Past-life karma",
        60,
        _stepped(60, lambda s: s),
        12,
    ),
)

VARGA_REGISTRY: dict[str, VargaSpec] = {spec.code: spec for spec in _SPECS}
VARGA_CODES: tuple[str, ...] = tuple(VARGA_REGISTRY)


def varga_sign(code: str, longitude: float) -> int:
    """0-based sign this longitude occupies in the given divisional chart."""
    return VARGA_REGISTRY[code].sign_of(longitude)


def varga_longitude(code: str, longitude: float) -> float:
    """Absolute longitude positioned inside the varga sign, for display and nakshatra.

    Convention: the position within the amsha, scaled by the divisor. Pinned here
    because implementations differ; verify against Jagannatha Hora, never the mockups.
    """
    spec = VARGA_REGISTRY[code]
    sign = spec.sign_of(longitude)
    numerator, denominator = (longitude % 30.0).as_integer_ratio()
    # position within the amsha, in units of the amsha width, scaled to a sign
    scaled = numerator * spec.divisor / denominator - 30.0 * amsha_index(
        longitude, spec.divisor
    )
    within = min(max(scaled, 0.0), 30.0 - 1e-12)
    return sign * 30.0 + within
