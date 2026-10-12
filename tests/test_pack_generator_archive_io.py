from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"


def _load_generator():
    name = "jazn_pack_generator_archive_io_v101860111_test"
    spec = importlib.util.spec_from_file_location(name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn" / "version.py").write_text(
        'PACKAGE_VERSION = "16.3.25.5.23"\n'
        'PACKAGE_RELEASE_NAME = "package-generator-v10.1.86.0.111-clean-rewrite"\n',
        encoding="utf-8",
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    return root


def test_parser_exposes_only_zip_and_split_transport_scope() -> None:
    generator = _load_generator()
    parsed = generator._parser().parse_args(
        ["pack", "--source", ".", "--out-dir", "out", "--content", "memory", "--split"]
    )
    assert parsed.content == "memory"
    assert parsed.split is True
    with pytest.raises(SystemExit):
        generator._parser().parse_args(
            ["pack", "--source", ".", "--out-dir", "out", "--container-format", "7z"]
        )


def test_split_transport_is_one_logical_zip_joined_byte_for_byte(tmp_path: Path) -> None:
    generator = _load_generator()
    root = _root(tmp_path)
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "blob.bin").write_bytes(os.urandom(2 * 1024 * 1024 + 17))
    result = generator.run_pack_request(
        source=root,
        out_dir=tmp_path / "packages",
        content="memory",
        memory_root=memory,
        split=True,
        split_size_mib=1,
        force_split=True,
    )
    assert result["logical_archive"] is None
    assert len(result["parts"]) >= 2
    joined = generator.join_parts(Path(result["parts"][0]), tmp_path / "joined.zip")
    assert generator.verify_package(joined)["ok"] is True
    with zipfile.ZipFile(joined, "r") as archive:
        assert archive.testzip() is None
        assert archive.read("memory/blob.bin") == (memory / "blob.bin").read_bytes()


def test_configuration_does_not_claim_7z_rar_or_encryption_backends() -> None:
    generator = _load_generator()
    report = generator.config_report()
    assert report["features"]["zip"] is True
    assert report["features"]["zip64"] is True
    assert report["features"]["split_transport"] is True
    rendered = str(report).lower()
    assert "aes_zip" not in rendered
    assert "rar" not in report["features"]
