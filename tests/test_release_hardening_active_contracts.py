from __future__ import annotations

from pathlib import Path
import ast
import inspect
import json

from latka_jazn.core import self_knowledge_contract, startup_contract


ROOT = Path(__file__).resolve().parents[1]

ACTIVE_GENERATORS = (
    ROOT / "latka_jazn" / "memory" / "auto_memory_update.py",
    ROOT / "latka_jazn" / "tools" / "dedup_manifest.py",
    ROOT / "latka_jazn" / "integrations" / "github_repository_plan.py",
)


def _legacy_write_calls(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    findings: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        rendered = ast.unparse(node)
        if "VERSION.txt" not in rendered and "MANIFEST_CURRENT.json" not in rendered:
            continue
        function = node.func
        name = function.attr if isinstance(function, ast.Attribute) else function.id if isinstance(function, ast.Name) else ""
        if name in {"write_text", "touch"}:
            findings.append(rendered)
        elif name == "open":
            mode_index = 0 if isinstance(function, ast.Attribute) else 1
            mode = (
                ast.literal_eval(node.args[mode_index])
                if len(node.args) > mode_index and isinstance(node.args[mode_index], ast.Constant)
                else ""
            )
            for keyword in node.keywords:
                if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                    mode = keyword.value.value
            if any(flag in str(mode) for flag in ("w", "a", "x", "+")):
                findings.append(rendered)
    return findings


def test_active_bootstrap_contract_has_only_canonical_release_sources_and_commands() -> None:
    path = ROOT / "latka_jazn" / "resources" / "canon" / "LATKA_SELF_KNOWLEDGE_CONTRACT.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    checklist = payload["post_update_bootstrap"]
    assert checklist == [
        "read latka_jazn/version.py",
        "read PACKAGE_INTEGRITY_MANIFEST.json",
        "read workspace_runtime/JAZN_ACTIVE_RUNTIME.json when present and verify it",
        "run python -X utf8 run.py status --json",
        "run python -X utf8 run.py doctor --json",
        'run python -X utf8 run.py chat-gpt -- "<wiadomość>"',
    ]
    active_text = path.read_text(encoding="utf-8")
    assert "VERSION.txt" not in active_text
    assert "MANIFEST_CURRENT.json" not in active_text
    assert "--chat-gpt-final-only" not in active_text


def test_self_check_uses_canonical_fields_and_legacy_alias_is_diagnostic_only() -> None:
    source = inspect.getsource(startup_contract.build_self_check)
    assert "'version_py_present'" in source
    assert "'package_integrity_manifest_present'" in source
    assert "'legacy_manifest_current_present'" in source
    assert "'manifest_current_present':" not in source


def test_active_code_does_not_recommend_legacy_release_sources() -> None:
    active_paths = [
        ROOT / "latka_jazn" / "core" / "self_knowledge_contract.py",
        ROOT / "latka_jazn" / "core" / "runtime_activation_cascade.py",
        ROOT / "latka_jazn" / "core" / "runtime_response_synthesizer.py",
        ROOT / "latka_jazn" / "resources" / "startup_contract_v14_8_2_4.json",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)
    assert "VERSION.txt" not in combined
    assert "MANIFEST_CURRENT.json" not in combined
    assert "--chat-gpt-final-only" not in combined


def test_historical_update_docs_are_not_loaded_as_active_contract_content() -> None:
    loader_source = inspect.getsource(self_knowledge_contract.load_self_knowledge_contract)
    assert "docs/update_history" not in loader_source
    assert "SELF_KNOWLEDGE_RESOURCE" in loader_source


def test_active_generators_neither_write_nor_plan_legacy_release_files() -> None:
    for path in ACTIVE_GENERATORS:
        source = path.read_text(encoding="utf-8")
        assert _legacy_write_calls(path) == [], path
        assert "VERSION.txt" not in source, path
        assert "MANIFEST_CURRENT.json" not in source, path


def test_config_has_no_canonical_manifest_current_alias() -> None:
    path = ROOT / "latka_jazn" / "config.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    properties = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "package_integrity_manifest_path" in properties
    assert "legacy_manifest_current_path" in properties
    assert "manifest_current_path" not in properties


def test_active_update_checkpoints_use_only_canonical_release_sources() -> None:
    auto_update = (ROOT / "latka_jazn" / "memory" / "auto_memory_update.py").read_text(encoding="utf-8")
    repository_plan = (ROOT / "latka_jazn" / "integrations" / "github_repository_plan.py").read_text(encoding="utf-8")
    assert '"latka_jazn/version.py"' in auto_update
    assert '"latka_jazn/version.py"' in repository_plan
    assert '"PACKAGE_INTEGRITY_MANIFEST.json"' in repository_plan
    assert "MANIFEST_*.json" not in repository_plan
