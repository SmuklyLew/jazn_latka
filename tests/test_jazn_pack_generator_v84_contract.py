from __future__ import annotations

import importlib.util
import hashlib
import json
import subprocess
import zipfile
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"


def _load_generator():
    module_name = "jazn_pack_generator_v84_contract_test"
    spec = importlib.util.spec_from_file_location(module_name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_fixture(root: Path) -> Path:
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        'DISTRIBUTION_VERSION = "91.82.73.64"\n'
        'PACKAGE_VERSION = "v91.82.73.64"\n'
        'PACKAGE_RELEASE_NAME = "fixture-release"\n',
        encoding="utf-8",
    )
    (root / "SOURCE_PROVENANCE.json").write_text("{}\n", encoding="utf-8")
    (root / "PACKAGE_INTEGRITY_MANIFEST.json").write_text("{}\n", encoding="utf-8")
    (root / ".gitignore").write_text("memory/\nworkspace_runtime/\n.packages/\n", encoding="utf-8")
    (root / "run.py").write_text("print('run')\n", encoding="utf-8")
    (root / "main.py").write_text("print('main')\n", encoding="utf-8")
    (root / "payload.txt").write_text("system payload\n", encoding="utf-8")
    return root


def _init_git_repo(root: Path) -> None:
    commands = [
        ["git", "init", "-q"],
        ["git", "config", "user.name", "Generator Test"],
        ["git", "config", "user.email", "generator@example.invalid"],
        ["git", "remote", "add", "origin", "https://github.com/SmuklyLew/jazn_latka.git"],
        ["git", "add", "."],
        ["git", "commit", "-qm", "fixture"],
        ["git", "branch", "-M", "master"],
    ]
    for command in commands:
        subprocess.run(command, cwd=root, check=True, capture_output=True)


def _zip_path(result) -> Path:
    matches = [path for path in result.committed_paths if path.name.endswith(".zip")]
    assert len(matches) == 1
    return matches[0]


def test_generator_identity_examples_and_default_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generator = _load_generator()

    assert generator.GENERATOR_VERSION == "8.7"
    assert generator.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.7"
    assert generator.__doc__ is not None
    assert r"py -X utf8 .\tools\jazn_pack_generator.py" in generator.__doc__
    assert "py _jazn_pack_generator.py" not in generator.__doc__
    assert r"D:\.AI\.packages" in generator.__doc__

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    state = generator.default_interactive_state()
    assert state.out_dir == tmp_path / ".packages"


def test_cli_rejects_abbreviated_long_options() -> None:
    generator = _load_generator()

    exact = generator.parser().parse_args(["pack", ".", "--profile", "system"])
    assert exact.profile == "system"

    with pytest.raises(SystemExit):
        generator.parser().parse_args(["pack", ".", "--prof", "system"])
    with pytest.raises(SystemExit):
        generator.parser().parse_args(["plan", ".", "--prof", "system"])
    with pytest.raises(SystemExit):
        generator.parser().parse_args(["extract", "sidecar.json", "out", "--cl"])


def test_v83_menu_and_responsive_contract(tmp_path: Path) -> None:
    generator = _load_generator()
    state = generator.InteractiveState(
        source=tmp_path / "jazn",
        out_dir=tmp_path / ".packages",
        profile="dual",
    )

    rows = generator.main_menu_rows(state)
    assert rows[:3] == [
        "Profil: [SYSTEM + PAMIĘĆ (2 OSOBNE ZIP-y)]",
        "Pakuj teraz",
        "Pokaż kanoniczny plan",
    ]
    assert rows[3].startswith("System Jaźni: [")
    assert rows[4].startswith("Zapis archiwum: [")
    assert rows[5].startswith("Nazwa: [")
    assert rows[6] == "Odśwież nazwę paczki"
    assert "Zapisz ustawienia" not in rows

    details = generator.main_menu_details(state)
    assert "modalnym oknie wyskakującym" in details[0]
    assert "następnym wierszu" in details[3]
    assert "następnym wierszu" in details[4]
    assert "następnym wierszu" in details[5]

    assert generator.dashboard_left_width_mode(right_visible=False, compact=False) == "full"
    assert generator.dashboard_left_width_mode(right_visible=True, compact=False) == "narrow"
    assert generator.dashboard_left_width_mode(right_visible=False, compact=True) == "compact"


