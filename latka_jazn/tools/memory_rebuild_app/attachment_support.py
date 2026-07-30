from __future__ import annotations

from typing import Any

from latka_jazn.tools import chat_export_reader as reader_module
from latka_jazn.tools.chat_export_models import AssetReference

_INSTALLED = False
_ORIGINAL_MESSAGE_TEXT_AND_ASSETS = reader_module._message_text_and_assets


def install_attachment_metadata_support() -> None:
    """Include files listed in message.metadata.attachments in archive asset references."""

    global _INSTALLED
    if _INSTALLED:
        return

    def message_text_and_assets(
        message: dict[str, Any],
        assets_map: dict[str, str],
    ) -> tuple[str, tuple[AssetReference, ...], str]:
        text, existing, content_type = _ORIGINAL_MESSAGE_TEXT_AND_ASSETS(message, assets_map)
        assets = {item.asset_pointer: item for item in existing}
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        attachments = metadata.get("attachments") if isinstance(metadata.get("attachments"), list) else []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            pointer = attachment.get("id") or attachment.get("file_id") or attachment.get("asset_pointer")
            if not pointer:
                continue
            pointer_text = str(pointer)
            original_filename = (
                attachment.get("name")
                or attachment.get("filename")
                or attachment.get("file_name")
                or assets_map.get(pointer_text)
            )
            mime_type = attachment.get("mimeType") or attachment.get("mime_type")
            assets[pointer_text] = AssetReference(
                asset_pointer=pointer_text,
                original_filename=str(original_filename) if original_filename else None,
                content_type="attachment",
                mime_type=str(mime_type) if mime_type else None,
            )
        return text, tuple(assets.values()), content_type

    reader_module._message_text_and_assets = message_text_and_assets
    _INSTALLED = True


__all__ = ["install_attachment_metadata_support"]
