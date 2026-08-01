from __future__ import annotations

from pathlib import Path

import pytest

import main as main_module

from latka_jazn.adapters.codex_session_bridge import build_parser as build_codex_bridge_parser
from latka_jazn.config import JaznConfig
from latka_jazn.core.continuity_badge import ContinuityBadgePolicy
from latka_jazn.core.module_responsibility_map import ModuleResponsibilityMap
from latka_jazn.core.project_index import ProjectStartupIndexer
from latka_jazn.core.runtime_daemon import daemon_auth_token_path, daemon_log_dir, daemon_pid_path
from latka_jazn.core.runtime_session_state import RuntimeSessionStateStore
from latka_jazn.core.runtime_root import runtime_state_path
from latka_jazn.core.turn_checkpoint_writer import TurnCheckpointWriter
from latka_jazn.core.turn_trace_reader import TurnTraceReader
from latka_jazn.model_adapters.openai_state_tracker import OpenAIStateTracker
from latka_jazn.nlp.network_dictionary_cache import NetworkDictionaryCache
from latka_jazn.nlp_reasoning.adapters.polimorf_adapter import PolimorfDictionaryAdapter
from latka_jazn.nlp_reasoning.lexical_resource_cache import LexicalResourceCache
from latka_jazn.nlp_reasoning.lexical_resource_registry import LexicalResourceRegistry
from latka_jazn.tools.runtime_contract_version_normalizer import normalize_runtime_contract_versions


def test_absolute_runtime_workspace_override_routes_startup_state_outside_code_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    code_root = tmp_path / "read-only-package"
    code_root.mkdir()
    state_root = tmp_path / "writable-state"
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(state_root))

    cfg = JaznConfig(root=code_root)

    assert cfg.runtime_workspace_dir == state_root.resolve()
    assert cfg.lexical_resource_cache_path == state_root.resolve() / "dictionary_cache.sqlite3"
    assert cfg.active_runtime_marker_path == state_root.resolve() / "JAZN_ACTIVE_RUNTIME.json"
    assert main_module._chatgpt_daemon_marker_path(cfg) == cfg.active_runtime_marker_path
    assert daemon_pid_path(cfg.root) == state_root.resolve() / "jazn_daemon.pid"
    assert daemon_auth_token_path(cfg.root) == state_root.resolve() / "daemon" / "capability.token"
    assert daemon_log_dir(cfg.root) == state_root.resolve() / "daemon"
    assert RuntimeSessionStateStore(cfg.root).latest_path == state_root.resolve() / "runtime_session_state.json"
    assert TurnCheckpointWriter(cfg.root).base == state_root.resolve() / "turn_checkpoints"
    assert TurnTraceReader(cfg.root).base == state_root.resolve() / "turn_checkpoints"
    assert ContinuityBadgePolicy(cfg.root).state_path == state_root.resolve() / "continuity_badge_state.json"
    assert ModuleResponsibilityMap(cfg.root).output_path == state_root.resolve() / "module_responsibility_map_current_line.json"
    assert ProjectStartupIndexer(cfg.root).output_path == state_root.resolve() / "project_startup_index_current_line.json"
    assert OpenAIStateTracker(cfg.root).path == state_root.resolve() / "openai_response_state.json"
    lexical_cache = LexicalResourceCache(cfg.root)
    assert lexical_cache.path == state_root.resolve() / "dictionary_cache.sqlite3"
    network_cache = NetworkDictionaryCache(cfg.root)
    assert network_cache.path == state_root.resolve() / "dictionary_cache.sqlite3"
    network_cache.close()

    polimorf_path = state_root / "polish_reasoning" / "polimorf.tsv"
    polimorf_path.parent.mkdir(parents=True)
    polimorf_path.write_text("kot\tkot\tsubst\n", encoding="utf-8")
    assert PolimorfDictionaryAdapter(cfg.root).path == polimorf_path
    assert LexicalResourceRegistry(cfg.root)._polimorf_path(None) == polimorf_path
    bridge_args = build_codex_bridge_parser().parse_args(["status"])
    assert Path(bridge_args.root) == state_root.resolve() / "codex_session_bridge"

    with pytest.raises(ValueError, match="escapes its configured root"):
        runtime_state_path(cfg.root, "workspace_runtime/../../outside.json")


def test_contract_normalizer_reads_and_writes_external_runtime_marker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "runtime"
    version_file = root / "latka_jazn" / "version.py"
    version_file.parent.mkdir(parents=True)
    version_file.write_text(
        "PACKAGE_VERSION = 'v1'\n"
        "PACKAGE_RELEASE_NAME = ''\n"
        "PACKAGE_VERSION_FULL = PACKAGE_VERSION\n",
        encoding="utf-8",
    )
    state_root = tmp_path / "external-state"
    state_root.mkdir()
    marker = state_root / "JAZN_ACTIVE_RUNTIME.json"
    marker.write_text(
        '{"schema_version":"jazn_active_runtime_marker/v0","version":"v0"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("JAZN_RUNTIME_WORKSPACE_DIR", str(state_root))

    report = normalize_runtime_contract_versions(root, apply=True)

    normalized = marker.read_text(encoding="utf-8")
    assert '"version": "v1"' in normalized
    assert report["results"][1]["exists"] is True
    assert not (root / "workspace_runtime" / "JAZN_ACTIVE_RUNTIME.json").exists()
