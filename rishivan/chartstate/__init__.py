"""The chart, diagnosed — blueprint §6.

    Chart  ->  ChartState  ->  every Rishi reads the same one

`koonji/facts.py` turns a chart into flat interned atoms for retrieval. This
turns the same chart into a structured, navigable diagnosis for reasoning:
planet-level and house-level, with the reasons attached.

    types.py       the frozen value types
    dispositor.py  dispositor and nakshatra-lord chains, cycle-safe
    functional.py  functional benefic/malefic under a named lagna framework
    strength.py    the strength interface — estimated until validated
    build.py       assembly, and the digest that catches calculation drift

Pure and deterministic throughout. The same chart must produce the same
diagnosis, or a trace cannot be replayed and the digest means nothing.
"""
