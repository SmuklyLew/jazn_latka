from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_flat_runtime_layout_remains_directly_runnable_from_unpacked_root() -> None:
    assert (ROOT / "run.py").is_file()
    assert (ROOT / "main.py").is_file()
    assert (ROOT / "latka_jazn" / "__init__.py").is_file()
    assert not (ROOT / "src" / "latka_jazn").exists()

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    find_config = pyproject["tool"]["setuptools"]["packages"]["find"]
    assert find_config["where"] == ["."]
    assert find_config["include"] == ["latka_jazn*"]


def test_dependency_policy_has_one_canonical_declaration_and_offline_lock_boundary() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "Canonical direct runtime dependencies" in requirements
    assert "pyproject.toml -> [project].dependencies" in requirements
    assert "JAZN_WHEELHOUSE_REQUIREMENTS.txt" in requirements

    active_specs = [
        line.strip()
        for line in requirements.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert active_specs == []


def test_repository_policy_documents_host_and_model_boundaries() -> None:
    policy = (
        ROOT / "docs" / "project" / "REPOSITORY_LAYOUT_AND_DEPENDENCY_POLICY.md"
    ).read_text(encoding="utf-8")
    assert "stdlib/host-first" in policy
    assert "`python -X utf8 run.py chat-gpt ...`" in policy
    assert "`python -X utf8 run.py chat-ollama ...`" in policy
    assert "Nie dodawaj `openai` SDK" in policy
    assert "Nie dodawaj pakietu Python" in policy
    assert "`JAZN_WHEELHOUSE_REQUIREMENTS.txt`" in policy
    assert "workflow `release-hardening/manifest_sync`" in policy


def test_run_py_is_public_ollama_operator_and_keeps_legacy_translation_internal() -> None:
    text = (ROOT / "run.py").read_text(encoding="utf-8")
    assert '"chat-ollama",' in text
    assert 'if argv and argv[0] == "chat-ollama":' in text
    assert 'return ["--chat-ollama", *argv[1:]]' in text

    ollama = (ROOT / "AGENTS.ollama.md").read_text(encoding="utf-8")
    assert "python -X utf8 run.py chat-ollama" in ollama
    assert "main.py --chat-ollama" in ollama


def test_bridge_discovery_presents_run_py_as_operator_for_host_lifecycle_and_ollama() -> None:
    text = (ROOT / "latka_jazn" / "core" / "bridge_discovery.py").read_text(
        encoding="utf-8"
    )
    for command in (
        "python -X utf8 run.py chat",
        "python -X utf8 run.py chat-gpt",
        "python -X utf8 run.py chat-ollama",
        "python -X utf8 run.py start",
        "python -X utf8 run.py status --json",
        "python -X utf8 run.py stop",
    ):
        assert command in text
