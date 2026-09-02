from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence
import fnmatch
import hashlib
import json

from latka_jazn.packaging.package_profiles import PackageProfile, load_package_profiles
from latka_jazn.tools.safe_paths import (
    UnsafeRelativePathError,
    resolve_safe_source,
    validate_safe_path_set,
    validate_safe_relative_path,
)

PACKAGE_INTEGRITY_MANIFEST = "PACKAGE_INTEGRITY_MANIFEST.json"
SOURCE_PROVENANCE = "SOURCE_PROVENANCE.json"
MEMORY_PACKAGE_MANIFEST = "memory/MEMORY_PACKAGE_MANIFEST.json"
PRIVATE_CANON_EXACT = "latka_jazn/core/canon/local_private_canon_extension.py"

_GLOBAL_BLOCKED_PARTS = frozenset({
    ".git", ".hg", ".svn", ".codex", ".venv", "venv", ".archives",
    "__pycache__", ".pytest_cache", ".pytest-tmp", ".mypy_cache", ".ruff_cache",
    ".tox", ".nox", "workspace_runtime", "exports", "backups", "backups_git",
    "requests", "responses", "processed", "status", "checkpoints", "logs", "log",
})
_GLOBAL_BLOCKED_SUFFIXES = (
    ".zip", ".7z", ".rar", ".tar", ".tar.gz", ".tgz", ".bz2", ".xz",
    ".pyc", ".pyo", ".tmp", ".temp", ".bak", ".log", ".before.py",
    ".sqlite3-wal", ".sqlite3-shm", ".sqlite-wal", ".sqlite-shm", "-wal", "-shm",
)
_DATABASE_SUFFIXES = (".sqlite", ".sqlite3", ".db")
_SECRET_EXACT = frozenset({
    ".env", "id_rsa", "id_ed25519", "credentials", "credentials.json",
    "secrets.json", "secret.json",
})
_SECRET_TOKENS = ("private_key", "credentials", "client_secret", "access_token", "refresh_token")
_LOCAL_DEPENDENCY_PREFIXES = (
    "latka_jazn/local_resources/python/environments/",
    "latka_jazn/local_resources/python/wheelhouse/",
)


class PackagePlanError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PackagePlanEntry:
    path: str
    source: Path
    size_bytes: int
    sha256: str
    classification: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "classification": self.classification,
        }


@dataclass(frozen=True, slots=True)
class PackagePlan:
    root: Path
    profile: str
    entries: tuple[PackagePlanEntry, ...]
    excluded: tuple[tuple[str, str], ...]
    source_mode: str

    @property
    def file_count(self) -> int:
        return len(self.entries)

    @property
    def total_size_bytes(self) -> int:
        return sum(item.size_bytes for item in self.entries)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(item.path for item in self.entries)

    def plan_sha256(self) -> str:
        payload = {
            "profile": self.profile,
            "entries": [item.to_dict() for item in self.entries],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "source_mode": self.source_mode,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "plan_sha256": self.plan_sha256(),
            "entries": [item.to_dict() for item in self.entries],
            "excluded": [{"path": p, "reason": r} for p, r in self.excluded],
        }


def _profile_alias(profile: str) -> str:
    value = str(profile or "").strip().lower().replace("-", "_")
    aliases = {"source_safe": "github_source_safe", "full": "combined"}
    return aliases.get(value, value)


