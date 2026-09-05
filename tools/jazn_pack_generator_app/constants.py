from __future__ import annotations

GENERATOR_VERSION = "10.1.86.0.111"
GENERATOR_TITLE = "Jaźń Pack Generator"
SETTINGS_SCHEMA = "jazn_pack_generator_settings/v1"
PACKAGE_MANIFEST_SCHEMA = "jazn_pack_generator_package/v1"

DEFAULT_PART_SIZE_MIB = 450
DEFAULT_COMPRESSION_LEVEL = 6
DEFAULT_UI_MODE = "studio"

CONTENT_CHOICES = ("system", "memory", "system+memory")
UI_MODE_CHOICES = ("text", "tui", "studio")
TRANSPORT_CHOICES = ("single", "split")

SETTINGS_FILENAME = "jazn_pack_generator_settings.json"

EXCLUDED_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".pytest-tmp", ".mypy_cache", ".ruff_cache", ".codex", ".vscode",
    "workspace_runtime", "logs", "log", "tmp", "temp", "backups", "backups_git",
    "exports", "requests", "responses", "status", "processed",
})

EXCLUDED_FILE_SUFFIXES = (
    ".pyc", ".pyo", ".sqlite-wal", ".sqlite-shm", ".sqlite3-wal", ".sqlite3-shm",
    ".db-wal", ".db-shm", ".tmp", ".temp", ".bak", ".bad", ".corrupt", ".partial",
)

EXCLUDED_FILE_NAMES = frozenset({
    SETTINGS_FILENAME,
    "__jazn_pack_generator_settings.json",
    "__jazn_pack_generator.lock.json",
})

WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
