from __future__ import annotations

from pathlib import Path
import importlib
import zipfile
import pytest

def generator():
    return importlib.import_module("tools.jazn_pack_generator")

def test_v101860111_exposes_three_real_ui_modes() -> None:
    module = generator()
    assert module.GENERATOR_VERSION == "10.1.86.0.111"
    assert module.UI_MODE_CHOICES == ("text", "tui", "studio")
    assert callable(module.run_text_ui)
    assert callable(module.run_terminal_tui)
    assert callable(module.run_studio_ui)

def test_v101860111_rejects_windows_reserved_member_name() -> None:
    from tools.jazn_pack_generator_app.archive import validate_archive_member_name
    with pytest.raises(Exception, match="zarezerwowana"):
        validate_archive_member_name("docs/CON.txt")

def test_v101860111_standard_zip_uses_deflate_and_unicode_names(tmp_path: Path) -> None:
    module = generator()
    root = tmp_path / "root"
    (root / "latka_jazn").mkdir(parents=True)
    (root / "latka_jazn/version.py").write_text(
        'PACKAGE_VERSION = "1.2.3"\nPACKAGE_RELEASE_NAME = "test"\n', encoding="utf-8"
    )
    (root / "run.py").write_text("pass\n", encoding="utf-8")
    (root / "zażółć.txt").write_text("gęślą jaźń", encoding="utf-8")
    out = tmp_path / "out"
    result = module.run_pack_request(source=root, out_dir=out, content="system")
    archive = Path(result["logical_archive"])
    with zipfile.ZipFile(archive, "r") as handle:
        info = handle.getinfo("zażółć.txt")
        assert info.compress_type == zipfile.ZIP_DEFLATED
        assert handle.testzip() is None
