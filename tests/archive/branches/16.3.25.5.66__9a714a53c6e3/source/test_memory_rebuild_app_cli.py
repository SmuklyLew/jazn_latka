from __future__ import annotations

from pathlib import Path
import json
import zipfile

from latka_jazn.tools.memory_rebuild_app.cli import build_parser, main


def test_parser_disables_abbreviations() -> None:
    parser = build_parser()
    assert parser.allow_abbrev is False


def test_create_list_and_inspect_source(tmp_path: Path, capsys) -> None:
    projects = tmp_path / "projects"
    target = tmp_path / "target"
    code = main([
        "--project-root", str(projects),
        "create-project",
        "--name", "Test",
        "--target-root", str(target),
    ])
    assert code == 0
    created = json.loads(capsys.readouterr().out)
    project_id = created["project"]["project_id"]

    archive = tmp_path / "chatgpt-export-2026-07-17.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("conversations.json", "[]")

    code = main([
        "--project-root", str(projects),
        "--project", project_id,
        "add-source",
        str(archive),
        "--approved",
    ])
    assert code == 0
    added = json.loads(capsys.readouterr().out)
    assert added["source"]["role"] == "chatgpt_export"

    code = main(["--project-root", str(projects), "list-projects"])
    assert code == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed[0]["project_id"] == project_id
