from __future__ import annotations

from latka_jazn.dependencies.release_artifact import _only_declared_dependency_outputs_are_missing


def _dependency_set(filename: str = "deps.zip") -> dict:
    return {
        "schema_version": "jazn_dependency_set/v1",
        "artifacts": [{"filename": filename}],
    }


def test_declared_dependency_sidecar_absence_maps_to_no_compatible_bundle() -> None:
    assert _only_declared_dependency_outputs_are_missing(
        _dependency_set(),
        [{
            "reason": "package_set_verification_failed",
            "errors": ["missing_output:deps.zip"],
        }],
    ) is True


def test_package_set_integrity_errors_are_not_downgraded_to_absence() -> None:
    for error in (
        "sha256_mismatch:deps.zip",
        "size_mismatch:deps.zip",
        "package_set_sha256_mismatch",
        "missing_output:system.zip",
    ):
        assert _only_declared_dependency_outputs_are_missing(
            _dependency_set(),
            [{
                "reason": "package_set_verification_failed",
                "errors": [error],
            }],
        ) is False


def test_projection_or_unreadable_package_set_remains_unverified() -> None:
    assert _only_declared_dependency_outputs_are_missing(
        _dependency_set(),
        [{"reason": "dependency_set_projection_mismatch"}],
    ) is False
    assert _only_declared_dependency_outputs_are_missing(
        _dependency_set(),
        [{"reason": "package_set_unreadable:ValueError:fixture"}],
    ) is False
