from __future__ import annotations

"""Validated, persistent settings for Memory Rebuild and its Studio UI."""

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping
import json
import os

from latka_jazn.core.runtime_root import RuntimeRootNotFoundError, find_runtime_root
from latka_jazn.tools.application_shell.operator_paths import (
    legacy_read_path, operator_file, validate_operator_path,
)

SETTINGS_SCHEMA = "jazn_memory_rebuild_settings/v1"
DEFAULT_SETTINGS_FILENAME = "memory_rebuild_settings.json"
DEFAULT_STUDIO_THEME = "latka-terminal"

RUNTIME_EDITABLE_FIELDS = (
    "retrieval_limit",
    "min_lexical_score",
    "embeddings_enabled",
    "embedding_model",
)
RUNTIME_LOCKED_FIELDS = (
    "require_fts5",
    "require_provenance",
    "automatic_l2",
    "automatic_l3",
    "automatic_activation",
)


@dataclass(frozen=True, slots=True)
class MemoryRebuildSettings:
    require_fts5: bool = True
    embeddings_enabled: bool = False
    embedding_model: str | None = None
    retrieval_limit: int = 20
    min_lexical_score: float = 0.0
    require_provenance: bool = True
    automatic_l2: bool = False
    automatic_l3: bool = False
    automatic_activation: bool = False

    def __post_init__(self) -> None:
        if not self.require_fts5:
            raise ValueError("FTS5 jest obowiązkowym baseline i nie może zostać wyłączone.")
        if not self.require_provenance:
            raise ValueError("Proweniencja jest obowiązkowa i nie może zostać wyłączona.")
        if isinstance(self.retrieval_limit, bool) or not isinstance(self.retrieval_limit, int):
            raise ValueError("retrieval_limit musi być liczbą całkowitą")
        if self.retrieval_limit < 1 or self.retrieval_limit > 500:
            raise ValueError("retrieval_limit musi mieścić się w zakresie 1..500")
        if isinstance(self.min_lexical_score, bool) or not isinstance(self.min_lexical_score, (int, float)):
            raise ValueError("min_lexical_score musi być liczbą")
        if not 0.0 <= float(self.min_lexical_score) <= 1.0:
            raise ValueError("min_lexical_score musi mieścić się w zakresie 0..1")
        model = (self.embedding_model or "").strip()
        if self.embeddings_enabled and not model:
            raise ValueError("Włączone embeddingi wymagają jawnie wskazanego modelu.")
        if self.embedding_model is not None and not model:
            object.__setattr__(self, "embedding_model", None)
        elif self.embedding_model is not None and model != self.embedding_model:
            object.__setattr__(self, "embedding_model", model)
        if self.automatic_l2 or self.automatic_l3 or self.automatic_activation:
            raise ValueError("Memory Rebuild nie zezwala na automatyczne L2, L3 ani aktywację.")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MemoryRebuildSettings":
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"Nieznane ustawienia Memory Rebuild: {', '.join(unknown)}")
        return cls(**{key: value[key] for key in allowed if key in value})

    def with_overrides(self, **changes: Any) -> "MemoryRebuildSettings":
        unknown = sorted(set(changes) - set(self.__dataclass_fields__))
        if unknown:
            raise ValueError(f"Nieznane ustawienia Memory Rebuild: {', '.join(unknown)}")
        locked = sorted(set(changes) & set(RUNTIME_LOCKED_FIELDS))
        for key in locked:
            if changes[key] != getattr(self, key):
                raise ValueError(f"{key} jest ustawieniem bezpieczeństwa tylko do odczytu.")
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MemoryRebuildStudioPreferences:
    theme_name: str = DEFAULT_STUDIO_THEME

    def __post_init__(self) -> None:
        value = str(self.theme_name or "").strip()
        if not value:
            raise ValueError("theme_name nie może być puste.")
        if value != self.theme_name:
            object.__setattr__(self, "theme_name", value)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MemoryRebuildStudioPreferences":
        allowed = set(cls.__dataclass_fields__)
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"Nieznane ustawienia Studio: {', '.join(unknown)}")
        return cls(**{key: value[key] for key in allowed if key in value})