def test_canonical_system_package_requires_both_entrypoints(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _runtime_fixture(tmp_path / "runtime")

    plan = generator.build_plan(root, "system", [])
    assert {"run.py", "main.py"} <= set(plan.paths)

    (root / "main.py").unlink()
    with pytest.raises(generator.PackError, match="main.py"):
        generator.build_plan(root, "system", [])


def test_dual_package_roundtrip_and_exclusion_contract(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _runtime_fixture(tmp_path / "runtime")
    memory = root / "memory"
    memory.mkdir()
    (memory / "runtime_memory.sqlite3").write_bytes(b"sqlite fixture")
    (memory / "runtime_memory.sqlite3-wal").write_bytes(b"transient")
    (memory / "nested.zip").write_bytes(b"not a real zip")
    (root / "workspace_runtime").mkdir()
    (root / "workspace_runtime" / "state.json").write_text("{}\n", encoding="utf-8")
    _init_git_repo(root)

    out_dir = tmp_path / ".packages"
    options = generator.PackOptions(
        source=root,
        out_dir=out_dir,
        profile="dual",
        archive_format="independent",
        archive_basename="",
        part_size_mb=4,
        compatibility_checks=False,
        update_source_manifest=True,
    )

    original_provenance = (root / "SOURCE_PROVENANCE.json").read_bytes()
    original_manifest = (root / "PACKAGE_INTEGRITY_MANIFEST.json").read_bytes()
    plans = generator.build_plans_for_options(options)
    assert (root / "SOURCE_PROVENANCE.json").read_bytes() == original_provenance
    assert (root / "PACKAGE_INTEGRITY_MANIFEST.json").read_bytes() == original_manifest

    results = generator.run_pack_with_plans(options, plans)
    by_profile = {result.profile: result for result in results}
    assert set(by_profile) == {"system", "memory"}

    system_sidecar = json.loads(by_profile["system"].sidecar_path.read_text(encoding="utf-8"))
    system_entries = {item["path"] for item in system_sidecar["entries"]}
    assert "PACKAGE_INTEGRITY_MANIFEST.json" in system_entries
    assert not any(path.startswith("memory/") for path in system_entries)
    assert not any(path.startswith("workspace_runtime/") for path in system_entries)

    memory_sidecar = json.loads(by_profile["memory"].sidecar_path.read_text(encoding="utf-8"))
    memory_entries = {item["path"] for item in memory_sidecar["entries"]}
    assert "memory/runtime_memory.sqlite3" in memory_entries
    assert "memory/MEMORY_PACKAGE_MANIFEST.json" in memory_entries
    assert "memory/runtime_memory.sqlite3-wal" not in memory_entries
    assert "memory/nested.zip" not in memory_entries

    system_plan = next(plan for plan in plans if plan.profile == "system")
    virtual = {entry.relative: entry.virtual_bytes for entry in system_plan.entries}
    assert virtual["SOURCE_PROVENANCE.json"] is not None
    assert virtual["PACKAGE_INTEGRITY_MANIFEST.json"] is not None
    assert (root / "SOURCE_PROVENANCE.json").read_bytes() == virtual["SOURCE_PROVENANCE.json"]
    assert (root / "PACKAGE_INTEGRITY_MANIFEST.json").read_bytes() == virtual["PACKAGE_INTEGRITY_MANIFEST.json"]

    with zipfile.ZipFile(_zip_path(by_profile["system"]), "r") as archive:
        archived_provenance = archive.read("SOURCE_PROVENANCE.json")
        archived_manifest = archive.read("PACKAGE_INTEGRITY_MANIFEST.json")
    assert archived_provenance == virtual["SOURCE_PROVENANCE.json"]
    assert archived_manifest == virtual["PACKAGE_INTEGRITY_MANIFEST.json"]
    manifest_payload = json.loads(archived_manifest.decode("utf-8"))
    provenance_row = next(item for item in manifest_payload["files"] if item["path"] == "SOURCE_PROVENANCE.json")
    assert provenance_row["sha256"] == hashlib.sha256(archived_provenance).hexdigest()

    persisted_before_replan = {
        name: (root / name).read_bytes()
        for name in generator.RELEASE_METADATA_PATHS
    }
    repeated_plans = generator.build_plans_for_options(options)
    assert {
        name: (root / name).read_bytes()
        for name in generator.RELEASE_METADATA_PATHS
    } == persisted_before_replan
    repeated_system = next(plan for plan in repeated_plans if plan.profile == "system")
    repeated_virtual = {entry.relative: entry.virtual_bytes for entry in repeated_system.entries}
    assert repeated_virtual["SOURCE_PROVENANCE.json"] == archived_provenance
    assert repeated_virtual["PACKAGE_INTEGRITY_MANIFEST.json"] == archived_manifest

    for result in results:
        report = generator.verify_package_sidecar(result.sidecar_path)
        assert report["ok"] is True
        destination = tmp_path / f"extract-{result.profile}"
        extracted = generator.extract_package_sidecar(
            result.sidecar_path,
            destination,
            clean=False,
            force=False,
        )
        assert extracted["destination"] == str(destination.resolve())

    assert (tmp_path / "extract-system" / "run.py").is_file()
    assert (tmp_path / "extract-system" / "main.py").is_file()
    assert not (tmp_path / "extract-system" / "memory").exists()
    assert (tmp_path / "extract-memory" / "memory" / "runtime_memory.sqlite3").is_file()


def test_pack_failure_does_not_touch_release_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    generator = _load_generator()
    root = _runtime_fixture(tmp_path / "runtime")
    _init_git_repo(root)
    options = generator.PackOptions(
        source=root,
        out_dir=tmp_path / ".packages",
        profile="system",
        archive_format="independent",
        archive_basename="",
        compatibility_checks=False,
        update_source_manifest=True,
    )
    original = {
        name: (root / name).read_bytes()
        for name in generator.RELEASE_METADATA_PATHS
    }
    plans = generator.build_plans_for_options(options)
    assert {name: (root / name).read_bytes() for name in generator.RELEASE_METADATA_PATHS} == original

    def fail_package(*_args, **_kwargs):
        raise generator.PackError("controlled package failure")

    monkeypatch.setattr(generator, "package_one", fail_package)
    with pytest.raises(generator.PackError, match="controlled package failure"):
        generator.run_pack_with_plans(options, plans)
    assert {name: (root / name).read_bytes() for name in generator.RELEASE_METADATA_PATHS} == original


def test_memory_only_package_never_requires_git_or_updates_system_metadata(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _runtime_fixture(tmp_path / "runtime")
    memory = root / "memory"
    memory.mkdir()
    (memory / "runtime_memory.sqlite3").write_bytes(b"memory-only")
    original = {
        name: (root / name).read_bytes()
        for name in generator.RELEASE_METADATA_PATHS
    }
    options = generator.PackOptions(
        source=root,
        out_dir=tmp_path / ".packages",
        profile="memory",
        archive_format="independent",
        archive_basename="",
        compatibility_checks=False,
        update_source_manifest=True,
    )
    results = generator.run_pack(options)
    assert [result.profile for result in results] == ["memory"]
    assert {name: (root / name).read_bytes() for name in generator.RELEASE_METADATA_PATHS} == original





def test_existing_release_metadata_lock_blocks_system_plan_without_touching_source(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _runtime_fixture(tmp_path / "runtime")
    _init_git_repo(root)
    lock = root / generator.RELEASE_METADATA_LOCK
    lock.write_text("{}\n", encoding="utf-8")
    original = {
        name: (root / name).read_bytes()
        for name in generator.RELEASE_METADATA_PATHS
    }

    with pytest.raises(generator.PackError, match="inny proces generatora"):
        generator.build_plan(
            root,
            "system",
            [],
            synchronize_release_metadata=True,
        )

    assert {
        name: (root / name).read_bytes()
        for name in generator.RELEASE_METADATA_PATHS
    } == original
    assert lock.is_file()

def test_release_metadata_write_rolls_back_both_files_on_second_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = _load_generator()
    root = _runtime_fixture(tmp_path / "runtime")
    _init_git_repo(root)
    options = generator.PackOptions(
        source=root,
        out_dir=tmp_path / ".packages",
        profile="system",
        archive_format="independent",
        archive_basename="",
        compatibility_checks=False,
        update_source_manifest=True,
    )
    plan = generator.build_plans_for_options(options)[0]
    original = {
        name: (root / name).read_bytes()
        for name in generator.RELEASE_METADATA_PATHS
    }
    real_replace = generator._write_file_from_temp
    calls = {"count": 0}

    def fail_second_metadata_replace(temp: Path, target: Path) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("controlled second replace failure")
        real_replace(temp, target)

    monkeypatch.setattr(generator, "_write_file_from_temp", fail_second_metadata_replace)
    with pytest.raises(generator.PackError, match="przywrócono poprzedni stan"):
        generator.write_source_release_metadata_from_plan(plan)

    assert {
        name: (root / name).read_bytes()
        for name in generator.RELEASE_METADATA_PATHS
    } == original
    assert not (root / generator.RELEASE_METADATA_LOCK).exists()
    assert not list(root.glob("*.tmp"))

def test_path_safety_rejects_traversal_and_absolute_paths(tmp_path: Path) -> None:
    generator = _load_generator()
    for unsafe in ("../escape.txt", "/absolute.txt", r"C:\absolute.txt"):
        with pytest.raises(generator.PackError):
            generator.safe_destination_path(tmp_path, unsafe)
