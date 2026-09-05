from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from latka_jazn.version import DISTRIBUTION_VERSION

ROOT = Path(__file__).resolve().parents[1]
STALE_PACKAGE_VERSION = "v" + ".".join(("15", "1", "0", "3", "90"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def rebuild():
    return load_module("jazn_version_rebuild_regression", ROOT / "tools" / "jazn_version_rebuild.py")


def make_rebuild_fixture(root: Path, rebuild: Any) -> Any:
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        f'DISTRIBUTION_VERSION = {DISTRIBUTION_VERSION!r}\n'
        'PACKAGE_VERSION = "v15.1.0.3.99"\n'
        'PACKAGE_RELEASE_NAME = "Memory Sqlite Pipeline"\n',
        encoding="utf-8",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\ndynamic = ["version"]\n'
        '[tool.setuptools.dynamic]\nversion = {attr = "latka_jazn.version.DISTRIBUTION_VERSION"}\n',
        encoding="utf-8",
    )
    version = rebuild.read_version(root)
    (root / rebuild.PROVENANCE_PATH).write_text(
        json.dumps(
            {
                "schema_version": f"source_provenance/{version.package}",
                "base_version": version.full,
                "runtime_version": version.full,
                "update_version": version.full,
                "version_source": "latka_jazn/version.py",
            }
        ) + "\n",
        encoding="utf-8",
    )
    (root / rebuild.MANIFEST_PATH).write_text(
        json.dumps(
            {
                "schema_version": f"package_integrity_manifest/{version.package}",
                "version": version.full,
                "runtime_version": version.full,
                "package_version": version.full,
            }
        ) + "\n",
        encoding="utf-8",
    )
    return version


def init_git(root: Path) -> None:
    for command in (
        ["git", "init", "-q"],
        ["git", "config", "user.name", "Version Rebuild Test"],
        ["git", "config", "user.email", "version-rebuild@example.invalid"],
        ["git", "add", "."],
        ["git", "commit", "-qm", "fixture"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)


def test_version_rebuild_metadata_check_includes_base_version(tmp_path: Path, rebuild) -> None:
    version = make_rebuild_fixture(tmp_path, rebuild)
    payload = json.loads((tmp_path / rebuild.PROVENANCE_PATH).read_text(encoding="utf-8"))
    payload["base_version"] = f"{STALE_PACKAGE_VERSION}-Memory Sqlite Pipeline"
    (tmp_path / rebuild.PROVENANCE_PATH).write_text(json.dumps(payload), encoding="utf-8")

    assert rebuild.metadata_current(tmp_path, rebuild.PROVENANCE_PATH, version) is False


def test_version_rebuild_streams_subprocess_output(tmp_path: Path, rebuild) -> None:
    lines: list[str] = []
    result = rebuild.command_streaming(
        [sys.executable, "-c", "print('etap 1'); print('etap 2')"],
        tmp_path,
        timeout=10,
        on_output=lines.append,
    )
    assert result.returncode == 0
    assert lines == ["etap 1", "etap 2"]
    assert "etap 1" in result.stdout


def test_version_rebuild_guides_user_through_commit_and_sync(tmp_path: Path, rebuild) -> None:
    version = make_rebuild_fixture(tmp_path, rebuild)
    init_git(tmp_path)
    assert "Możesz uruchomić generator paczek" in rebuild.workflow_guidance(tmp_path, version)

    version_path = tmp_path / rebuild.VERSION_PATH
    version_path.write_text(version_path.read_text(encoding="utf-8") + "# zmiana\n", encoding="utf-8")
    assert "zatwierdź latka_jazn/version.py" in rebuild.workflow_guidance(tmp_path, version)

    subprocess.run(["git", "checkout", "--", str(rebuild.VERSION_PATH)], cwd=tmp_path, check=True)
    provenance = json.loads((tmp_path / rebuild.PROVENANCE_PATH).read_text(encoding="utf-8"))
    provenance["runtime_version"] = f"{STALE_PACKAGE_VERSION}-Memory Sqlite Pipeline"
    (tmp_path / rebuild.PROVENANCE_PATH).write_text(json.dumps(provenance), encoding="utf-8")
    subprocess.run(["git", "add", str(rebuild.PROVENANCE_PATH)], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "stale metadata fixture"], cwd=tmp_path, check=True)
    assert "Synchronizuj metadane" in rebuild.workflow_guidance(tmp_path, version)


def test_version_rebuild_repeated_sync_accepts_current_metadata_only_changes(
    tmp_path: Path,
    rebuild,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    version = make_rebuild_fixture(tmp_path, rebuild)
    init_git(tmp_path)
    provenance_path = tmp_path / rebuild.PROVENANCE_PATH
    provenance_path.write_text(provenance_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    def unexpected_command(*_args, **_kwargs):
        raise AssertionError("kanoniczna synchronizacja nie powinna być uruchamiana ponownie")

    monkeypatch.setattr(rebuild, "command_streaming", unexpected_command)
    progress: list[tuple[int, str]] = []
    output = rebuild.sync_metadata(
        tmp_path,
        sys.executable,
        "master",
        progress=lambda value, message: progress.append((value, message)),
    )

    assert "już aktualne" in output
    assert progress[-1][0] == 100
    assert "czekają na commit" in progress[-1][1]
    assert "Zatwierdź SOURCE_PROVENANCE.json" in rebuild.workflow_guidance(tmp_path, version)
