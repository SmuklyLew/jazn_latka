from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import os
import uuid

PROJECT_SCHEMA = "jazn_memory_rebuild_project/v1"

SOURCE_ROLES: tuple[str, ...] = (
    "chatgpt_export",
    "chatgpt_html_export",
    "journal",
    "approved_l0",
    "layered_memory",
    "runtime_event_ledger",
    "sqlite_snapshot",
    "reference_document",
    "visual_asset",
    "unknown",
)

TRUTH_DOMAINS: tuple[str, ...] = (
    "conversation_event",
    "source_recorded",
    "user_confirmed",
    "assistant_claim",
    "runtime_claim",
    "dream",
    "imagination",
    "book_scene",
    "roleplay",
    "symbolic",
    "technical",
    "unknown",
)

PIPELINES: tuple[str, ...] = (
    "memory_rebuild",
    "html_control",
    "catalog_only",
    "sqlite_baseline",
    "excluded",
)

DEFAULT_SETTINGS: dict[str, Any] = {
    "recursive_scan": False,
    "verify_after_each": True,
    "full_validation": True,
    "continue_on_error": False,
    "create_backup": True,
    "audit_classifiers": True,
    "reclassify_journal_dry_run": True,
    "apply_reclassification": False,
    "analyse_topics": False,
    "force_topics": False,
    "candidate_limit": 0,
    "progress_every_conversations": 5,
    "hash_sources_during_scan": True,
    "verify_zip_crc_during_scan": False,
    "preserve_all_chat_branches": True,
    "preserve_exact_source_text": True,
    "automatic_experience_approval": False,
    "automatic_l2": False,
    "automatic_l3": False,
}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def normalized_path(value: str | Path) -> str:
    raw = str(value).strip()
    if not raw:
        return ""
    return str(Path(raw).expanduser().resolve())


