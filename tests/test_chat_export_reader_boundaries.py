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