def package_safety_reason(relative: str, profile: str = "system") -> str | None:
    try:
        rel = validate_safe_relative_path(str(relative))
    except UnsafeRelativePathError as exc:
        return f"unsafe_path:{exc}"
    normalized_profile = _profile_alias(profile)
    parts = [part.casefold() for part in PurePosixPath(rel).parts]
    name = parts[-1]
    if any(part in _GLOBAL_BLOCKED_PARTS for part in parts):
        return "immutable_repository_runtime_or_cache_directory"
    if rel == PRIVATE_CANON_EXACT:
        return "known_private_generated_source"
    if any(rel.startswith(prefix) for prefix in _LOCAL_DEPENDENCY_PREFIXES):
        return "local_dependency_environment_or_wheelhouse"
    if name in _SECRET_EXACT or (name.startswith(".env.") and name != ".env.example"):
        return "secret_file"
    if any(token in name for token in _SECRET_TOKENS):
        return "secret_name"
    if ".zip." in name or any(name.endswith(suffix) for suffix in _GLOBAL_BLOCKED_SUFFIXES):
        return "nested_archive_backup_or_transient_file"
    if rel == PACKAGE_INTEGRITY_MANIFEST:
        return "generated_integrity_manifest_replaces_source"
    if normalized_profile == "memory":
        if not rel.startswith("memory/"):
            return "outside_memory_profile"
        if rel == MEMORY_PACKAGE_MANIFEST:
            return "generated_memory_manifest_replaces_source"
        return None
    if normalized_profile in {"system", "github_source_safe", "nlp"}:
        if rel.startswith("memory/"):
            return "memory_forbidden_in_system"
        if name.endswith(_DATABASE_SUFFIXES):
            return "database_forbidden_in_system"
    return None


def _match(pattern: str, relative: str) -> bool:
    pattern = str(pattern).replace("\\", "/").strip().lstrip("/")
    if not pattern:
        return False
    name = PurePosixPath(relative).name
    if fnmatch.fnmatchcase(relative, pattern) or fnmatch.fnmatchcase(name, pattern):
        return True
    if pattern.endswith("/"):
        folder = pattern.rstrip("/")
        return relative == folder or relative.startswith(folder + "/")
    return False


def _profile_rule(root: Path, profile: str) -> PackageProfile | None:
    normalized = _profile_alias(profile)
    if normalized in {"combined", "dual"}:
        return None
    try:
        return load_package_profiles(root).get(normalized)
    except Exception:
        return None


def _included_by_profile(root: Path, relative: str, profile: str) -> bool:
    normalized = _profile_alias(profile)
    if normalized == "memory":
        return relative.startswith("memory/")
    rule = _profile_rule(root, normalized)
    if rule is None:
        # Compatibility fallback for portable generator operating on an older tree.
        if normalized == "system":
            return (
                relative in {"run.py", "main.py", "AGENTS.md", "AGENTS.codex.md", "AGENTS.chatgpt.md", "AGENTS.ollama.md", "README.md", "SOURCE_PROVENANCE.json", "pyproject.toml", "requirements.txt", ".gitignore", ".gitattributes"}
                or relative.startswith(("latka_jazn/", "tests/", ".github/"))
            )
        if normalized == "github_source_safe":
            return _included_by_profile(root, relative, "system")
        if normalized == "nlp":
            return relative.startswith(("latka_jazn/nlp/", "latka_jazn/nlp_reasoning/", "latka_jazn/resources/"))
        return False
    included = any(_match(pattern, relative) for pattern in rule.includes)
    excluded = any(_match(pattern, relative) for pattern in rule.excludes)
    return bool(included and not excluded)


def select_candidate_paths(
    root: Path,
    candidates: Iterable[str],
    *,
    profile: str,
    base_excludes: Iterable[str] = (),
    custom_excludes: Iterable[str] = (),
    manual_excludes_enabled: bool = True,
) -> tuple[list[str], list[tuple[str, str]]]:
    root = Path(root).resolve()
    normalized_profile = _profile_alias(profile)
    selected: list[str] = []
    excluded: list[tuple[str, str]] = []
    for raw in candidates:
        try:
            relative = validate_safe_relative_path(str(raw))
        except UnsafeRelativePathError as exc:
            excluded.append((str(raw), f"unsafe_path:{exc}"))
            continue
        if not _included_by_profile(root, relative, normalized_profile):
            excluded.append((relative, "outside_profile_allowlist"))
            continue
        base = next((p for p in base_excludes if _match(str(p), relative)), None)
        if base is not None:
            excluded.append((relative, f"base:{base}"))
            continue
        if manual_excludes_enabled:
            manual = next((p for p in custom_excludes if _match(str(p), relative)), None)
            if manual is not None:
                excluded.append((relative, f"manual:{manual}"))
                continue
        reason = package_safety_reason(relative, normalized_profile)
        if reason:
            excluded.append((relative, reason))
            continue
        selected.append(relative)
    selected = sorted(set(selected))
    validate_safe_path_set(selected)
    return selected, sorted(set(excluded))


