"""Timing as a first-class subsystem — blueprint §8.

    activation.py  what a period lord actually touches
    windows.py     promise -> activation -> trigger -> peak -> fading
    query.py       periods and windows at an arbitrary moment

Vimshottari only, made extremely reliable, exactly as the blueprint orders. The
exact period boundaries come from `chart/dasha.py`, which already computes five
levels; nothing here re-derives them.

A second dasha system, when it arrives, is a second *opinion* under its own key
in `TimingReport.by_system`. Averaging two systems produces a number no tradition
endorses and no reviewer can check.
"""
