from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"expected text not found in {path}: {old!r}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def replace_title(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = "Jaźń - Studio testów"
    new = "Jaźń - Studio Testów"
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf-8")


replace(
    ROOT / "tools" / "jazn_tests_studio.py",
    "from typing import Any, Callable\n",
    "from typing import Any, Callable, Literal\n",
)
replace(
    ROOT / "tools" / "jazn_tests_studio.py",
    'APP_NAME = "Jaźń - Studio testów"',
    'APP_NAME = "Jaźń - Studio Testów"',
)
replace(
    ROOT / "tools" / "jazn_tests_studio.py",
    'def text_with_scrollbars(parent, *, wrap: str = "none"):',
    'def text_with_scrollbars(parent, *, wrap: Literal["none", "char", "word"] = "none"): ',
)
replace(
    ROOT / "tools" / "jazn_tests_studio" / "migrate_stable_test_contracts.py",
    'def add_node(node: ast.AST, prefix: str = "") -> None:',
    'def add_node(node: ast.FunctionDef | ast.AsyncFunctionDef, prefix: str = "") -> None:',
)
for relative in (
    "tools/jazn_tests_studio/README.md",
    "tools/jazn_tests_studio/__init__.py",
    "tools/jazn_tests_studio/settings.json",
    "tools/jazn_tests_studio/migrate_stable_test_contracts.py",
):
    replace_title(ROOT / relative)
replace(
    ROOT / ".github" / "workflows" / "persistent-runtime-e2e.yml",
    "run: python -X utf8 -m compileall -q latka_jazn tests main.py run.py",
    "run: python -X utf8 -m compileall -q -x 'tests/archive/' latka_jazn tests main.py run.py",
)
