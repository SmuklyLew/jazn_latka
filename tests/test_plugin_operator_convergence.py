from __future__ import annotations

from pathlib import Path

from latka_jazn.core.operator_capabilities import operator_capability_report
from latka_jazn.dependencies.runtime import activation_profile_names, release_profile_names, resolve_profile_requirements
from latka_jazn.plugins import PLUGIN_ENTRY_POINT_GROUP, discover_plugins, plugin_readiness_report

ROOT = Path(__file__).resolve().parents[1]


def test_archive_is_optional_for_activation_but_remains_in_release_profile() -> None:
    assert activation_profile_names(ROOT) == ("core",)
    assert release_profile_names(ROOT) == ("core", "archive")
    core = resolve_profile_requirements(ROOT, ["core"])
    archive = resolve_profile_requirements(ROOT, ["archive"])
    assert not any(req.lower().startswith(("py7zr", "pyzipper", "rarfile")) for req in core)
    assert any(req.lower().startswith("py7zr") for req in archive)
    assert any(req.lower().startswith("pyzipper") for req in archive)
    assert any(req.lower().startswith("rarfile") for req in archive)


def test_plugin_registry_uses_pypa_entry_point_group_without_loading_external_code() -> None:
    report = discover_plugins(load_external=False)
    assert report["ok"] is True
    assert report["entry_point_group"] == PLUGIN_ENTRY_POINT_GROUP == "jazn.plugins"
    archive = next(item for item in report["plugins"] if item["plugin_id"] == "archive")
    assert archive["source"] == "builtin"
    assert archive["manifest"]["classification"] == "optional"
    assert archive["manifest"]["network_policy"] == "denied"


def test_missing_enhanced_archive_backends_do_not_block_runtime_core(monkeypatch) -> None:
    import latka_jazn.archive.capabilities as capabilities

    monkeypatch.setattr(capabilities, "_module_available", lambda _name: False)
    report = plugin_readiness_report()
    assert report["blocks_runtime_core"] is False
    archive = next(item for item in report["plugins"] if item["plugin_id"] == "archive")
    assert archive["ready"] is True
    assert archive["state"] == "degraded"
    assert archive["detail"]["baseline_zip_ready"] is True
    assert archive["detail"]["enhanced_ready"] is False


def test_git_and_pip_are_operator_only_capabilities() -> None:
    report = operator_capability_report(ROOT)
    assert report["blocks_runtime_core"] is False
    assert report["git"]["operator_only"] is True
    assert report["git"]["live_daemon_mutation_allowed"] is False
    assert set(report["git"]["forbidden_live_daemon_actions"]) >= {"pull", "checkout", "reset", "merge", "push"}
    assert report["pip"]["operator_only"] is True
    assert report["pip"]["live_daemon_mutation_allowed"] is False
    assert report["pip"]["runtime_network_allowed"] is False
    assert report["pip"]["delegated_to"] == "latka_jazn.tools.dependency_studio"
