from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = ROOT / "tools" / "jazn_pack_generator.py"


def _load_generator():
    name = "jazn_pack_generator_archive_io_v1638_test"
    spec = importlib.util.spec_from_file_location(name, GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _memory_plan(generator, tmp_path: Path):
    source = tmp_path / "memory-source.txt"
    source.write_text("archive generator fixture\n", encoding="utf-8")
    version = generator.VersionInfo(
        Path("latka_jazn/version.py"),
        "16.3.8",
        "archive-io-generator-hardening",
        "16.3.8-archive-io-generator-hardening",
        "16.3.8-archive-io-generator-hardening",
    )
    entry = generator.PlanEntry(
        relative="memory/raw/fixture.txt",
        source=source,
        size_bytes=source.stat().st_size,
        sha256=generator.sha256_file(source),
        classification="memory_file",
    )
    return generator.PackPlan(
        root=tmp_path,
        profile="memory",
        version=version,
        entries=[entry],
        manifest_builder="test",
    )


def test_parser_exposes_archive_container_and_security_options() -> None:
    generator = _load_generator()
    parsed = generator.parser().parse_args(
        [
            "pack", ".", "--profile", "memory",
            "--container-format", "7z",
            "--encrypt-7z",
            "--password-env", "TEST_ARCHIVE_PASSWORD",
            "--extract-max-ratio", "250",
        ]
    )
    assert parsed.container_format == "7z"
    assert parsed.encrypt_7z is True
    assert parsed.archive_password_env == "TEST_ARCHIVE_PASSWORD"
    assert parsed.archive_max_ratio == 250.0


def test_generator_7z_package_and_sidecar_roundtrip(tmp_path: Path) -> None:
    generator = _load_generator()
    plan = _memory_plan(generator, tmp_path)
    options = generator.PackOptions(
        source=tmp_path,
        out_dir=tmp_path / "out",
        profile="memory",
        archive_format="independent",
        archive_basename="jazn_latka_v16.3.8-archive-io-generator-hardening",
        sidecars=True,
        compatibility_checks=False,
    )
    settings = generator.GeneratorArchiveSettings(container_format="7z", require_free_space=False)
    with generator.archive_settings_override(settings):
        result = generator.package_one(plan, options, "fixture_memory.zip")
        assert result.package_name == "fixture_memory.7z"
        assert result.sidecar_path.name == "fixture_memory.7z.package.json"
        payload = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
        assert payload["container_format"] == "7z"
        assert payload["archive_io_contract"] == "jazn_archive_io/v1"
        assert payload["encryption"]["secret_persisted"] is False
        extracted = generator.extract_package_sidecar(result.sidecar_path, tmp_path / "roundtrip")
    assert (tmp_path / "roundtrip/memory/raw/fixture.txt").read_text(encoding="utf-8") == "archive generator fixture\n"


def test_generator_aes_zip_never_persists_secret(tmp_path: Path, monkeypatch) -> None:
    generator = _load_generator()
    plan = _memory_plan(generator, tmp_path)
    options = generator.PackOptions(
        source=tmp_path,
        out_dir=tmp_path / "aes-out",
        profile="memory",
        archive_format="independent",
        sidecars=True,
        compatibility_checks=False,
    )
    monkeypatch.setenv("TEST_JAZN_AES_PASSWORD", "not-written-to-sidecar")
    settings = generator.GeneratorArchiveSettings(
        container_format="aes_zip",
        password_env="TEST_JAZN_AES_PASSWORD",
        aes_bits=256,
        require_free_space=False,
    )
    with generator.archive_settings_override(settings):
        result = generator.package_one(plan, options, "fixture_memory.zip")
        payload_text = result.sidecar_path.read_text(encoding="utf-8")
        payload = json.loads(payload_text)
        assert payload["container_format"] == "aes_zip"
        assert payload["encryption"]["method"] == "WZ_AES_256"
        assert payload["encryption"]["password_env"] == "TEST_JAZN_AES_PASSWORD"
        assert "not-written-to-sidecar" not in payload_text
        generator.extract_package_sidecar(result.sidecar_path, tmp_path / "aes-roundtrip")
    assert (tmp_path / "aes-roundtrip/memory/raw/fixture.txt").is_file()
