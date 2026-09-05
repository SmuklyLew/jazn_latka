from __future__ import annotations

from pathlib import Path


def replace_exact(path: str, old: str, new: str, *, expected: int = 1) -> None:
    target = Path(path)
    if not target.is_file():
        raise SystemExit(f"{path}: required file is missing")
    text = target.read_text(encoding="utf-8")
    observed = text.count(old)
    if observed == 0 and new in text:
        return
    if observed != expected:
        raise SystemExit(
            f"{path}: expected {expected} occurrence(s), found {observed}: {old!r}"
        )
    target.write_text(text.replace(old, new), encoding="utf-8")


# Preserve the integer type while constructing the wheel fixture.
path = "tests/test_dependency_unpacked_wheel_bootstrap_v1632555.py"
replace_exact(
    path,
    "    files: list[dict[str, object]] = []\n    resolved: list[dict[str, object]] = []\n    for wheel in (packaging_wheel, demo_wheel):\n        metadata = wheel_metadata(wheel)\n        row = {\n            \"filename\": wheel.name,\n            \"size_bytes\": wheel.stat().st_size,",
    "    files: list[dict[str, object]] = []\n    resolved: list[dict[str, object]] = []\n    total_size_bytes = 0\n    for wheel in (packaging_wheel, demo_wheel):\n        metadata = wheel_metadata(wheel)\n        size_bytes = wheel.stat().st_size\n        total_size_bytes += size_bytes\n        row = {\n            \"filename\": wheel.name,\n            \"size_bytes\": size_bytes,",
)
replace_exact(
    path,
    '        "total_size_bytes": sum(int(item["size_bytes"]) for item in files),',
    '        "total_size_bytes": total_size_bytes,',
)

# The test double must genuinely satisfy the production DialogBackend protocol.
path = "tests/test_memory_rebuild_v4_protocol_engine.py"
replace_exact(
    path,
    '    dialogs = type("Dialogs", (), {"message": lambda self, *_args: None})()\n',
    '    class SilentDialogs(studio.TextDialogs):\n'
    '        def message(self, title: str, text: str) -> None:\n'
    '            del title, text\n\n'
    '    dialogs = SilentDialogs()\n',
)

# Keep the shared Windows-safe helper and remove the duplicate declaration.
path = "tests/test_release_metadata_semantics_v163253.py"
replace_exact(
    path,
    '\n\ndef _remove_git_metadata(root: Path) -> None:\n'
    '    def _clear_readonly_and_retry(function, path, _excinfo) -> None:\n'
    '        os.chmod(path, stat.S_IWRITE)\n'
    '        function(path)\n\n'
    '    shutil.rmtree(root / ".git", onexc=_clear_readonly_and_retry)\n',
    '',
)

# Active legacy operator tool: express Windows and Prompt Toolkit contracts explicitly.
path = "tools/memory_rebuild_legacy_v24.py"
replace_exact(
    path,
    "from typing import Any, Callable, Iterable, Sequence\n",
    "from typing import TYPE_CHECKING, Any, Callable, Iterable, Sequence\n\n"
    "if TYPE_CHECKING:\n"
    "    from prompt_toolkit.formatted_text.base import StyleAndTextTuples\n",
)
replace_exact(
    path,
    "    CF_UNICODETEXT = 13\n"
    "    GMEM_MOVEABLE = 0x0002\n"
    "    user32 = ctypes.windll.user32\n"
    "    kernel32 = ctypes.windll.kernel32\n",
    "    CF_UNICODETEXT = 13\n"
    "    GMEM_MOVEABLE = 0x0002\n"
    "    windll = getattr(ctypes, \"windll\", None)\n"
    "    if windll is None:\n"
    "        raise MemoryRebuildToolError(\n"
    "            \"Natywny schowek Windows jest dostępny tylko na Windows.\"\n"
    "        )\n"
    "    user32 = windll.user32\n"
    "    kernel32 = windll.kernel32\n",
)
replace_exact(
    path,
    "def render_detail() -> list[tuple[str, str]]:",
    "def render_detail() -> StyleAndTextTuples:",
    expected=2,
)
replace_exact(
    path,
    "def render_footer() -> list[tuple[str, str]]:",
    "def render_footer() -> StyleAndTextTuples:",
)
replace_exact(
    path,
    "def render() -> list[tuple[str, str]]:",
    "def render() -> StyleAndTextTuples:",
)
replace_exact(
    path,
    "out: list[tuple[str, str]] =",
    "out: StyleAndTextTuples =",
    expected=2,
)
replace_exact(
    path,
    "fragments: list[tuple[str, str]] =",
    "fragments: StyleAndTextTuples =",
)
replace_exact(
    path,
    '        out = [\n            ("class:panel.title", "  WYBRANE ŹRÓDŁO\\n"),',
    '        out: StyleAndTextTuples = [\n            ("class:panel.title", "  WYBRANE ŹRÓDŁO\\n"),',
)

# Canonical release CI must consume the same active-tree Pyright contract.
replace_exact(
    ".github/workflows/release-hardening.yml",
    "      - name: Static type audit\n        run: pyright latka_jazn main.py run.py\n",
    "      - name: Static type audit\n        run: pyright --project pyrightconfig.json\n",
)

# This correction is a versioned patch on top of Pack Generator 10.1.86.0.
path = "latka_jazn/version.py"
replace_exact(
    path,
    "# v16.3.25.5.18 hardens Pack Generator 10.1.86.0 release automation so newly\n"
    "# materialized cross-target dependency locks are staged and committed before\n"
    "# canonical release-metadata synchronization requires a clean working tree.\n"
    'DISTRIBUTION_VERSION = "16.3.25.5.18"\n'
    'PACKAGE_VERSION = "16.3.25.5.18"\n'
    'PACKAGE_RELEASE_NAME = "pack-generator-lock-persistence-hardening"\n',
    "# v16.3.25.5.19 integrates Pack Generator 10.1.86.0 with the canonical\n"
    "# active-tree Pyright contract and resolves the remaining classified typing\n"
    "# errors without weakening diagnostics or runtime behavior.\n"
    'DISTRIBUTION_VERSION = "16.3.25.5.19"\n'
    'PACKAGE_VERSION = "16.3.25.5.19"\n'
    'PACKAGE_RELEASE_NAME = "package-generator-v10.1.86.0-pyright-hardening"\n',
)
