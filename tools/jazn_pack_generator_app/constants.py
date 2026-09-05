from __future__ import annotations

GENERATOR_VERSION = "10.1.86.0.113"
GENERATOR_TITLE = "Jaźń Pack Generator"
SETTINGS_SCHEMA = "jazn_pack_generator_settings/v1"
PACKAGE_MANIFEST_SCHEMA = "jazn_pack_generator_package/v2"

DEFAULT_PART_SIZE_MIB = 450
DEFAULT_COMPRESSION_LEVEL = 6
DEFAULT_UI_MODE = "studio"

CONTENT_CHOICES = ("system", "memory", "system+memory")
UI_MODE_CHOICES = ("text", "tui", "studio")
TRANSPORT_CHOICES = ("single", "split")

SETTINGS_FILENAME = "jazn_pack_generator_settings.json"

EXCLUDED_DIR_NAMES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".pytest-tmp", ".mypy_cache", ".ruff_cache", ".codex", ".vscode", ".archives",
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
    "memory_rebuild_settings.json",
})

EXCLUDED_SECRET_FILE_NAMES = frozenset({
    ".env",
    "credentials.json",
    "client_secret.json",
    "service_account.json",
    "id_rsa",
    "id_ed25519",
})

EXCLUDED_SECRET_NAME_TOKENS = (
    "private_key",
    "client_secret",
    "service_account_key",
)

WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
