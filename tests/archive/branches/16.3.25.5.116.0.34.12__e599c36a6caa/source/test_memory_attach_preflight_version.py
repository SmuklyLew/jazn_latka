from __future__ import annotations

from types import SimpleNamespace

from latka_jazn.packaging import memory_package_attach as attach_module


def test_memory_attach_rejects_verified_preflight_without_runtime_version(tmp_path, monkeypatch) -> None:
    preflight = SimpleNamespace(
        structure_ok=True,
        manifest_ok=True,
        provenance_ok=True,
        version=None,
        to_dict=lambda: {
            "structure_ok": True,
            "manifest_ok": True,
            "provenance_ok": True,
            "version": None,
        },
    )
    monkeypatch.setattr(attach_module, "runtime_preflight", lambda _root: preflight)

    result = attach_module.attach_memory_package(tmp_path, parts_dir=tmp_path)

    assert result.ok is False
    assert result.state == "runtime_not_verified"
    assert result.exit_code == 13
    assert result.report["runtime_preflight_version_missing"] is True
