from __future__ import annotations

import importlib
from pathlib import Path
import os
import zipfile

def generator():
    return importlib.import_module("tools.jazn_pack_generator")

def _root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text(
        'PACKAGE_VERSION = "16.3.25.5.23"\n'
        'PACKAGE_RELEASE_NAME = "package-generator-v10.1.86.0.111-clean-rewrite"\n',
        encoding="utf-8",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    (root / "system.txt").write_text("system", encoding="utf-8")
    (root / "memory").mkdir()
    (root / "memory/old.txt").write_text("must not enter SYSTEM", encoding="utf-8")
    return root

def test_v101860111_system_is_folder_snapshot_without_memory(tmp_path: Path) -> None:
    module = generator()
    root = _root(tmp_path)
    result = module.run_pack_request(source=root, out_dir=tmp_path / "out", content="system")
    with zipfile.ZipFile(result["logical_archive"]) as archive:
        names = set(archive.namelist())
    assert "system.txt" in names
    assert not any(name.startswith("memory/") for name in names)
    assert "package_distribution" not in (Path(module.__file__).read_text(encoding="utf-8"))

def test_v101860111_memory_only_and_split_join_roundtrip(tmp_path: Path) -> None:
    module = generator()
    root = _root(tmp_path)
    memory = tmp_path / "private-memory"
    memory.mkdir()
    (memory / "a.bin").write_bytes(os.urandom(2 * 1024 * 1024 + 123))
    result = module.run_pack_request(
        source=root, out_dir=tmp_path / "out", content="memory", memory_root=memory,
        split=True, split_size_mib=1, force_split=True,
    )
    assert result["logical_archive"] is None
    assert len(result["parts"]) >= 2
    report = module.verify_package(Path(result["parts"][0]))
    assert report["ok"] is True
    joined = module.join_parts(Path(result["parts"][0]), tmp_path / "joined.zip")
    with zipfile.ZipFile(joined) as archive:
        assert "memory/a.bin" in archive.namelist()

def test_v101860111_system_plus_memory_is_one_logical_zip(tmp_path: Path) -> None:
    module = generator()
    root = _root(tmp_path)
    memory = tmp_path / "private-memory"
    memory.mkdir()
    (memory / "fresh.txt").write_text("memory", encoding="utf-8")
    result = module.run_pack_request(
        source=root, out_dir=tmp_path / "out", content="system+memory", memory_root=memory,
    )
    with zipfile.ZipFile(result["logical_archive"]) as archive:
        names = set(archive.namelist())
    assert "system.txt" in names
    assert "memory/fresh.txt" in names
    assert "memory/old.txt" not in names
