from __future__ import annotations

from typing import Any

from latka_jazn.tools.chat_export_reader import build_conversation_graph


def test_conversation_graph_handles_structural_depth_beyond_python_recursion_limit() -> None:
    depth = 2048
    mapping: dict[str, Any] = {}
    previous: str | None = None
    for index in range(depth):
        node_id = f"node-{index}"
        mapping[node_id] = {
            "parent": previous,
            "children": [],
            "message": None,
        }
        if previous is not None:
            mapping[previous]["children"].append(node_id)
        previous = node_id

    graph = build_conversation_graph(
        {
            "id": "deep-conversation",
            "current_node": previous,
            "mapping": mapping,
        }
    )

    assert graph.node_count == depth
    assert len(graph.current_path) == depth
    assert graph.current_path[0] == "node-0"
    assert graph.current_path[-1] == f"node-{depth - 1}"
    assert graph.nodes[0].node_id == "node-0"
    assert graph.nodes[-1].node_id == f"node-{depth - 1}"


def test_conversation_graph_preserves_depth_first_child_order() -> None:
    conversation: dict[str, Any] = {
        "id": "branched-conversation",
        "current_node": "b-1",
        "mapping": {
            "root": {"parent": None, "children": ["a", "b"], "message": None},
            "a": {"parent": "root", "children": ["a-1", "a-2"], "message": None},
            "a-1": {"parent": "a", "children": [], "message": None},
            "a-2": {"parent": "a", "children": [], "message": None},
            "b": {"parent": "root", "children": ["b-1"], "message": None},
            "b-1": {"parent": "b", "children": [], "message": None},
        },
    }

    graph = build_conversation_graph(conversation)

    assert tuple(node.node_id for node in graph.nodes) == (
        "root",
        "a",
        "a-1",
        "a-2",
        "b",
        "b-1",
    )