@dataclass(frozen=True, slots=True)
class MemoryRebuildToolSettings:
    runtime: MemoryRebuildSettings = field(default_factory=MemoryRebuildSettings)
    studio: MemoryRebuildStudioPreferences = field(default_factory=MemoryRebuildStudioPreferences)
    schema_version: str = SETTINGS_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != SETTINGS_SCHEMA:
            raise ValueError(
                f"Nieobsługiwany schema_version ustawień: {self.schema_version!r}; "
                f"oczekiwano {SETTINGS_SCHEMA!r}"
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MemoryRebuildToolSettings":
        allowed = {"schema_version", "runtime", "studio"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"Nieznane sekcje ustawień Memory Rebuild: {', '.join(unknown)}")
        runtime_raw = value.get("runtime", {})
        studio_raw = value.get("studio", {})
        if not isinstance(runtime_raw, Mapping):
            raise ValueError("Sekcja runtime musi być obiektem JSON.")
        if not isinstance(studio_raw, Mapping):
            raise ValueError("Sekcja studio musi być obiektem JSON.")
        return cls(
            runtime=MemoryRebuildSettings.from_mapping(dict(runtime_raw)),
            studio=MemoryRebuildStudioPreferences.from_mapping(dict(studio_raw)),
            schema_version=str(value.get("schema_version") or SETTINGS_SCHEMA),
        )

    def with_runtime(self, runtime: MemoryRebuildSettings) -> "MemoryRebuildToolSettings":
        return replace(self, runtime=runtime)

    def with_studio(self, studio: MemoryRebuildStudioPreferences) -> "MemoryRebuildToolSettings":
        return replace(self, studio=studio)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "runtime": self.runtime.to_dict(),
            "studio": asdict(self.studio),
        }


def _settings_system_root(tool_root: str | Path | None) -> Path:
    try:
        return find_runtime_root(Path(tool_root) if tool_root is not None else Path.cwd())
    except RuntimeRootNotFoundError:
        return Path(__file__).resolve().parents[3]


def _validate_settings_destination(path: str | Path, system_root: Path) -> Path:
    """Protect both the selected deployment and the code supplying this module."""
    candidate = Path(path).expanduser()
    for root in {system_root, Path(__file__).resolve().parents[3]}:
        validate_operator_path(candidate, root, allow_memory_settings=True)
        validate_operator_path(candidate.with_name(candidate.name + ".tmp"), root, allow_memory_settings=True)
    return candidate.resolve()


def resolve_settings_path(
    path: str | Path | None = None,
    *,
    tool_root: str | Path | None = None,
) -> Path:
    """Resolve writable settings independently of the tool or working directory."""
    system_root = _settings_system_root(tool_root)
    configured = str(path or "").strip() or os.environ.get("JAZN_MEMORY_REBUILD_SETTINGS", "").strip()
    if configured:
        return _validate_settings_destination(configured, system_root)

    workspace = os.environ.get("JAZN_RUNTIME_WORKSPACE_DIR", "").strip()
    if workspace:
        return _validate_settings_destination(
            Path(workspace).expanduser() / DEFAULT_SETTINGS_FILENAME, system_root,
        )

    return _validate_settings_destination(
        operator_file("memory_rebuild", system_root, DEFAULT_SETTINGS_FILENAME), system_root,
    )


def _read_mapping(source: Path) -> dict[str, Any]:
    value = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Plik ustawień Memory Rebuild musi zawierać obiekt JSON.")
    return value


def _decode_tool_settings(value: Mapping[str, Any]) -> tuple[MemoryRebuildToolSettings, bool]:
    """Return settings and whether the input used the legacy flat runtime schema."""
    if any(key in value for key in ("schema_version", "runtime", "studio")):
        return MemoryRebuildToolSettings.from_mapping(value), False
    return MemoryRebuildToolSettings(runtime=MemoryRebuildSettings.from_mapping(value)), True


def save_tool_settings(
    settings: MemoryRebuildToolSettings,
    path: str | Path | None = None,
    *,
    tool_root: str | Path | None = None,
) -> Path:
    destination = resolve_settings_path(path, tool_root=tool_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(settings.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def load_tool_settings(
    path: str | Path | None = None,
    *,
    tool_root: str | Path | None = None,
    create: bool = False,
) -> MemoryRebuildToolSettings:
    source = resolve_settings_path(path, tool_root=tool_root)
    destination = source
    if source == resolve_settings_path(tool_root=tool_root):
        legacy = Path(tool_root or Path.cwd()).expanduser().resolve() / DEFAULT_SETTINGS_FILENAME
        source = legacy_read_path(destination, legacy)
    if not source.is_file():
        settings = MemoryRebuildToolSettings()
        if create:
            save_tool_settings(settings, destination, tool_root=tool_root)
        return settings
    settings, legacy = _decode_tool_settings(_read_mapping(source))
    if create and legacy and source == destination:
        save_tool_settings(settings, destination, tool_root=tool_root)
    return settings


def load_settings(
    path: str | Path | None = None,
    *,
    tool_root: str | Path | None = None,
) -> MemoryRebuildSettings:
    """Backward-compatible runtime-settings loader for CLI/API consumers."""
    return load_tool_settings(path, tool_root=tool_root, create=False).runtime


__all__ = [
    "DEFAULT_SETTINGS_FILENAME",
    "DEFAULT_STUDIO_THEME",
    "MemoryRebuildSettings",
    "MemoryRebuildStudioPreferences",
    "MemoryRebuildToolSettings",
    "RUNTIME_EDITABLE_FIELDS",
    "RUNTIME_LOCKED_FIELDS",
    "SETTINGS_SCHEMA",
    "load_settings",
    "load_tool_settings",
    "resolve_settings_path",
    "save_tool_settings",
]
