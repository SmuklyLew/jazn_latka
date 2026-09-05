from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"


def _load_generator():
    name = "jazn_pack_generator_v101860111_profile_contract_test"
    spec = importlib.util.spec_from_file_location(name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        'PACKAGE_VERSION = "16.3.25.5.23"\n'
        'PACKAGE_RELEASE_NAME = "package-generator-v10.1.86.0.111-clean-rewrite"\n',
        encoding="utf-8",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    (root / "system.txt").write_text("system", encoding="utf-8")
    return root


def test_v101860111_exposes_exact_three_user_content_choices() -> None:
    generator = _load_generator()
    assert generator.GENERATOR_VERSION == "10.1.86.0.111"
    assert generator.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v1"
    assert generator.CONTENT_CHOICES == ("system", "memory", "system+memory")


def test_system_plan_is_plain_system_snapshot_without_memory(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _root(tmp_path)
    (root / "memory").mkdir()
    (root / "memory" / "old.txt").write_text("memory", encoding="utf-8")
    plan = generator.plan_pack(
        generator.PackRequest(
            source_root=root,
            output_root=tmp_path / "out",
            content=generator.ContentMode.SYSTEM,
        )
    )
    names = {entry.archive_path for entry in plan.entries}
    assert "system.txt" in names
    assert not any(name.startswith("memory/") for name in names)


def test_memory_plan_uses_selected_memory_root(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _root(tmp_path)
    memory = tmp_path / "memory-source"
    memory.mkdir()
    (memory / "fresh.txt").write_text("memory", encoding="utf-8")
    plan = generator.plan_pack(
        generator.PackRequest(
            source_root=root,
            output_root=tmp_path / "out",
            content=generator.ContentMode.MEMORY,
            memory_root=memory,
        )
    )
    names = {entry.archive_path for entry in plan.entries}
    assert "memory/fresh.txt" in names
    assert "system.txt" not in names


def test_combined_plan_has_system_and_selected_memory_in_one_plan(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _root(tmp_path)
    (root / "memory").mkdir()
    (root / "memory" / "old.txt").write_text("old", encoding="utf-8")
    memory = tmp_path / "memory-source"
    memory.mkdir()
    (memory / "fresh.txt").write_text("fresh", encoding="utf-8")
    plan = generator.plan_pack(
        generator.PackRequest(
            source_root=root,
            output_root=tmp_path / "out",
            content=generator.ContentMode.SYSTEM_AND_MEMORY,
            memory_root=memory,
        )
    )
    names = {entry.archive_path for entry in plan.entries}
    assert "system.txt" in names
    assert "memory/fresh.txt" in names
    assert "memory/old.txt" not in names
