from __future__ import annotations

from pathlib import Path

import latka_jazn.tools.dependency_studio as studio


ROOT = Path(__file__).resolve().parents[1]


def test_repeated_profile_flags_preserve_core_and_archive(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_download_bundle(root, *, profile_names, **kwargs):
        captured["root"] = Path(root)
        captured["profiles"] = list(profile_names)
        return {"ok": True, "command": [], "state": "bundle_downloaded"}

    monkeypatch.setattr(studio, "download_bundle", fake_download_bundle)
    ns = studio.build_parser().parse_args([
        "--root", str(ROOT),
        "download",
        "--profile", "core",
        "--profile", "archive",
        "--dry-run",
    ])
    exit_code, payload = studio.execute(ns)
    assert exit_code == 0
    assert payload["ok"] is True
    assert captured["profiles"] == ["core", "archive"]


def test_comma_profile_form_remains_backward_compatible(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_download_bundle(root, *, profile_names, **kwargs):
        captured["profiles"] = list(profile_names)
        return {"ok": True, "command": [], "state": "bundle_downloaded"}

    monkeypatch.setattr(studio, "download_bundle", fake_download_bundle)
    ns = studio.build_parser().parse_args([
        "--root", str(ROOT),
        "download",
        "--profile", "core,archive",
        "--dry-run",
    ])
    exit_code, _ = studio.execute(ns)
    assert exit_code == 0
    assert captured["profiles"] == ["core", "archive"]
