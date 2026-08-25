"""The council pipeline as a graph.

`council/orchestrator.py` grew to 564 lines with every branch inline, which made
the branches untestable: you could not ask "what happens to a muhurta question
with no birth data" without running the whole pipeline, model calls and all.

Here a node does work and an edge chooses. Every `route_*` function is pure
(`State -> str`) and gets a table-driven test, which is the entire point.
"""
