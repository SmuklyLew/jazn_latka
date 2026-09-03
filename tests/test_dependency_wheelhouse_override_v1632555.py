from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import latka_jazn.dependencies.release_artifact as release_artifact
import latka_jazn.packaging.dependency_package_contract as dependency_contract


def test_materialized_sidecar_honors_explicit_wheelhouse_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "runtime"
    root.mkdir()
    sidecar_name = "deps.zip"
    (root / sidecar_name).write_bytes(b"sidecar")
    target = {
        "alias": "linux-x64",
        "python_version": "3.12",
        "implementation": "cp",
        "abi": "cp312",
        "platform_family": "linux",
        "architecture": "x86_64",
        "libc_family": "glibc",
    }
    dependency_set = {
        "schema_version": "jazn_dependency_set/v1",
        "artifacts": [
            {
                "filename": sidecar_name,
                "bundle_name": "core+archive__linux-x64__py312__fixture",
                "sha256": "a" * 64,
                "target": target,
            }
        ],
    }
    (root / "JAZN_DEPENDENCY_SET.json").write_text(
        json.dumps(dependency_set), encoding="utf-8"
    )
    package_set_path = root / "fixture.package.json"
    package_set_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        release_artifact,
        "_verified_package_set_for_dependency_set",
        lambda _root, _payload: (
            package_set_path,
            {"schema_version": "jazn_package_set/v3"},
            [],
        ),
    )
    monkeypatch.setattr(
        release_artifact,
        "target_spec",
        lambda *_args, **_kwargs: SimpleNamespace(to_dict=lambda: dict(target)),
    )
    captured: dict[str, Path] = {}

    def fake_extract(source, destination, **_kwargs):
        captured["source"] = Path(source)
        captured["destination"] = Path(destination)
        return {"ok": True, "state": "dependency_artifact_materialized"}

    monkeypatch.setattr(dependency_contract, "extract_verified_dependency_sidecar", fake_extract)
    explicit = tmp_path / "operator-wheelhouse"
    monkeypatch.setenv("JAZN_DEPENDENCY_WHEELHOUSE", str(explicit))

    result = release_artifact.materialize_compatible_dependency_artifact(root)

    assert result["ok"] is True
    assert captured["source"] == root / sidecar_name
    assert captured["destination"].parent == explicit.resolve()
