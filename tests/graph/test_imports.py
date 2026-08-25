"""The graph package exists and langgraph is a real, pinned dependency.

Trivial, and worth a test: a missing pin is the failure that only shows up on
Streamlit Cloud, three days later, in someone else's session.
"""


def test_langgraph_is_installed():
    import langgraph.graph  # noqa: F401


def test_langgraph_is_pinned_not_floated():
    from pathlib import Path

    line = next(
        l for l in Path("requirements.txt").read_text().splitlines()
        if l.strip().startswith("langgraph")
    )
    assert "==" in line, f"pin it: {line!r}"


def test_graph_package_imports():
    import rishivan.graph  # noqa: F401