def _deduplicated(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = os.path.normcase(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


@dataclass(slots=True)
class SourceSpec:
    source_id: str
    path: str
    role: str = "unknown"
    order: int = 0
    enabled: bool = True
    source_family: str = ""
    truth_domain: str = "unknown"
    pipeline: str = "catalog_only"
    approved: bool = False
    notes: str = ""
    size_bytes: int | None = None
    sha256: str | None = None
    status: str = "uninspected"
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, path: str | Path, **values: Any) -> "SourceSpec":
        return cls(source_id=new_id("src"), path=normalized_path(path), **values).normalized()

    def normalized(self) -> "SourceSpec":
        self.path = normalized_path(self.path)
        self.role = self.role if self.role in SOURCE_ROLES else "unknown"
        self.truth_domain = self.truth_domain if self.truth_domain in TRUTH_DOMAINS else "unknown"
        self.pipeline = self.pipeline if self.pipeline in PIPELINES else "catalog_only"
        self.order = max(0, int(self.order))
        self.enabled = bool(self.enabled)
        self.approved = bool(self.approved)
        self.warnings = _deduplicated(str(item) for item in self.warnings if str(item).strip())
        self.metadata = dict(self.metadata or {})
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceSpec":
        allowed = cls.__dataclass_fields__.keys()
        values = {key: payload[key] for key in allowed if key in payload}
        values.setdefault("source_id", new_id("src"))
        values.setdefault("path", "")
        return cls(**values).normalized()

    def to_dict(self) -> dict[str, Any]:
        self.normalized()
        return asdict(self)


@dataclass(slots=True)
class BaselineSpec:
    baseline_id: str
    path: str
    label: str
    enabled: bool = True
    immutable: bool = True
    added_at_utc: str = field(default_factory=utc_iso)
    status: str = "uninspected"
    summary: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @classmethod
    def create(cls, path: str | Path, label: str | None = None) -> "BaselineSpec":
        resolved = normalized_path(path)
        return cls(
            baseline_id=new_id("base"),
            path=resolved,
            label=(label or Path(resolved).name or "baseline").strip(),
        ).normalized()

    def normalized(self) -> "BaselineSpec":
        self.path = normalized_path(self.path)
        self.label = self.label.strip() or Path(self.path).name or "baseline"
        self.enabled = bool(self.enabled)
        self.immutable = True
        self.summary = dict(self.summary or {})
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BaselineSpec":
        allowed = cls.__dataclass_fields__.keys()
        values = {key: payload[key] for key in allowed if key in payload}
        values.setdefault("baseline_id", new_id("base"))
        values.setdefault("path", "")
        values.setdefault("label", "baseline")
        return cls(**values).normalized()

    def to_dict(self) -> dict[str, Any]:
        self.normalized()
        return asdict(self)


@dataclass(slots=True)
class RebuildProject:
    project_id: str
    name: str
    target_root: str
    mode: str = "developer"
    source_directory: str = ""
    schema_version: str = PROJECT_SCHEMA
    created_at_utc: str = field(default_factory=utc_iso)
    updated_at_utc: str = field(default_factory=utc_iso)
    revision: int = 0
    sources: list[SourceSpec] = field(default_factory=list)
    baselines: list[BaselineSpec] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_SETTINGS))
    last_plan: dict[str, Any] | None = None
    last_run: dict[str, Any] | None = None
    notes: str = ""

    @classmethod
    def create(
        cls,
        name: str,
        target_root: str | Path,
        *,
        source_directory: str | Path = "",
        mode: str = "developer",
    ) -> "RebuildProject":
        return cls(
            project_id=new_id("project"),
            name=name.strip() or "Odbudowa pamięci",
            target_root=normalized_path(target_root),
            source_directory=normalized_path(source_directory) if str(source_directory).strip() else "",
            mode=mode,
        ).normalized()

    def normalized(self) -> "RebuildProject":
        self.name = self.name.strip() or "Odbudowa pamięci"
        self.target_root = normalized_path(self.target_root)
        self.source_directory = normalized_path(self.source_directory) if self.source_directory else ""
        self.mode = self.mode if self.mode in {"developer", "system"} else "developer"
        self.schema_version = PROJECT_SCHEMA
        self.revision = max(0, int(self.revision))
        merged_settings = dict(DEFAULT_SETTINGS)
        merged_settings.update(dict(self.settings or {}))
        merged_settings["automatic_experience_approval"] = False
        merged_settings["automatic_l2"] = False
        merged_settings["automatic_l3"] = False
        self.settings = merged_settings

        sources: list[SourceSpec] = []
        seen_paths: set[str] = set()
        for item in self.sources:
            source = item if isinstance(item, SourceSpec) else SourceSpec.from_dict(dict(item))
            source.normalized()
            key = os.path.normcase(source.path)
            if not source.path or key in seen_paths:
                continue
            seen_paths.add(key)
            sources.append(source)
        sources.sort(key=lambda item: (item.order if item.order > 0 else 10**9, item.path.casefold()))
        for index, source in enumerate(sources, 1):
            source.order = index
        self.sources = sources

        baselines: list[BaselineSpec] = []
        seen_baselines: set[str] = set()
        for item in self.baselines:
            baseline = item if isinstance(item, BaselineSpec) else BaselineSpec.from_dict(dict(item))
            baseline.normalized()
            key = os.path.normcase(baseline.path)
            if not baseline.path or key in seen_baselines:
                continue
            seen_baselines.add(key)
            baselines.append(baseline)
        self.baselines = baselines
        return self

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RebuildProject":
        values = dict(payload)
        values["sources"] = [SourceSpec.from_dict(dict(item)) for item in payload.get("sources", [])]
        values["baselines"] = [BaselineSpec.from_dict(dict(item)) for item in payload.get("baselines", [])]
        allowed = cls.__dataclass_fields__.keys()
        filtered = {key: values[key] for key in allowed if key in values}
        filtered.setdefault("project_id", new_id("project"))
        filtered.setdefault("name", "Odbudowa pamięci")
        filtered.setdefault("target_root", "")
        return cls(**filtered).normalized()

    def to_dict(self) -> dict[str, Any]:
        self.normalized()
        payload = asdict(self)
        payload["sources"] = [item.to_dict() for item in self.sources]
        payload["baselines"] = [item.to_dict() for item in self.baselines]
        return payload

    def touch(self) -> None:
        self.updated_at_utc = utc_iso()
        self.revision += 1

    def source_by_id(self, source_id: str) -> SourceSpec:
        for source in self.sources:
            if source.source_id == source_id:
                return source
        raise KeyError(source_id)

    def baseline_by_id(self, baseline_id: str) -> BaselineSpec:
        for baseline in self.baselines:
            if baseline.baseline_id == baseline_id:
                return baseline
        raise KeyError(baseline_id)

    def add_source(self, source: SourceSpec) -> SourceSpec:
        candidate = source.normalized()
        key = os.path.normcase(candidate.path)
        for existing in self.sources:
            if os.path.normcase(existing.path) == key:
                return existing
        candidate.order = len(self.sources) + 1
        self.sources.append(candidate)
        self.touch()
        return candidate

    def remove_source(self, source_id: str) -> SourceSpec:
        for index, source in enumerate(self.sources):
            if source.source_id == source_id:
                removed = self.sources.pop(index)
                self.normalized()
                self.touch()
                return removed
        raise KeyError(source_id)

    def move_source(self, source_id: str, direction: int) -> None:
        index = next((i for i, item in enumerate(self.sources) if item.source_id == source_id), None)
        if index is None:
            raise KeyError(source_id)
        target = max(0, min(len(self.sources) - 1, index + int(direction)))
        if target == index:
            return
        item = self.sources.pop(index)
        self.sources.insert(target, item)
        for position, source in enumerate(self.sources, 1):
            source.order = position
        self.touch()

    def add_baseline(self, baseline: BaselineSpec) -> BaselineSpec:
        candidate = baseline.normalized()
        key = os.path.normcase(candidate.path)
        for existing in self.baselines:
            if os.path.normcase(existing.path) == key:
                return existing
        self.baselines.append(candidate)
        self.touch()
        return candidate

    def remove_baseline(self, baseline_id: str) -> BaselineSpec:
        for index, baseline in enumerate(self.baselines):
            if baseline.baseline_id == baseline_id:
                removed = self.baselines.pop(index)
                self.touch()
                return removed
        raise KeyError(baseline_id)

    def enabled_sources(self, *, pipeline: str | None = None) -> list[SourceSpec]:
        result = [item for item in self.sources if item.enabled]
        if pipeline is not None:
            result = [item for item in result if item.pipeline == pipeline]
        return sorted(result, key=lambda item: item.order)

    def enabled_baselines(self) -> list[BaselineSpec]:
        return [item for item in self.baselines if item.enabled]


__all__ = [
    "BaselineSpec",
    "DEFAULT_SETTINGS",
    "PIPELINES",
    "PROJECT_SCHEMA",
    "RebuildProject",
    "SOURCE_ROLES",
    "SourceSpec",
    "TRUTH_DOMAINS",
    "new_id",
    "normalized_path",
    "utc_iso",
]
