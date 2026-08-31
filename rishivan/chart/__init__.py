"""Make the Swiss Ephemeris importable on a Linux host that built it from source.

Every `import swisseph` in this codebase lives in this package, so this
`__init__` is the one place that runs before all of them - which is why the
repair below is here rather than in `ephemeris.py`.

**The failure this fixes.** `pyswisseph` publishes no wheel newer than cp311.
On any Python 3.12+ host, pip therefore builds 2.10.3.2 from its sdist, and the
resulting extension needs the C++ runtime - `nm -u` on it lists `_ZSt7nothrow`,
`__cxa_throw` and friends. macOS gets away with this because clang links libc++
into a module by default; on Linux the module is linked with `gcc` and no
`-lstdc++`, so the .so is built and installed successfully and then fails at
import with:

    ImportError: .../swisseph.cpython-314-x86_64-linux-gnu.so:
                 undefined symbol: _ZSt7nothrow

That is an ABI defect in an installed package, not a missing dependency, so no
requirements pin can fix it. What does fix it is loading libstdc++ with
RTLD_GLOBAL FIRST: its symbols then sit in the global scope where the ephemeris
module's dlopen can resolve them.

**The permanent fix is to deploy on Python 3.11**, where a manylinux wheel
exists and nothing is compiled at all - see README's deployment section. This
repair exists because that requires deleting and redeploying a Streamlit Cloud
app (the Python version cannot be changed in place), and an app should not be
down in the meantime.

Deliberately narrow. It runs on Linux only, only after an import has actually
failed, and only when the error names an undefined symbol. A genuinely missing
`pyswisseph` is left alone to raise its own ImportError at the real call site,
because "not installed" and "installed but mislinked" need different answers
and hiding one behind the other is how a deploy problem becomes a mystery.
"""

from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

CXX_RUNTIME = "libstdc++.so.6"
"""The soname, not a path. Debian, Ubuntu and Alpine all put it somewhere
different and all of them answer to this name through the dynamic loader."""

SYMPTOM = "undefined symbol"
"""The substring that distinguishes a mislinked extension from an absent one."""


def _repair_ephemeris_abi() -> None:
    """Import `swisseph`, and if it fails for lack of libstdc++, supply it."""
    if not sys.platform.startswith("linux"):
        return
    try:
        import swisseph  # noqa: F401
    except ImportError as first:
        if SYMPTOM not in str(first):
            # Not installed at all, or broken some other way. Not ours.
            return
        detail = str(first)
    else:
        return

    try:
        ctypes.CDLL(CXX_RUNTIME, mode=ctypes.RTLD_GLOBAL)
    except OSError:
        logger.warning(
            "the ephemeris needs the C++ runtime and %s could not be loaded; "
            "the original error was: %s", CXX_RUNTIME, detail,
        )
        return

    try:
        import swisseph  # noqa: F401
    except ImportError:
        logger.warning(
            "preloading %s did not make the ephemeris importable; the original "
            "error was: %s", CXX_RUNTIME, detail, exc_info=True,
        )
        return

    logger.info(
        "the installed ephemeris was linked without the C++ runtime; "
        "preloaded %s and it imported", CXX_RUNTIME,
    )


_repair_ephemeris_abi()