def discover_filesystem_candidates(root: Path) -> list[str]:
    root = Path(root).resolve()
    values: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            values.append(validate_safe_relative_path(path.relative_to(root).as_posix()))
        except UnsafeRelativePathError:
            continue
    return sorted(set(values))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PackagePlanBuilder:
    def __init__(
        self,
        root: Path | str,
        profile: str,
        *,
        candidate_paths: Sequence[str] | None = None,
        source_mode: str = "filesystem",
        base_excludes: Sequence[str] = (),
        custom_excludes: Sequence[str] = (),
        manual_excludes_enabled: bool = True,
    ) -> None:
        self.root = Path(root).resolve()
        self.profile = _profile_alias(profile)
        self.candidate_paths = list(candidate_paths) if candidate_paths is not None else None
        self.source_mode = source_mode
        self.base_excludes = tuple(base_excludes)
        self.custom_excludes = tuple(custom_excludes)
        self.manual_excludes_enabled = manual_excludes_enabled

    def build(self) -> PackagePlan:
        if self.profile == "dual":
            raise PackagePlanError("dual is a publication layout; build system and memory plans separately")
        if self.profile == "combined":
            system = PackagePlanBuilder(
                self.root, "system", candidate_paths=self.candidate_paths,
                source_mode=self.source_mode, base_excludes=self.base_excludes,
                custom_excludes=self.custom_excludes,
                manual_excludes_enabled=self.manual_excludes_enabled,
            ).build()
            memory = PackagePlanBuilder(
                self.root, "memory", candidate_paths=self.candidate_paths,
                source_mode=self.source_mode, base_excludes=self.base_excludes,
                custom_excludes=self.custom_excludes,
                manual_excludes_enabled=self.manual_excludes_enabled,
            ).build()
            by_path = {item.path: item for item in (*system.entries, *memory.entries)}
            combined_entries = tuple(by_path[path] for path in sorted(by_path))
            return PackagePlan(
                self.root, "combined", combined_entries,
                tuple(sorted(set((*system.excluded, *memory.excluded)))), self.source_mode,
            )
        candidates = self.candidate_paths if self.candidate_paths is not None else discover_filesystem_candidates(self.root)
        selected, excluded = select_candidate_paths(
            self.root, candidates, profile=self.profile,
            base_excludes=self.base_excludes, custom_excludes=self.custom_excludes,
            manual_excludes_enabled=self.manual_excludes_enabled,
        )
        plan_entries: list[PackagePlanEntry] = []
        for relative in selected:
            source = resolve_safe_source(self.root, relative)
            before = source.stat()
            digest = _sha256_file(source)
            after = source.stat()
            if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                raise PackagePlanError(f"source changed while freezing package plan: {relative}")
            plan_entries.append(PackagePlanEntry(
                relative if False else relative,
                source,
                after.st_size,
                digest,
                "memory_file" if self.profile == "memory" else "static_project_file",
            ))
        return PackagePlan(self.root, self.profile, tuple(plan_entries), tuple(excluded), self.source_mode)


__all__ = [
    "PackagePlan", "PackagePlanBuilder", "PackagePlanEntry", "PackagePlanError",
    "discover_filesystem_candidates", "package_safety_reason", "select_candidate_paths",
]
