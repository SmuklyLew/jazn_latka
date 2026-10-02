from __future__ import annotations

import json
from pathlib import Path
import tomllib

from latka_jazn.dependencies.runtime import resolve_profile_requirements


ROOT = Path(__file__).parents[1]


def test_pypdf_is_optional_pdf_capability_not_activation_core() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    base = list(pyproject["project"]["dependencies"])
    optional = pyproject["project"]["optional-dependencies"]
    assert not any(str(item).startswith("pypdf") for item in base)
    assert optional["pdf"] == ["pypdf>=6.19.0,<7"]

    registry = json.loads(
        (ROOT / "latka_jazn/resources/dependencies/profiles.json").read_text(encoding="utf-8")
    )
    assert registry["activation_profiles"] == ["core"]
    assert registry["profiles"]["pdf"] == {
        "kind": "runtime_optional",
        "source_optional_group": "pdf",
    }
    assert registry["release_profiles"] == ["core", "archive", "pdf"]
    assert "pdf" in registry["profiles"]["all"]["includes"]

    core = resolve_profile_requirements(ROOT, ["core"])
    release = resolve_profile_requirements(ROOT, registry["release_profiles"])
    assert "pypdf>=6.19.0,<7" not in core
    assert "pypdf>=6.19.0,<7" in release


def test_release_locks_follow_explicit_core_archive_pdf_profile() -> None:
    locks = ROOT / "latka_jazn/resources/dependencies/locks"
    current = locks / "core+archive+pdf"
    legacy = locks / "core+archive"
    expected = {
        "windows-x64-py312.txt",
        "windows-x64-py313.txt",
        "windows-x64-py314.txt",
        "linux-x64-py312.txt",
        "linux-x64-py313.txt",
        "linux-x64-py314.txt",
    }
    assert current.is_dir()
    assert {path.name for path in current.glob("*.txt")} == expected
    assert not legacy.exists()
    for path in current.glob("*.txt"):
        text = path.read_text(encoding="utf-8")
        assert "pypdf==6.19.0 --hash=sha256:7e5d6e730e7dae87d560a2cee218b852f6498c8be61966f3cd02ead971e48d14" in text


def test_dependency_block_message_names_only_activation_required_core() -> None:
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "required core+archive Python dependencies" not in text
    assert "activation-required core Python dependencies" in text
