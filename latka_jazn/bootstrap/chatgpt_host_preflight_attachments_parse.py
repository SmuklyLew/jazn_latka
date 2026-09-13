from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from latka_jazn.bootstrap.chatgpt_host_preflight_parse import optional_int
from latka_jazn.packaging.attachment_materialization import (
    AttachmentMaterializationReport,
    probe_attachment_materialization,
)


def attachment_reports_from_payload(
    payload: Mapping[str, Any],
) -> tuple[AttachmentMaterializationReport, ...]:
    raw = payload.get("attachments", [])
    if not isinstance(raw, list):
        raise ValueError("attachments_must_be_array")
    reports: list[AttachmentMaterializationReport] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise ValueError("attachment_spec_must_be_object")
        path_value = str(item.get("path") or "").strip()
        if not path_value:
            raise ValueError("attachment_path_is_required")
        expected_size = optional_int(item, "expected_size_bytes", None)
        expected_sha = (
            str(item["expected_sha256"]).strip()
            if item.get("expected_sha256") is not None
            else None
        )
        reports.append(
            probe_attachment_materialization(
                Path(path_value),
                expected_size_bytes=expected_size,
                expected_sha256=expected_sha,
            )
        )
    return tuple(reports)
