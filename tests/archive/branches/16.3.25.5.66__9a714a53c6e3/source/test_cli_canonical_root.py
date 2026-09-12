from __future__ import annotations

from pathlib import Path

from latka_jazn import cli


def test_legacy_flag_route_injects_repository_root(monkeypatch, tmp_path: Path) -> None:
    captured: list[str] = []

    def fake_legacy(args: list[str]) -> int:
        captured.extend(args)
        return 0

    monkeypatch.setattr(cli, "_legacy_main", fake_legacy)
    monkeypatch.chdir(tmp_path)

    assert cli.main(["--chat"]) == 0
    assert captured[:2] == ["--root", str(Path(cli.__file__).resolve().parents[1])]
    assert captured[2:] == ["--chat"]


def test_explicit_legacy_root_is_preserved(monkeypatch, tmp_path: Path) -> None:
    captured: list[str] = []

    def fake_legacy(args: list[str]) -> int:
        captured.extend(args)
        return 0

    monkeypatch.setattr(cli, "_legacy_main", fake_legacy)

    assert cli.main(["--root", str(tmp_path), "--chat"]) == 0
    assert captured == ["--root", str(tmp_path), "--chat"]
