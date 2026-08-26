"""The wiring. Asserts topology, not behaviour - behaviour is the node tests."""

from rishivan.graph.build import EDGE_MAPS, NODE_NAMES, STATIC_EDGES, build_graph


def test_the_graph_compiles():
    assert build_graph(store=None, client=None) is not None


def test_every_router_destination_is_a_real_node():
    """A typo in a conditional-edge mapping is a runtime KeyError on a branch
    nobody exercises until a user takes it."""
    for source, mapping in EDGE_MAPS.items():
        for destination in mapping.values():
            assert destination in NODE_NAMES, f"{source} -> {destination}"


def test_every_static_edge_points_somewhere_real():
    for source, destination in STATIC_EDGES.items():
        assert source in NODE_NAMES, source
        assert destination in NODE_NAMES or destination == "__end__", destination


def test_every_node_is_reachable():
    """An unreachable node is dead code that still has to be maintained."""
    reachable = {"intake"}
    for mapping in EDGE_MAPS.values():
        reachable.update(mapping.values())
    reachable.update(STATIC_EDGES.values())
    unreachable = set(NODE_NAMES) - reachable
    assert not unreachable, f"unreachable: {sorted(unreachable)}"


def test_every_node_leads_somewhere():
    """A node with no outgoing edge hangs the graph."""
    has_exit = set(STATIC_EDGES) | set(EDGE_MAPS)
    dead_ends = set(NODE_NAMES) - has_exit
    assert not dead_ends, f"no outgoing edge: {sorted(dead_ends)}"


def test_the_graph_renders_to_mermaid():
    """Free documentation, and it fails loudly if the topology is malformed."""
    diagram = build_graph(store=None, client=None).get_graph().draw_mermaid()
    assert "intake" in diagram


def test_a_checkpointer_can_be_attached():
    from rishivan.graph.build import checkpointer_for

    graph = build_graph(store=None, client=None, checkpointer=checkpointer_for("demo"))
    assert graph is not None


# ==========================================================================
# Phase 4: the dependency chain, straightened
# ==========================================================================


def test_varga_selection_runs_after_the_hierarchy_that_names_its_domain():
    assert STATIC_EDGES["chart_state"] == "hierarchy"
    assert STATIC_EDGES["hierarchy"] == "varga_select"


def test_the_reading_is_computed_before_the_timing_that_needs_its_promise():
    """`dasha_windows` reads `reading.promises(domain)`. With the reading
    downstream of it, that call could only ever see None - which is how every
    window came back promise-less."""
    assert STATIC_EDGES["varga_select"] == "koonji_read"
    assert STATIC_EDGES["koonji_read"] == "dasha_windows"


def test_the_reading_is_computed_after_the_vargas_it_compiles_facts_from():
    """Selecting D9 for a marriage question and then compiling the fact set
    without it buys nothing."""
    assert STATIC_EDGES["varga_select"] == "koonji_read"


def test_the_new_nodes_are_declared():
    for node in ("hierarchy", "koonji_read"):
        assert node in NODE_NAMES
