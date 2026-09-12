from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from latka_jazn.config import JaznConfig
from latka_jazn.core.readiness import evaluate_voice_live_readiness
from latka_jazn.nlp import dictionary_readiness
from latka_jazn.nlp.dictionary_readiness import build_dictionary_readiness_status
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

    readiness = build_dictionary_readiness_status(
        JaznConfig(root=tmp_path, dictionary_allow_network=False)
    )
    providers = {item["provider"]: item for item in readiness["providers"]}
    assert providers["plwordnet_optional"]["license_verified"] is True
    assert providers["plwordnet_optional"]["last_probe_ok"] is True
    assert providers["plwordnet_optional"]["lookup_ready"] is True


def test_dictionary_status_uses_read_only_capability_probes(tmp_path: Path) -> None:
    status = build_dictionary_readiness_status(
        JaznConfig(root=tmp_path, dictionary_allow_network=False)
    )
    providers = {item["provider"]: item for item in status["providers"]}

    assert status["probe_mode"] == "read_only_no_network"
    assert status["dictionary_lookup_ready"] is True
    assert "local_jazn_mini_lexicon" in status["ready_lookup_providers"]
    assert providers["wiktionary_mediawiki_api"]["reachable"] is None
    assert providers["wiktionary_mediawiki_api"]["last_probe_ok"] is None
    assert providers["wiktionary_mediawiki_api"]["lookup_ready"] is False
    assert providers["sjp_reference"]["reference_ready"] is True
    assert providers["sjp_reference"]["lookup_ready"] is False
    assert "mediawiki_wiktionary_provider" not in status
    assert not (tmp_path / "workspace_runtime").exists()


def test_provider_module_presence_cannot_make_dictionary_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class MissingMorfeusz:
        name = "morfeusz_optional"
        available = False

    monkeypatch.setattr(dictionary_readiness, "MINI_LEXICON", {})
    monkeypatch.setattr(
        dictionary_readiness,
        "OptionalMorfeuszProvider",
        MissingMorfeusz,
    )
    status = build_dictionary_readiness_status(
        JaznConfig(root=tmp_path, dictionary_allow_network=False)
    )

    assert status["dictionary_lookup_ready"] is False
    assert status["ready_lookup_providers"] == []
    assert status["external_failure_blocks_voice"] is False


def test_dictionary_failure_is_fail_soft_for_live_voice(tmp_path: Path) -> None:
    daemon = {
        "active_state": "active_trusted",
        "pid_alive": True,
        "process_identity_confirmed": True,
        "endpoint_probe_performed": True,
        "endpoint_reachable": True,
        "endpoint_pid_matches": True,
        "endpoint_root_matches": True,
        "endpoint_identity_matches": True,
        "heartbeat_fresh": True,
        "resolved_active_root": str(tmp_path.resolve()),
        "package_integrity_verified": True,
        "source_provenance_verified": True,
    }

    assert evaluate_voice_live_readiness(
        daemon=daemon,
        expected_active_root=tmp_path,
    ).ready is True
