from __future__ import annotations

from pathlib import Path


def replace_exact(path: str, old: str, new: str, expected: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    observed = text.count(old)
    if observed != expected:
        raise SystemExit(
            f"{path}: expected {expected} occurrence(s), found {observed}: {old!r}"
        )
    target.write_text(text.replace(old, new), encoding="utf-8")


# Test typing: retain the integer while constructing the fixture.
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

# Test typing: the double must genuinely satisfy DialogBackend.
path = "tests/test_memory_rebuild_v4_protocol_engine.py"
replace_exact(
    path,
    '    dialogs = type("Dialogs", (), {"message": lambda self, *_args: None})()\n',
    '    class SilentDialogs(studio.TextDialogs):\n'
    '        def message(self, title: str, text: str) -> None:\n'
    '            del title, text\n\n'
    '    dialogs = SilentDialogs()\n',
)

# Test typing: remove the duplicate helper declaration, keep the shared Windows-safe helper.
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

# Active legacy compatibility tool: make platform and Prompt Toolkit contracts explicit.
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
    "    if sys.platform == \"win32\":\n"
    "        user32 = ctypes.windll.user32\n"
    "        kernel32 = ctypes.windll.kernel32\n"
    "    else:\n"
    "        raise MemoryRebuildToolError(\"Natywny schowek Windows jest dostępny tylko na Windows.\")\n",
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

# Active v8.9 compatibility source: express intentional dynamic module writes dynamically.
path = "tools/pack_generator_sources/jazn_pack_generator_v89.py"
replace_exact(
    path,
    "    legacy.GENERATOR_VERSION = GENERATOR_VERSION\n    legacy.SETTINGS_SCHEMA = SETTINGS_SCHEMA\n",
    "    setattr(legacy, \"GENERATOR_VERSION\", GENERATOR_VERSION)\n"
    "    setattr(legacy, \"SETTINGS_SCHEMA\", SETTINGS_SCHEMA)\n",
)
replace_exact(
    path,
    "    legacy.build_plan = build_plan\n",
    "    setattr(legacy, \"build_plan\", build_plan)\n",
)
replace_exact(
    path,
    '    manifest_target = manifest.get("target") if isinstance(manifest.get("target"), dict) else {}\n',
    '    raw_target = manifest.get("target")\n'
    '    manifest_target = raw_target if isinstance(raw_target, dict) else {}\n',
)

# Canonical CI now consumes the same project-wide configuration as Pylance/Pyright.
replace_exact(
    ".github/workflows/release-hardening.yml",
    "      - name: Static type audit\n        run: pyright latka_jazn main.py run.py\n",
    "      - name: Static type audit\n        run: pyright --project pyrightconfig.json\n",
)

# This correction is a separate versioned patch after the baseline/config stage.
path = "latka_jazn/version.py"
replace_exact(
    path,
    "# v16.3.25.5.17 establishes one canonical Pyright active-tree contract shared\n"
    "# by local Pylance/Pyright diagnostics and CI, while keeping archive snapshots\n"
    "# outside the active static-analysis boundary.\n"
    'DISTRIBUTION_VERSION = "16.3.25.5.17"\n'
    'PACKAGE_VERSION = "16.3.25.5.17"\n'
    'PACKAGE_RELEASE_NAME = "pylance-pyright-hardening"\n',
    "# v16.3.25.5.18 corrects every classified active-tree Pyright baseline error\n"
    "# without weakening diagnostics, while preserving explicit platform and\n"
    "# compatibility boundaries for the Jaźń runtime and operator tools.\n"
    'DISTRIBUTION_VERSION = "16.3.25.5.18"\n'
    'PACKAGE_VERSION = "16.3.25.5.18"\n'
    'PACKAGE_RELEASE_NAME = "pylance-pyright-active-tree-corrections"\n',
)
