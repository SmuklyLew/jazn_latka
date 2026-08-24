from __future__ import annotations

from typing import Any

from latka_jazn.tools.chat_export_reader import build_conversation_graph


def test_conversation_graph_rejects_non_object_nested_message_shapes() -> None:
    conversation: dict[str, Any] = {
        "id": "conversation-1",
        "current_node": "child",
        "mapping": {
            "root": {
                "parent": None,
                "children": ["child"],
                "message": {
                    "id": "message-1",
                    "author": ["invalid", "shape"],
                    "content": ["invalid", "shape"],
                },
            },
            "child": ["invalid", "node"],
        },
    }

    graph = build_conversation_graph(conversation)

    assert graph.node_count == 2
    assert graph.message_count == 1
    assert graph.current_path == ("child",)
    assert graph.nodes[0].role is None
    assert graph.nodes[0].content_type == "unknown"
    assert graph.nodes[1].message_id is None


def test_conversation_graph_handles_deep_and_cyclic_mappings_iteratively() -> None:
    depth = 2_000
    mapping: dict[str, Any] = {}
    for ordinal in range(depth):
        node_id = f"node-{ordinal}"
        parent = f"node-{ordinal - 1}" if ordinal else None
        children = [f"node-{ordinal + 1}"] if ordinal + 1 < depth else ["node-1000"]
        mapping[node_id] = {
            "parent": parent,
            "children": children,
            "message": {
                "id": f"message-{ordinal}",
                "author": {"role": "user"},
                "content": {"content_type": "text", "parts": [f"text-{ordinal}"]},
            },
        }

    graph = build_conversation_graph({
        "id": "deep-conversation",
        "current_node": f"node-{depth - 1}",
        "mapping": mapping,
    })

    assert graph.node_count == depth
    assert graph.message_count == depth
    assert graph.nodes[0].node_id == "node-0"
    assert graph.nodes[-1].node_id == f"node-{depth - 1}"
