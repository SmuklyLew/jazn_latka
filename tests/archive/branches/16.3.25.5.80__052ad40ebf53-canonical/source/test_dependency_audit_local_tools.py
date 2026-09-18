from __future__ import annotations

from pathlib import Path

from latka_jazn.dependencies.audit import scan_external_imports


def _write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_tool_sibling_package_is_local_but_external_import_remains(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root / "tools" / "jazn_pack_generator_app" / "__init__.py")
    _write(
        root / "tools" / "jazn_pack_generator.py",
        "import jazn_pack_generator_app\nimport fictional_external_dependency\n",
    )

    report = scan_external_imports(root)

    assert "jazn_pack_generator_app" not in report["imports"]
    assert report["imports"]["fictional_external_dependency"] == [
        "tools/jazn_pack_generator.py"
    ]


def test_tool_sibling_module_is_local_for_tool_scripts(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root / "tools" / "helper.py")
    _write(root / "tools" / "runner.py", "import helper\n")

    report = scan_external_imports(root)

    assert "helper" not in report["imports"]


def test_retired_pack_generator_sources_are_not_active_audit_inputs(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(
        root / "tools" / "pack_generator_sources" / "archive" / "v-old" / "legacy.py",
        "import retired_only_dependency\n",
    )
    _write(
        root / "latka_jazn" / "archive" / "service.py",
        "import active_archive_dependency\n",
    )

    report = scan_external_imports(root)

    assert "retired_only_dependency" not in report["imports"]
    assert report["imports"]["active_archive_dependency"] == [
        "latka_jazn/archive/service.py"
    ]
