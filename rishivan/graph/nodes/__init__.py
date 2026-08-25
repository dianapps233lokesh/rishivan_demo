"""One file per node group.

A node takes state and returns only the keys it owns - never the whole state,
because LangGraph merges partial updates and a full-state return makes every
write look like it came from everywhere.
"""
