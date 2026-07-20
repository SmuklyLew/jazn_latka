from __future__ import annotations

import subprocess
from pathlib import Path

from latka_jazn.config import JaznConfig
from latka_jazn.core.chat_command_contract import command_contract
from latka_jazn.core.runtime_environment import OLLAMA_ADAPTER, detect_runtime_environment

_TEXT_SUFFIXES = {".py", ".md", ".json", ".txt", ".toml", ".yml", ".yaml"}
_DYNAMIC_ROOTS = {".git", ".pytest_cache", "__pycache__", "exports", "memory", "workspace_runtime"}


def _repository_text_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return [
            path
            for path in root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in _TEXT_SUFFIXES
            and not any(part in _DYNAMIC_ROOTS for part in path.relative_to(root).parts)
        ]

    return [
        root / raw_path.decode("utf-8", errors="surrogateescape")
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]


def test_chat_ollama_selects_native_adapter(tmp_path: Path) -> None:
    cfg = JaznConfig(root=tmp_path)
    cfg.local_model_name = "test-model"
    status = detect_runtime_environment(cfg, command="--chat-ollama", env={})
    assert status.visible_channel_adapter == OLLAMA_ADAPTER
    assert status.effective_runtime_adapter == OLLAMA_ADAPTER


def test_ollama_contract_is_local_and_keyless() -> None:
    contract = command_contract("--chat-ollama")
    assert contract["command"] == "--chat-ollama"
    assert contract["requires_api_key"] is False
    assert contract["uses_openai_api"] is False
    assert "Ollama" in contract["truth_boundary"]


def test_active_repository_has_no_removed_local_backend_integration() -> None:
    root = Path(__file__).resolve().parents[1]
    stem = "lm" + "studio"
    forbidden = (stem, "lm_" + "studio", "lm-" + "studio", "lm " + "studio")
    excluded = {
        root / "PACKAGE_INTEGRITY_MANIFEST.json",
        root / "latka_jazn/contracts/embedded_sources.py",
    }
    offenders: list[str] = []

    for path in _repository_text_files(root):
        if path in excluded or not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").casefold()
        if any(token in text for token in forbidden):
            offenders.append(str(path.relative_to(root)))

    assert sorted(offenders) == []
