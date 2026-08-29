from __future__ import annotations

from pathlib import Path
import json

import pytest


def _conversation(text: str) -> dict:
    return {
        "id": "conversation-v4",
        "title": "Entity &quot;control&quot;",
        "current_node": "assistant",
        "mapping": {
            "user": {
                "id": "user",
                "parent": None,
                "children": ["assistant"],
                "message": {
                    "id": "message-user",
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": [text]},
                    "metadata": {"nested": ["A &amp; B", {"quote": "&quot;hej&quot;"}]},
                    "recipient": "all",
                    "channel": None,
                },
            },
            "assistant": {
                "id": "assistant",
                "parent": "user",
                "children": [],
                "message": {
                    "id": "message-assistant",
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["Odpowiedź"]},
                    "metadata": {},
                    "recipient": "all",
                    "channel": None,
                },
            },
        },
    }


def test_chatgpt_export_bundle_classifies_every_member_semantically(tmp_path: Path) -> None:
    from latka_jazn.tools.memory_rebuild_app.source_bundle import (
        ChatGPTExportBundle,
        SourceRole,
    )

    (tmp_path / "conversations.json").write_text("[]", encoding="utf-8")
    (tmp_path / "conversations-1.json").write_text("[]", encoding="utf-8")
    (tmp_path / "chat.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "message_feedback.json").write_text("[]", encoding="utf-8")
    (tmp_path / "shared_conversations.json").write_text("[]", encoding="utf-8")
    (tmp_path / "user.json").write_text("{}", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "asset.txt").write_text("payload", encoding="utf-8")
    (tmp_path / "future-sidecar.json").write_text("{}", encoding="utf-8")

    bundle = ChatGPTExportBundle.discover(tmp_path)
    by_name = {item.relative_path: item.role for item in bundle.members}

    assert by_name["conversations.json"] is SourceRole.CANONICAL_CHAT_GRAPH
    assert by_name["conversations-1.json"] is SourceRole.CANONICAL_CHAT_GRAPH
    assert by_name["chat.html"] is SourceRole.LOSSLESS_CONTROL_GRAPH
    assert by_name["message_feedback.json"] is SourceRole.SUPPLEMENTAL_METADATA
    assert by_name["shared_conversations.json"] is SourceRole.SHARED_LINK_METADATA
    assert by_name["user.json"] is SourceRole.PRIVATE_ACCOUNT_METADATA
    assert by_name["assets/asset.txt"] is SourceRole.SOURCE_ATTACHMENT
    assert by_name["future-sidecar.json"] is SourceRole.UNKNOWN_SIDECAR
    assert bundle.source_sha256
    assert bundle.canonical_chat_members == (
        "conversations.json",
        "conversations-1.json",
    )


def test_html_entities_are_decoded_only_in_semantic_values_after_json_parse() -> None:
    from latka_jazn.tools.memory_rebuild_app.html_semantics import (
        HtmlEmbeddedJsonParser,
        HtmlParseMode,
    )

    raw_conversation = _conversation("powiedział &quot;hej&quot;")
    html = "<script>var jsonData = " + json.dumps([raw_conversation], ensure_ascii=False) + ";</script>"

    result = HtmlEmbeddedJsonParser().parse_text(html)

    assert result.mode is HtmlParseMode.EMBEDDED_JSON_LOSSLESS
    assert result.raw_payload[0]["mapping"]["user"]["message"]["content"]["parts"][0] == (
        "powiedział &quot;hej&quot;"
    )
    semantic_message = result.semantic_payload[0]["mapping"]["user"]["message"]
    assert semantic_message["content"]["parts"][0] == 'powiedział "hej"'
    assert semantic_message["metadata"]["nested"] == ["A & B", {"quote": '"hej"'}]
    assert result.raw_html == html


def test_json_and_embedded_html_are_semantically_equal_after_entity_normalization(
    tmp_path: Path,
) -> None:
    from latka_jazn.tools.memory_rebuild_app.chat_sources import compare_chat_sources

    canonical = _conversation('powiedział "hej"')
    encoded = _conversation("powiedział &quot;hej&quot;")
    json_path = tmp_path / "conversations.json"
    html_path = tmp_path / "chat.html"
    json_path.write_text(json.dumps([canonical], ensure_ascii=False), encoding="utf-8")
    html_path.write_text(
        "<script>var jsonData = " + json.dumps([encoded], ensure_ascii=False) + ";</script>",
        encoding="utf-8",
    )

    comparison = compare_chat_sources(json_path, html_path)

    assert comparison["ok"] is True
    assert comparison["control_mode"] == "embedded_json_lossless"
    assert comparison["semantic_mismatches"] == []


def test_rendered_html_is_lossy_and_invalid_html_is_explicit() -> None:
    from latka_jazn.tools.memory_rebuild_app.html_semantics import (
        HtmlEmbeddedJsonParser,
        HtmlParseMode,
    )

    parser = HtmlEmbeddedJsonParser()
    rendered = parser.parse_text(
        '<div class="conversation"><h4>Tytuł</h4><pre class="message">Treść</pre></div>'
    )
    invalid = parser.parse_text("<html><body>bez danych rozmowy</body></html>")

    assert rendered.mode is HtmlParseMode.RENDERED_HTML_LOSSY
    assert rendered.semantic_payload
    assert invalid.mode is HtmlParseMode.INVALID_HTML
    assert invalid.semantic_payload == []


def test_memory_rebuild_package_import_does_not_apply_versioned_monkey_patches() -> None:
    import latka_jazn.tools.memory_rebuild_app as app

    assert not hasattr(app, "_apply_v16311_hardening")
    assert not hasattr(app, "_apply_v16312_ci_hotfix")
    assert not hasattr(app, "_apply_v16325_hardening")


@pytest.mark.parametrize("module_name", [
    "v16311_hardening",
    "v16312_ci_hotfix",
    "v16325_hardening",
])
def test_versioned_hardening_modules_are_not_required_by_active_import_path(module_name: str) -> None:
    init_source = Path("latka_jazn/tools/memory_rebuild_app/__init__.py").read_text(encoding="utf-8")
    assert module_name not in init_source
