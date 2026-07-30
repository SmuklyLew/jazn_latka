from __future__ import annotations

from pathlib import Path
import json

from latka_jazn.tools.memory_rebuild_app.cli import APP_VERSION, build_parser, main
from latka_jazn.tools.memory_rebuild_app.unified_memory import CANONICAL_DATABASE_NAME


def test_parser_exposes_v24_commands() -> None:
    parser = build_parser()
    parsed = parser.parse_args(["unified-init", "--database", "memory_jazn.sqlite3"])
    assert parsed.command == "unified-init"
    parsed = parser.parse_args(["test-profile", "--database", "memory_jazn.sqlite3", "--profile", "final"])
    assert parsed.profile == "final"
    assert APP_VERSION == "2.4.0"


def test_cli_initializes_and_validates_single_database(tmp_path: Path, capsys) -> None:
    database = tmp_path / CANONICAL_DATABASE_NAME
    assert main(["unified-init", "--database", str(database)]) == 0
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["ok"]
    assert database.is_file()

    assert main(["unified-validate", "--database", str(database), "--quick"]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["ok"]
    assert validation["single_physical_database"] is True


def test_cli_does_not_abbreviate_commands_or_options() -> None:
    parser = build_parser()
    try:
        parser.parse_args(["unified-init", "--data", "x.sqlite3"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("argument abbreviation must remain disabled")
