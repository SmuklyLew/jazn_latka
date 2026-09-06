from __future__ import annotations

import json
from pathlib import Path

import latka_jazn.archive.capabilities as capabilities
from latka_jazn.archive import archive_capability_report, archive_format_capability
from latka_jazn.core.capability_reality_checker import CapabilityRealityChecker
from latka_jazn.core.handlers.capability_status_handler import CapabilityStatusHandler


ROOT = Path(__file__).parents[1]


def _format(report: dict, name: str) -> dict:
    return next(item for item in report["formats"] if item["format"] == name)


def _operations(row: dict) -> dict[str, bool]:
    return {item["name"]: bool(item["available"]) for item in row["operations"]}


def test_archive_report_separates_knowledge_from_executable_support() -> None:
    report = archive_capability_report().to_dict()
    assert report["schema_version"].startswith("archive_capability_matrix/")
    assert "container" in report["archive_definition"].lower()
    assert "extension alone is not proof" in report["archive_definition"]
    assert "knowledge of an archive format" in report["truth_boundary"]

    zip_row = _format(report, "zip")
    assert zip_row["backend"] == "python.stdlib.zipfile"
    assert zip_row["backend_kind"] == "stdlib"
    assert zip_row["runtime_supported"] is True
    zip_ops = _operations(zip_row)
    assert all(zip_ops[name] for name in ("detect", "inspect", "list", "integrity_test", "extract", "create"))
    assert zip_ops["create_encrypted_zip"] is False


def test_optional_archive_backends_report_missing_without_erasing_format_knowledge(monkeypatch) -> None:
    monkeypatch.setattr(capabilities, "_module_available", lambda name: False)
    report = capabilities.archive_capability_report().to_dict()

    seven = _format(report, "7z")
    aes = _format(report, "aes_zip")
    assert seven["backend_available"] is False
    assert seven["runtime_supported"] is False
    assert _operations(seven)["detect"] is True
    assert _operations(seven)["extract"] is False
    assert aes["backend_available"] is False
    assert aes["runtime_supported"] is False
    assert _operations(aes)["detect"] is True
    assert _operations(aes)["extract"] is False


def test_archive_report_exposes_rarfile_as_canonical_read_backend() -> None:
    report = archive_capability_report().to_dict()
    known = report["known_but_not_exposed"]
    assert known["tar"]["known"] is True
    assert known["tar"]["python_stdlib_backend"] == "tarfile"
    assert known["tar"]["runtime_archive_service_supported"] is False

    rar = _format(report, "rar")
    assert rar["backend"] == "rarfile.RarFile"
    assert rar["family"] == "RAR3/RAR5"
    rar_ops = _operations(rar)
    assert rar_ops["detect"] is True
    assert rar_ops["create"] is False
    assert rar_ops["inspect"] is rar["backend_available"]
    assert "rarfile>=4.5,<5" in report["dependency_contract"]["core_runtime_requirements"]


def test_archive_report_exposes_existing_fail_closed_security_policy() -> None:
    policy = archive_capability_report().to_dict()["safety_policy"]
    for key in (
        "inspect_before_extract",
        "reject_absolute_paths",
        "reject_parent_traversal",
        "reject_symlinks_by_default",
        "member_count_limit",
        "member_size_limit",
        "total_uncompressed_size_limit",
        "compression_ratio_limit",
        "staging_before_commit",
        "atomic_destination_commit",
    ):
        assert policy[key] is True
    assert policy["password_persistence"] is False


def test_archive_dependency_contract_matches_dependency_studio_registry() -> None:
    report = archive_capability_report().to_dict()
    registry = json.loads(
        (ROOT / "latka_jazn" / "resources" / "dependencies" / "profiles.json").read_text(encoding="utf-8")
    )
    archive_profile = registry["profiles"]["archive"]
    assert "archive" in registry["activation_profiles"]
    assert archive_profile["kind"] == "runtime_required"
    assert archive_profile["requirements"] == report["dependency_contract"]["requirements"]
    assert report["dependency_contract"]["activation_required"] is True


def test_archive_format_lookup_accepts_canonical_aliases() -> None:
    assert archive_format_capability("zip64")["format"] == "zip"  # type: ignore[index]
    assert archive_format_capability("sevenzip")["format"] == "7z"  # type: ignore[index]
    assert archive_format_capability("aes-zip")["format"] == "aes_zip"  # type: ignore[index]
    assert archive_format_capability("rar")["format"] == "rar"  # type: ignore[index]


def test_capability_handler_surfaces_archive_matrix_instead_of_generic_claim() -> None:
    result = CapabilityStatusHandler().handle(
        "Czy umiesz obsługiwać archiwa ZIP, 7z i AES ZIP?",
        {"intent": "capability_status_question"},
    )
    assert result.route == "capability_status"
    assert "ZIP/ZIP64" in result.body
    assert "`py7zr`" in result.body
    assert "`pyzipper`" in result.body
    archive = result.data["archive_capabilities"]
    assert _format(archive, "zip")["runtime_supported"] is True
    assert "archive_capability_matrix" in result.satisfied_components


def test_capability_reality_checker_validates_archive_truth_mapping() -> None:
    report = CapabilityRealityChecker().run().to_dict()
    row = next(item for item in report["checks"] if item["name"] == "archive_capability_truth")
    assert row["status"] == "ok"
    assert "zip=True" in row["evidence"]
