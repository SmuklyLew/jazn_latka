from __future__ import annotations

import ast
from pathlib import Path

import CHATGPT_BOOTSTRAP as bootstrap
from latka_jazn.memory.availability import build_memory_availability_status, core_state_root, runtime_memory_storage_root
from latka_jazn.memory.memory_root import default_memory_root, memory_root_has_payload, previous_host_memory_root, resolve_memory_root, resolve_memory_root_diagnostic
from latka_jazn.memory.runtime_memory_install import resolve_memory_tier_database_path
from latka_jazn.memory.unified_memory_runtime import probe_unified_memory_database
from latka_jazn.tools.memory_rebuild_app.unified_schema import CANONICAL_DATABASE_NAME

ROOT = Path(__file__).resolve().parents[1]


def test_operator_zip_requires_main_and_chatgpt_runbook() -> None:
    assert {'run.py', 'main.py', 'AGENTS.md', 'AGENTS.chatgpt.md'}.issubset(bootstrap._REQUIRED_ROOT_FILES)
    assert {'SOURCE_PROVENANCE.json', 'PACKAGE_INTEGRITY_MANIFEST.json'}.issubset(bootstrap._REQUIRED_ROOT_FILES)


def test_nonactivation_dependency_probe_cannot_autoinstall() -> None:
    tree = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_bootstrap_entrypoint_environment')
    calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'prepare_entrypoint_environment']
    assert len(calls) == 1
    auto_install = next(k.value for k in calls[0].keywords if k.arg == 'auto_install')
    assert isinstance(auto_install, ast.Compare)
    assert isinstance(auto_install.left, ast.Name) and auto_install.left.id == 'command'
    assert len(auto_install.ops) == 1 and isinstance(auto_install.ops[0], ast.In)
    assert isinstance(auto_install.comparators[0], ast.Name)
    assert auto_install.comparators[0].id == '_ACTIVATION_COMMANDS'


def _root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / 'active-system'
    root.mkdir()
    monkeypatch.delenv('JAZN_MEMORY_ROOT', raising=False)
    monkeypatch.delenv('JAZN_MEMORY_TIER_DB', raising=False)
    monkeypatch.delenv('JAZN_MEMORY_MODE', raising=False)
    monkeypatch.setenv('JAZN_RUNTIME_WORKSPACE_DIR', str(tmp_path / 'workspace'))
    return root


def test_system_only_runtime_storage_is_not_private_memory(tmp_path: Path, monkeypatch) -> None:
    root = _root(tmp_path, monkeypatch)
    diagnostic = resolve_memory_root_diagnostic(root)
    assert diagnostic['selected'] == str(default_memory_root(root))
    assert diagnostic['selected_has_payload'] is False
    optional = build_memory_availability_status(root, mode='optional')
    assert optional.core_runtime_allowed is True
    assert optional.persistent_memory_enabled is False
    assert runtime_memory_storage_root(root) == core_state_root(root) / 'memory_runtime'
    assert not (root / 'memory').exists()
    assert build_memory_availability_status(root, mode='required').core_runtime_allowed is False
    assert build_memory_availability_status(root, mode='off').persistent_memory_enabled is False


def test_previous_workspace_payload_is_read_compatible_not_migrated(tmp_path: Path, monkeypatch) -> None:
    root = _root(tmp_path, monkeypatch)
    previous = previous_host_memory_root(root)
    (previous / 'raw').mkdir(parents=True)
    (previous / 'raw' / 'chat.html').write_text('fixture', encoding='utf-8')
    assert resolve_memory_root(root) == previous
    assert not (root / 'memory').exists()
    assert resolve_memory_root_diagnostic(root)['selection_source'] == 'previous_host_memory_compatibility'


def test_unverified_unified_db_marker_cannot_assert_autobiography(tmp_path: Path, monkeypatch) -> None:
    root = _root(tmp_path, monkeypatch)
    db = root / 'memory' / 'sqlite' / CANONICAL_DATABASE_NAME
    db.parent.mkdir(parents=True)
    db.write_bytes(b'not a sqlite file')
    assert memory_root_has_payload(root / 'memory')
    assert build_memory_availability_status(root).persistent_memory_enabled is True
    probe = probe_unified_memory_database(db)
    assert probe['memory_search_ready'] is False
    assert probe.get('full_autobiographical_recall_ready') is not True
    assert resolve_memory_tier_database_path(root).name == 'runtime_memory.sqlite3'


def test_documented_memory_roles_and_ci_path_filters() -> None:
    guide = (ROOT / 'docs/runtime/CHATGPT_MAIN_FIRST_MEMORY_OPERATIONS.md').read_text(encoding='utf-8')
    for name in ('memory_jazn.sqlite3', 'runtime_write_v2/runtime_memory.sqlite3', 'core_state',
                 'JAZN_MEMORY_ROOT', 'JAZN_MEMORY_MODE', 'full_autobiographical_recall_ready', 'connect_runtime_readonly'):
        assert name in guide
    workflow = (ROOT / '.github/workflows/persistent-runtime-e2e.yml').read_text(encoding='utf-8')
    assert workflow.count('latka_jazn/core/chatgpt_host_pre_response_gate/**') == 2
    assert 'latka_jazn/core/chatgpt_host_pre_response_gate.py' not in workflow
    assert workflow.count('tests/test_chatgpt_main_first_memory_contract.py') == 2
    config = (ROOT / 'pyrightconfig.json').read_text(encoding='utf-8')
    assert 'jazn_runtime_bootstrap.py' in config
