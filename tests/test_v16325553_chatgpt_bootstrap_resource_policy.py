from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

import pytest

import CHATGPT_BOOTSTRAP as bootstrap
from latka_jazn.packaging.zip_resource_limits import (
    DEFAULT_MAX_COMPRESSION_RATIO,
    DEFAULT_MAX_MEMBER_UNCOMPRESSED_BYTES,
    DEFAULT_MAX_MEMBERS,
    DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
)


_REQUIRED_MEMBERS = {
    "run.py": "print('ok')\n",
    "AGENTS.md": "# test\n",
    "latka_jazn/version.py": "PACKAGE_VERSION='test'\n",
    "PACKAGE_INTEGRITY_MANIFEST.json": "{}\n",
    "SOURCE_PROVENANCE.json": "{}\n",
}


def _write_zip(path: Path, members: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in members.items():
            zf.writestr(name, content)


def _sidecar(zip_path: Path) -> Path:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sidecar = zip_path.with_name(f"{zip_path.name}.sha256")
    sidecar.write_text(f"{digest}  {zip_path.name}\n", encoding="ascii")
    return sidecar


def test_standalone_bootstrap_defaults_match_canonical_zip_policy() -> None:
    assert bootstrap.DEFAULT_MAX_ENTRIES == DEFAULT_MAX_MEMBERS
    assert bootstrap.DEFAULT_MAX_TOTAL_BYTES == DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES
    assert bootstrap.DEFAULT_MAX_MEMBER_BYTES == DEFAULT_MAX_MEMBER_UNCOMPRESSED_BYTES
    assert bootstrap.DEFAULT_MAX_COMPRESSION_RATIO == DEFAULT_MAX_COMPRESSION_RATIO


def test_standalone_bootstrap_rejects_excessive_compression_ratio(tmp_path: Path) -> None:
    package = tmp_path / "system.zip"
    members = dict(_REQUIRED_MEMBERS)
    members["highly-compressible.txt"] = "A" * 100_000
    _write_zip(package, members)
    sidecar = _sidecar(package)
    destination = tmp_path / "runtime"

    with pytest.raises(bootstrap.BootstrapError, match="compression-ratio limit exceeded"):
        bootstrap.bootstrap_system_zip(
            zip_path=package,
            sha256_file_path=sidecar,
            destination=destination,
            max_compression_ratio=2.0,
        )

    assert not destination.exists()


def test_standalone_bootstrap_cli_exposes_compression_ratio_limit() -> None:
    parser = bootstrap._build_parser()
    parsed = parser.parse_args(
        [
            "--zip",
            "system.zip",
            "--expected-sha256",
            "0" * 64,
            "--destination",
            "runtime",
            "--max-compression-ratio",
            "77.5",
        ]
    )

    assert parsed.max_compression_ratio == 77.5
