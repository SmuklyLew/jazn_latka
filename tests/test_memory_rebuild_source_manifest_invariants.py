from __future__ import annotations

import json

from latka_jazn.tools.memory_rebuild_app.adapters.music_analysis import _analysis_rows
from latka_jazn.tools.memory_rebuild_app.run_manifest import RunManifest


def test_music_analysis_accepts_entries_collection(tmp_path) -> None:
    source = tmp_path / "analizy_utworow.json"
    source.write_text(
        json.dumps(
            {
                "entries": [
                    {"numer": 2, "analiza": "druga"},
                    {"numer": 1, "analiza": "pierwsza"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = list(_analysis_rows(source))
    assert [row["numer"] for row in rows] == [2, 1]
    assert [row["analiza"] for row in rows] == ["druga", "pierwsza"]


def test_run_manifest_sanitized_inventory_order_survives_draft_roundtrip(tmp_path) -> None:
    identity = {
        "run_id": "v1192-order",
        "tool_version": "119.2.0",
        "system_version": "119.2.0",
        "base_commit": "a" * 40,
    }
    manifest = RunManifest.begin(
        run_id=identity["run_id"],
        tool_version=identity["tool_version"],
        system_version=identity["system_version"],
        base_commit=identity["base_commit"],
    ).with_sources(
        (
            {"path": "z.json", "role": "journal", "sha256": "b" * 64},
            {"path": "a.json", "role": "conversation", "sha256": "a" * 64},
        )
    )
    before = manifest.sanitized_dict()
    manifest.write_draft(tmp_path)

    restored = RunManifest.load_draft(
        tmp_path,
        run_id=identity["run_id"],
        tool_version=identity["tool_version"],
        system_version=identity["system_version"],
        base_commit=identity["base_commit"],
    )

    assert restored.sanitized_dict() == before
    assert restored.source_sha256 == manifest.source_sha256
    assert list(before["source_roles"].values()) == ["journal", "conversation"]
    assert list(before["source_sha256"].values()) == ["b" * 64, "a" * 64]
