"""Minimal, read-only operator configuration for a Jaźń process.

Public defaults are versioned in config/jazn.toml; optional local credentials
live in config/jazn.secrets.env, which is never a release/source artifact.
Configuration is loaded once by main.py before dependency/runtime imports.
"""

from __future__ import annotations

from collections.abc import MutableMapping
import os
from pathlib import Path
import re
import stat
import tomllib


class OperatorConfigError(ValueError):
    """Fail closed, without rendering secret values."""


DEFAULT_FILE = Path("config/jazn.toml")
SECRET_FILE = Path("config/jazn.secrets.env")
_MAX_CONFIG_BYTES = 32 * 1024
_MAX_SECRET_BYTES = 64 * 1024
_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
_DEFAULT_KEYS = frozenset({
    "JAZN_LLM_ROUTE",
    "JAZN_MEMORY_MODE",
    "JAZN_MEMORY_READINESS_POLICY",
    "JAZN_OLLAMA_BASE_URL",
    "JAZN_ALLOW_PAID_OPENAI",
})
_ENUMS = {
    "JAZN_LLM_ROUTE": frozenset({"auto", "local", "chatgpt_bridge", "openai_api", "none"}),
    "JAZN_MEMORY_MODE": frozenset({"optional", "required", "off"}),
    "JAZN_MEMORY_READINESS_POLICY": frozenset({"searchable", "native_unified_required"}),
    "JAZN_ALLOW_PAID_OPENAI": frozenset({"0", "1"}),
}
_SECRET_KEYS = frozenset({
    "OPENAI_API_KEY",
    "GITHUB_CLIENT_SECRET",
    "JAZN_SIWC_ACCESS_TOKEN",
    "JAZN_MCP_OAUTH_CLIENT_SECRET",
    "JAZN_INTROSPECTION_CLIENT_SECRET",
    "JAZN_MCP_PROBE_TOKEN",
    "JAZN_MEMORY_CLOUD_TOKEN",
    "JAZN_MEMORY_WRITER_LEASE_TOKEN",
})
_SECRET_SUFFIXES = ("_TOKEN", "_SECRET", "_PASSWORD", "_API_KEY")


def _is_secret_key(key: str) -> bool:
    return key in _SECRET_KEYS or (
        key.startswith("JAZN_") and key.endswith(_SECRET_SUFFIXES)
    )


def _read_limited(path: Path, limit: int, *, secret: bool) -> bytes | None:
    if not path.exists() and not path.is_symlink():
        return None
    # An operator cannot redirect secret reads through a symlink.
    if path.is_symlink() or (secret and path.parent.is_symlink()):
        raise OperatorConfigError("Niebezpieczny link w pliku konfiguracji")
    if not path.is_file():
        raise OperatorConfigError("Konfiguracja nie jest zwykłym plikiem")
    if path.stat().st_size > limit:
        raise OperatorConfigError("Plik konfiguracji przekracza limit rozmiaru")
    if secret and os.name != "nt" and path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise OperatorConfigError("Plik sekretów wymaga uprawnień 0600")
    # A bounded read handles growth between stat and open.
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise OperatorConfigError("Plik konfiguracji przekracza limit rozmiaru")
    return content


def _load_defaults(path: Path) -> dict[str, str]:
    raw = _read_limited(path, _MAX_CONFIG_BYTES, secret=False)
    if raw is None:
        return {}
    try:
        document = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise OperatorConfigError("Nieprawidłowy publiczny TOML") from exc
    if set(document) != {"schema_version", "environment"} or document["schema_version"] != 1:
        raise OperatorConfigError("Nieprawidłowy schemat konfiguracji")
    values = document["environment"]
    if not isinstance(values, dict):
        raise OperatorConfigError("Sekcja environment musi być mapą")
    if unknown := set(values) - _DEFAULT_KEYS:
        raise OperatorConfigError("Niedozwolone klucze publicznej konfiguracji: " + ", ".join(sorted(unknown)))
    for key, value in values.items():
        if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
            raise OperatorConfigError(f"Nieprawidłowa wartość ustawienia {key}")
        if key in _ENUMS and value not in _ENUMS[key]:
            raise OperatorConfigError(f"Niedozwolona wartość ustawienia {key}")
        if key == "JAZN_OLLAMA_BASE_URL" and not (
            value.startswith("http://127.0.0.1:") or value.startswith("http://localhost:")
        ):
            raise OperatorConfigError("Domyślny endpoint Ollama musi być lokalny")
    return values


def _load_secrets(path: Path) -> dict[str, str]:
    raw = _read_limited(path, _MAX_SECRET_BYTES, secret=True)
    if raw is None:
        return {}
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise OperatorConfigError("Nieprawidłowe kodowanie pliku sekretów") from exc
    values: dict[str, str] = {}
    for number, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not _KEY.fullmatch(key) or not _is_secret_key(key):
            raise OperatorConfigError(f"Niedozwolona nazwa sekretu w linii {number}")
        if key in values or not value:
            raise OperatorConfigError(f"Nieprawidłowy lub powielony sekret w linii {number}")
        # No shell, interpolation, eval, or escape processing; literal KEY=VALUE only.
        values[key] = value
    return values


def load_operator_configuration(
    root: str | Path, *, environ: MutableMapping[str, str] | None = None
) -> dict[str, object]:
    """Load tracked policy and ignored secrets, preserving explicit environment overrides.

    Transactional validation: no environment mutation if either file is invalid.
    Return names and counts only; never values or credentials.
    """
    base = Path(root).absolute()
    defaults = _load_defaults(base / DEFAULT_FILE)
    secrets = _load_secrets(base / SECRET_FILE)
    dest = os.environ if environ is None else environ
    installed_defaults: list[str] = []
    installed_secrets: list[str] = []
    for key, value in defaults.items():
        if key not in dest:
            dest[key] = value
            installed_defaults.append(key)
    for key, value in secrets.items():
        if key not in dest:
            dest[key] = value
            installed_secrets.append(key)
    return {
        "defaults_file_present": (base / DEFAULT_FILE).is_file(),
        "secrets_file_present": (base / SECRET_FILE).is_file(),
        "default_keys_applied": sorted(installed_defaults),
        "secret_count_applied": len(installed_secrets),
    }
