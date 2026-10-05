from __future__ import annotations

import json
from pathlib import Path

import pytest

from latka_jazn.packaging.memory_package_manifest import verify_memory_package_manifest
from tools.jazn_pack_generator_app import staging
from tools.jazn_pack_generator_app.errors import PackIntegrityError
from tools.jazn_pack_generator_app.models import ContentMode, PackPlan, PackRequest, SourceEntry


def _memory_plan(tmp_path: Path) -> PackPlan:
    source = tmp_path / "source"
    (source / "memory" / "raw").mkdir(parents=True)
    first = source / "memory" / "raw" / "one.json"
    second = source / "memory" / "notes.txt"
    second.parent.mkdir(parents=True, exist_ok=True)
    first.write_text('{"id": 1}\n', encoding="utf-8")
    second.write_text("memory note\n", encoding="utf-8")
    entries = (
        SourceEntry(first, "memory/raw/one.json", first.stat().st_size, False),
        SourceEntry(second, "memory/notes.txt", second.stat().st_size, False),
    )
    return PackPlan(
        request=PackRequest(
            source_root=source,
            output_root=tmp_path / "out",
            content=ContentMode.MEMORY,
        ),
        package_version="16.3.25.5.107-test",
        package_basename="memory-test.zip",
        entries=entries,
        excluded=(),
        source_total_size_bytes=sum(item.size_bytes for item in entries),
    )


def test_native_v3_generator_staging_is_exact_set_verified(tmp_path: Path) -> None:
    destination = tmp_path / "staging"
    result = staging.materialize_source_staging(_memory_plan(tmp_path), destination)

    report = verify_memory_package_manifest(destination)
    assert report["ok"] is True, report

    manifest = json.loads(
        (destination / "memory" / "MEMORY_PACKAGE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    declared = {item["path"] for item in manifest["files"]}
    actual = {
        path.relative_to(destination).as_posix()
        for path in (destination / "memory").rglob("*")
        if path.is_file()
        and path.name != "MEMORY_PACKAGE_MANIFEST.json"
    }
    assert declared == actual
    assert manifest["file_count"] == len(actual)


def test_generator_refuses_to_continue_when_exact_set_verification_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        staging,
        "verify_memory_package_manifest",
        lambda _root: {
            "ok": False,
            "errors": [
                {"code": "memory_package_unlisted_file", "path": "memory/unlisted.bin"}
            ],
        },
    )

    with pytest.raises(PackIntegrityError, match="memory_package_unlisted_file"):
        staging.materialize_source_staging(_memory_plan(tmp_path), tmp_path / "staging")
