from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from latka_jazn.nlp.external_dictionary_adapter import ExternalDictionaryAdapter


def _provision_plwordnet(root: Path) -> None:
    resource = root / "resources" / "plwordnet"
    resource.mkdir(parents=True)
    (resource / "resource.json").write_text(
        json.dumps({"license_note": "fixture-only"}), encoding="utf-8"
    )
    with sqlite3.connect(resource / "index.sqlite3") as connection:
        connection.execute(
            """
            CREATE TABLE lexical_entries(
              term TEXT, lemma TEXT, pos TEXT, definition TEXT,
              relations_json TEXT, source_version TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO lexical_entries VALUES(?,?,?,?,?,?)",
            (
                "kot",
                "kot",
                "subst",
                "udomowiony ssak z rodziny kotowatych",
                json.dumps({"hypernym": ["ssak"], "related": ["kocur"]}),
                "fixture-v1",
            ),
        )


def test_external_dictionary_uses_local_plwordnet_offline(tmp_path: Path) -> None:
    _provision_plwordnet(tmp_path)
    adapter = ExternalDictionaryAdapter(tmp_path, allow_network=False)
    try:
        result = adapter.lookup("kot")
    finally:
        adapter.close()
    assert result.found is True
    assert "kot" in result.lemmas
    assert any("ssak" in definition for definition in result.definitions)
    assert any(item.get("relation") == "hypernym" for item in result.semantic_relations)
    assert any(item.get("provider") == "plwordnet_optional" for item in result.provider_statuses)
