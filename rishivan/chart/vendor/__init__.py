"""Vendored copies of the main repo's pure-arithmetic astro engines.

Each file here (varga.py, numbers.py, ashtakavarga.py) is a verbatim copy of
app/astro/... in the main repo, kept only because rishivan_demo deploys as
its own standalone Streamlit Cloud app from its own git repo — the main
repo's app/ directory does not exist in that deployment, so these modules
cannot be imported across the filesystem the way local dev (a single
monorepo checkout) allows.

Each has zero dependencies beyond the stdlib, so vendoring is safe. If the
main repo's version of one of these changes, re-copy it here to stay in
sync — there is no automated sync.
"""
