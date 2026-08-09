from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from latka_jazn.nlp.lexical_intelligence import LexicalCache, LexicalIntelligenceEngine
from latka_jazn.nlp.providers.plwordnet_optional_provider import PlWordNetOptionalProvider


def _build_plwordnet_fixture(root: Path) -> None:
    resource = root / "resources" / "plwordnet"
    resource.mkdir(parents=True)
    (resource / "resource.json").write_text(
        json.dumps({"version": "fixture", "license_note": "fixture only"}), encoding="utf-8"
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
            ("pamięć", "pamięć", "subst", "zdolność zachowania informacji", json.dumps({"hypernym": ["zdolność"]}), "fixture"),
        )


def test_plwordnet_local_index_is_read_only_and_returns_relations(tmp_path: Path) -> None:
    _build_plwordnet_fixture(tmp_path)
    result = PlWordNetOptionalProvider(tmp_path).lookup("pamięć")
    assert result.status == "ok"
    assert result.lemmas == ["pamięć"]
    assert result.raw["relations"]["hypernym"] == ["zdolność"]
    assert result.raw["read_only"] is True


def test_lexical_engine_keeps_provider_provenance_and_cache(tmp_path: Path) -> None:
    _build_plwordnet_fixture(tmp_path)
    cache_path = tmp_path / "cache" / "lexical.sqlite3"
    engine = LexicalIntelligenceEngine(root=tmp_path, cache_path=cache_path, enable_morfeusz=False)
    first = engine.analyse("pamięć", context="Pamięć rozmów")
    assert any(item.source == "plwordnet_optional" and item.status == "ok" for item in first.evidence)
    second = engine.analyse("pamięć", context="Pamięć rozmów")
    assert second.cache_hit is True
    assert LexicalCache(cache_path).path.is_file()
