from __future__ import annotations

from pathlib import Path
import json
import zipfile

from latka_jazn.tools.memory_rebuild_app.source_inventory import inspect_source


def test_memory_test_plan_bundle_is_reference_not_rebuild_source(tmp_path: Path) -> None:
    archive = tmp_path / "jazn_memory_test_03_full_plan_documents.zip"
    manifest = {
        "schema_version": "jazn_memory_test_03_plan_bundle/v1",
        "file_count": 1,
        "files": [],
    }
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(
            "jazn_memory_test_03_full_plan_documents/00_INDEX/BUNDLE_MANIFEST.json",
            json.dumps(manifest),
        )
        bundle.writestr(
            "jazn_memory_test_03_full_plan_documents/00_INDEX/FULL_PLAN_INDEX.md",
            "# Plan Testu 03\n",
        )

    result = inspect_source(archive, calculate_sha256=False, verify_zip_crc=True)

    assert result.ok is True
    assert result.status == "ready"
    assert result.role == "reference_document"
    assert result.truth_domain == "technical"
    assert result.pipeline == "catalog_only"
    assert result.metadata["zip"]["bundle_schemas"] == [
        "jazn_memory_test_03_plan_bundle/v1"
    ]
    assert result.metadata["zip"]["crc_error_member"] is None
