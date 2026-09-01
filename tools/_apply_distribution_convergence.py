from __future__ import annotations

"""One-shot implementation driver for v16.3.25.3.15 distribution convergence.

This file is intentionally temporary.  The branch-specific workflow executes it,
validates the resulting tree, removes this driver/workflow, and commits only the
real implementation plus permanent tests/build tooling.
"""

import ast
import json
import re
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEN_SOURCE_REF = "1bba3391cae7c2203b6bbdd621768e4c9c021f9e"


def write(rel: str, text: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).lstrip("\n"), encoding="utf-8", newline="\n")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def replace_once(rel: str, old: str, new: str) -> None:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{rel}: expected one replacement, got {count}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def replace_function(rel: str, name: str, source: str) -> None:
    path = ROOT / rel
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name and getattr(n, "col_offset", 0) == 0]
    if len(nodes) != 1:
        raise RuntimeError(f"{rel}: expected one top-level function {name}, got {len(nodes)}")
    node = nodes[0]
    lines = text.splitlines(keepends=True)
    replacement = textwrap.dedent(source).strip("\n") + "\n"
    lines[node.lineno - 1 : node.end_lineno] = [replacement]
    path.write_text("".join(lines), encoding="utf-8", newline="\n")


def insert_after_import(rel: str, marker: str, insertion: str) -> None:
    replace_once(rel, marker, marker + insertion)


def restore_generator_sources() -> None:
    targets = [
        "_jazn_pack_generator_core.py",
        "_jazn_pack_generator_memory_v2.py",
        "_jazn_pack_generator_v1601_policy.py",
        "_jazn_pack_generator_v1638_archive_io.py",
        "_jazn_pack_generator_v16311_profiles.py",
    ]
    base = ROOT / "tools" / "pack_generator_sources"
    base.mkdir(parents=True, exist_ok=True)
    for name in targets:
        raw = subprocess.run(
            ["git", "show", f"{GEN_SOURCE_REF}:tools/{name}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        (base / name).write_bytes(raw)
    write(
        "tools/pack_generator_sources/README.md",
        """
        # Pack Generator build sources

        These modules are build-time sources for the portable two-file Pack Generator.
        `tools/build_jazn_pack_generator_bundle.py` embeds their exact bytes together
        with the canonical packaging/path modules and records SHA-256 for every source.
        The portable distribution remains `jazn_pack_generator.py` plus its settings
        JSON; these build sources are not runtime dependencies of the portable tool.
        """,
    )


def main() -> None:
    # ------------------------------------------------------------------
    # 1. Cross-platform path boundary shared by package/archive/memory.
    # ------------------------------------------------------------------
    write(
        "latka_jazn/tools/safe_paths.py",
        r'''
        from __future__ import annotations

        from pathlib import Path, PurePosixPath, PureWindowsPath
        from typing import Iterable
        import os
        import unicodedata


        class UnsafeRelativePathError(ValueError):
            """Raised when an untrusted package/archive path is not safely relative."""


        _WINDOWS_RESERVED = {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
            "COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³",
        }


        def _within(path: Path, root: Path) -> bool:
            try:
                path.relative_to(root)
            except ValueError:
                return False
            return True


        def _is_reparse_point(path: Path) -> bool:
            try:
                if path.is_symlink():
                    return True
                is_junction = getattr(path, "is_junction", None)
                if callable(is_junction) and is_junction():
                    return True
                attributes = int(getattr(path.lstat(), "st_file_attributes", 0) or 0)
                return bool(attributes & int(getattr(os, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)))
            except OSError:
                return False


        def validate_safe_relative_path(relative: str) -> str:
            """Return canonical POSIX relative path or fail closed on the raw input.

            This is the single lexical boundary for manifests, package-set sidecars,
            archive members and memory transport paths.  It intentionally validates
            *before* any cleanup/sanitization so an unsafe spelling cannot become safe
            merely by stripping `./`, whitespace or alternate separators.
            """
            if not isinstance(relative, str):
                raise UnsafeRelativePathError("path must be a string")
            if not relative or not relative.strip():
                raise UnsafeRelativePathError("empty path is forbidden")
            if relative != relative.strip():
                raise UnsafeRelativePathError("leading or trailing whitespace is forbidden")
            if "\x00" in relative:
                raise UnsafeRelativePathError("NUL byte is forbidden")
            if "\\" in relative:
                raise UnsafeRelativePathError("alternate path separators are forbidden")

            posix = PurePosixPath(relative)
            windows = PureWindowsPath(relative)
            if posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root:
                raise UnsafeRelativePathError("absolute, drive, or UNC path is forbidden")
            parts = relative.split("/")
            if any(part in {"", ".", ".."} for part in parts):
                raise UnsafeRelativePathError("empty, dot, or parent segments are forbidden")
            for part in parts:
                if any(ord(ch) < 32 for ch in part):
                    raise UnsafeRelativePathError("control character in path component is forbidden")
                if ":" in part:
                    raise UnsafeRelativePathError("drive or alternate data stream syntax is forbidden")
                if part.endswith((" ", ".")):
                    raise UnsafeRelativePathError("Windows-trimmed trailing space or period is forbidden")
                stem = part.split(".", 1)[0].upper()
                if stem in _WINDOWS_RESERVED:
                    raise UnsafeRelativePathError(f"Windows reserved device name is forbidden: {part}")
            return "/".join(parts)


        def portable_path_key(relative: str) -> str:
            canonical = validate_safe_relative_path(relative)
            return unicodedata.normalize("NFC", canonical).casefold()


        def validate_safe_path_set(paths: Iterable[str]) -> tuple[str, ...]:
            """Validate a complete cross-platform path inventory and reject collisions."""
            exact: set[str] = set()
            folded: dict[str, str] = {}
            result: list[str] = []
            for raw in paths:
                canonical = validate_safe_relative_path(str(raw))
                if canonical in exact:
                    raise UnsafeRelativePathError(f"duplicate path is forbidden: {canonical}")
                key = portable_path_key(canonical)
                previous = folded.get(key)
                if previous is not None and previous != canonical:
                    raise UnsafeRelativePathError(
                        f"portable case/Unicode path collision is forbidden: {previous!r} vs {canonical!r}"
                    )
                exact.add(canonical)
                folded[key] = canonical
                result.append(canonical)
            return tuple(result)


        def resolve_safe_path(
            root: Path | str,
            relative: str,
            *,
            must_exist: bool = False,
            must_be_file: bool = False,
        ) -> Path:
            canonical = validate_safe_relative_path(relative)
            root_resolved = Path(root).expanduser().resolve()
            candidate = root_resolved.joinpath(*canonical.split("/"))
            resolved = candidate.resolve(strict=False)
            if not _within(resolved, root_resolved):
                raise UnsafeRelativePathError("resolved path escapes root")

            current = root_resolved
            for part in canonical.split("/"):
                current = current / part
                if (current.exists() or current.is_symlink()) and _is_reparse_point(current):
                    target = current.resolve(strict=False)
                    if not _within(target, root_resolved):
                        raise UnsafeRelativePathError("symlink or reparse point escapes root")
            if must_exist and not resolved.exists():
                raise UnsafeRelativePathError("path does not exist")
            if must_be_file and not resolved.is_file():
                raise UnsafeRelativePathError("path is not a regular file")
            return resolved


        def resolve_safe_source(root: Path | str, relative: str) -> Path:
            return resolve_safe_path(root, relative, must_exist=True, must_be_file=True)


        def resolve_safe_destination(root: Path | str, relative: str) -> Path:
            return resolve_safe_path(root, relative)
        ''',
    )

    # ------------------------------------------------------------------
    # 2. One package plan + immutable security policy.
    # ------------------------------------------------------------------
    write(
        "latka_jazn/packaging/package_plan.py",
        r'''
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
                    entries = tuple(by_path[path] for path in sorted(by_path))
                    return PackagePlan(
                        self.root, "combined", entries,
                        tuple(sorted(set((*system.excluded, *memory.excluded)))), self.source_mode,
                    )
                candidates = self.candidate_paths if self.candidate_paths is not None else discover_filesystem_candidates(self.root)
                selected, excluded = select_candidate_paths(
                    self.root, candidates, profile=self.profile,
                    base_excludes=self.base_excludes, custom_excludes=self.custom_excludes,
                    manual_excludes_enabled=self.manual_excludes_enabled,
                )
                entries: list[PackagePlanEntry] = []
                for relative in selected:
                    source = resolve_safe_source(self.root, relative)
                    before = source.stat()
                    digest = _sha256_file(source)
                    after = source.stat()
                    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                        raise PackagePlanError(f"source changed while freezing package plan: {relative}")
                    entries.append(PackagePlanEntry(
                        relative if False else relative,
                        source,
                        after.st_size,
                        digest,
                        "memory_file" if self.profile == "memory" else "static_project_file",
                    ))
                return PackagePlan(self.root, self.profile, tuple(entries), tuple(excluded), self.source_mode)


        __all__ = [
            "PackagePlan", "PackagePlanBuilder", "PackagePlanEntry", "PackagePlanError",
            "discover_filesystem_candidates", "package_safety_reason", "select_candidate_paths",
        ]
        ''',
    )

    # Fix a cosmetic constructor expression immediately; keeping the generated source simple
    # makes the portable bundle byte-for-byte deterministic.
    replace_once(
        "latka_jazn/packaging/package_plan.py",
        "                        relative if False else relative,\n",
        "                        relative,\n",
    )

    # ------------------------------------------------------------------
    # 3. One package-set/sidecar contract, current writer v3.
    # ------------------------------------------------------------------
    write(
        "latka_jazn/packaging/package_set_contract.py",
        r'''
        from __future__ import annotations

        from dataclasses import dataclass
        from pathlib import Path
        from typing import Any, Iterable, Mapping
        import hashlib
        import json
        import re

        from latka_jazn.tools.safe_paths import validate_safe_relative_path, validate_safe_path_set

        CURRENT_SCHEMA = "jazn_package_set/v3"
        READABLE_SCHEMAS = frozenset({"jazn_package_set/v1", "jazn_package_set/v2", CURRENT_SCHEMA})
        WRITABLE_SCHEMAS = frozenset({CURRENT_SCHEMA})
        CONTENT_PROFILES = frozenset({"system", "memory", "combined", "dependencies"})
        _SHA_RE = re.compile(r"^[0-9a-f]{64}$")


        class PackageSetContractError(ValueError):
            pass


        def _flat_filename(value: object) -> str:
            raw = str(value or "").strip()
            canonical = validate_safe_relative_path(raw)
            if "/" in canonical:
                raise PackageSetContractError(f"package output filename must be flat: {raw!r}")
            return canonical


        def _sha(value: object, *, required: bool = True) -> str | None:
            raw = str(value or "").strip().lower()
            if not raw and not required:
                return None
            if not _SHA_RE.fullmatch(raw):
                raise PackageSetContractError(f"invalid SHA-256: {value!r}")
            return raw


        def package_set_hash(outputs: Iterable[Mapping[str, Any]]) -> str:
            digest = hashlib.sha256()
            rows = sorted(outputs, key=lambda row: int(row.get("part_no", 0)))
            for row in rows:
                digest.update(
                    f"{int(row.get('part_no', 0))}\0{row.get('filename')}\0{int(row.get('size_bytes', 0))}\0{row.get('sha256')}\n".encode("utf-8")
                )
            return digest.hexdigest()


        def plan_hash(entries: Iterable[Mapping[str, Any]], *, profile: str) -> str:
            rows = [
                {
                    "path": validate_safe_relative_path(str(item.get("path") or "")),
                    "size_bytes": int(item.get("size_bytes", 0)),
                    "sha256": _sha(item.get("sha256")),
                    "classification": str(item.get("classification") or "file"),
                }
                for item in entries
            ]
            rows.sort(key=lambda item: item["path"])
            raw = json.dumps({"profile": profile, "entries": rows}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            return hashlib.sha256(raw).hexdigest()


        def validate_package_set(payload: Mapping[str, Any], *, require_current: bool = False) -> dict[str, Any]:
            if not isinstance(payload, Mapping):
                raise PackageSetContractError("package sidecar root must be an object")
            schema = str(payload.get("schema_version") or "").strip()
            allowed = WRITABLE_SCHEMAS if require_current else READABLE_SCHEMAS
            if schema not in allowed:
                raise PackageSetContractError(f"unsupported package-set schema: {schema!r}")
            package_name = _flat_filename(payload.get("package_name"))
            profile = str(payload.get("profile") or "unknown").strip().lower()
            if schema == CURRENT_SCHEMA and profile not in CONTENT_PROFILES:
                raise PackageSetContractError(f"unsupported v3 package profile: {profile!r}")
            archive_format = str(payload.get("archive_format") or "").strip().lower()
            if archive_format not in {"binary", "independent"}:
                raise PackageSetContractError(f"unsupported archive_format: {archive_format!r}")
            raw_outputs = payload.get("outputs")
            if not isinstance(raw_outputs, list) or not raw_outputs:
                raise PackageSetContractError("package sidecar requires non-empty outputs")
            outputs: list[dict[str, Any]] = []
            names: list[str] = []
            part_numbers: set[int] = set()
            for raw in raw_outputs:
                if not isinstance(raw, Mapping):
                    raise PackageSetContractError("package output entry must be an object")
                part_no = int(raw.get("part_no", len(outputs) + 1))
                if part_no < 1 or part_no in part_numbers:
                    raise PackageSetContractError("package output part numbers must be positive and unique")
                part_numbers.add(part_no)
                filename = _flat_filename(raw.get("filename"))
                names.append(filename)
                size = int(raw.get("size_bytes", -1))
                if size < 0:
                    raise PackageSetContractError(f"negative package output size: {filename}")
                outputs.append({
                    **dict(raw), "part_no": part_no, "filename": filename,
                    "size_bytes": size, "sha256": _sha(raw.get("sha256")),
                })
            validate_safe_path_set(names)
            result = dict(payload)
            result.update({
                "schema_version": schema,
                "package_name": package_name,
                "profile": profile,
                "archive_format": archive_format,
                "outputs": sorted(outputs, key=lambda item: item["part_no"]),
            })
            if schema == CURRENT_SCHEMA:
                entries = payload.get("entries")
                if not isinstance(entries, list):
                    raise PackageSetContractError("v3 package sidecar requires entries inventory")
                paths = [validate_safe_relative_path(str((item or {}).get("path") or "")) for item in entries if isinstance(item, Mapping)]
                if len(paths) != len(entries):
                    raise PackageSetContractError("v3 package entries must be objects")
                validate_safe_path_set(paths)
                declared_plan = _sha(payload.get("plan_sha256"))
                computed_plan = plan_hash(entries, profile=profile)
                if declared_plan != computed_plan:
                    raise PackageSetContractError("v3 plan_sha256 does not match entries")
                declared_set = _sha(payload.get("package_set_sha256"))
                if declared_set != package_set_hash(outputs):
                    raise PackageSetContractError("v3 package_set_sha256 does not match outputs")
            return result


        def load_package_set(path: Path | str, *, require_current: bool = False) -> dict[str, Any]:
            source = Path(path)
            try:
                payload = json.loads(source.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise PackageSetContractError(f"cannot read package sidecar {source}: {exc}") from exc
            return validate_package_set(payload, require_current=require_current)


        def build_single_zip_sidecar(
            *,
            package_name: str,
            profile: str,
            package_version: str,
            zip_path: Path,
            entries: list[dict[str, Any]],
            artifact_role: str | None = None,
            related_artifacts: list[dict[str, Any]] | None = None,
            generator: str = "latka_jazn",
        ) -> dict[str, Any]:
            zip_path = Path(zip_path)
            digest = hashlib.sha256()
            with zip_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            output = {
                "part_no": 1,
                "filename": zip_path.name,
                "size_bytes": zip_path.stat().st_size,
                "sha256": digest.hexdigest(),
                "is_complete_zip": True,
            }
            payload: dict[str, Any] = {
                "schema_version": CURRENT_SCHEMA,
                "generator": generator,
                "package_name": _flat_filename(package_name),
                "profile": profile,
                "archive_format": "independent",
                "container_format": "zip",
                "package_version": package_version,
                "plan_sha256": plan_hash(entries, profile=profile),
                "entry_count": len(entries),
                "source_total_size_bytes": sum(int(item.get("size_bytes", 0)) for item in entries),
                "package_set_sha256": package_set_hash([output]),
                "outputs": [output],
                "entries": entries,
                "artifact_role": artifact_role or profile,
                "related_artifacts": list(related_artifacts or []),
            }
            return validate_package_set(payload, require_current=True)


        __all__ = [
            "CURRENT_SCHEMA", "READABLE_SCHEMAS", "WRITABLE_SCHEMAS", "CONTENT_PROFILES",
            "PackageSetContractError", "build_single_zip_sidecar", "load_package_set",
            "package_set_hash", "plan_hash", "validate_package_set",
        ]
        ''',
    )

    # ------------------------------------------------------------------
    # 4. Central resource-limit profiles (existing limits preserved).
    # ------------------------------------------------------------------
    write(
        "latka_jazn/archive/resource_policy.py",
        r'''
        from __future__ import annotations

        from dataclasses import dataclass


        @dataclass(frozen=True, slots=True)
        class ArchiveResourcePolicy:
            name: str
            max_members: int
            max_total_uncompressed_bytes: int
            max_member_uncompressed_bytes: int
            max_compression_ratio: float


        SYSTEM_PACKAGE = ArchiveResourcePolicy("system_package", 20_000, 8 * 1024**3, 2 * 1024**3, 1_000.0)
        MEMORY_PACKAGE_V3 = ArchiveResourcePolicy("memory_package_v3", 20_000, 8 * 1024**3, 2 * 1024**3, 1_000.0)
        DEPENDENCY_ARTIFACT = ArchiveResourcePolicy("dependency_artifact", 20_000, 8 * 1024**3, 2 * 1024**3, 1_000.0)
        LEGACY_MEMORY_REPACK_INPUT = ArchiveResourcePolicy("legacy_memory_repack_input", 200_000, 64 * 1024**3, 16 * 1024**3, 500.0)
        GENERIC_ARCHIVE = ArchiveResourcePolicy("generic_archive", 200_000, 64 * 1024**3, 16 * 1024**3, 500.0)

        POLICIES = {item.name: item for item in (
            SYSTEM_PACKAGE, MEMORY_PACKAGE_V3, DEPENDENCY_ARTIFACT,
            LEGACY_MEMORY_REPACK_INPUT, GENERIC_ARCHIVE,
        )}
        ''',
    )

    replace_once(
        "latka_jazn/packaging/zip_resource_limits.py",
        "import zipfile\n\n\nclass ZipResourceLimitError",
        "import zipfile\n\nfrom latka_jazn.archive.resource_policy import SYSTEM_PACKAGE\n\n\nclass ZipResourceLimitError",
    )
    replace_once(
        "latka_jazn/packaging/zip_resource_limits.py",
        "DEFAULT_MAX_MEMBERS = 20_000\nDEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES = 8 * 1024**3\nDEFAULT_MAX_MEMBER_UNCOMPRESSED_BYTES = 2 * 1024**3\nDEFAULT_MAX_COMPRESSION_RATIO = 1_000.0",
        "DEFAULT_MAX_MEMBERS = SYSTEM_PACKAGE.max_members\nDEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES = SYSTEM_PACKAGE.max_total_uncompressed_bytes\nDEFAULT_MAX_MEMBER_UNCOMPRESSED_BYTES = SYSTEM_PACKAGE.max_member_uncompressed_bytes\nDEFAULT_MAX_COMPRESSION_RATIO = SYSTEM_PACKAGE.max_compression_ratio",
    )

    # ------------------------------------------------------------------
    # 5. package_export and package_integrity delegate content decisions.
    # ------------------------------------------------------------------
    insert_after_import(
        "latka_jazn/tools/package_export.py",
        "from latka_jazn.packaging.zip_resource_limits import validate_zip_resources\n",
        "from latka_jazn.packaging.package_plan import PackagePlanBuilder, package_safety_reason\n",
    )
    replace_function(
        "latka_jazn/tools/package_export.py",
        "forbidden_package_reason",
        '''
        def forbidden_package_reason(rel: str) -> str | None:
            return package_safety_reason(str(rel), "system")
        ''',
    )
    replace_function(
        "latka_jazn/tools/package_export.py",
        "build_package_plan",
        '''
        def build_package_plan(root: Path, mode: str, output_zip: Path | None = None) -> list[tuple[Path, str]]:
            """Compatibility facade over the one canonical PackagePlanBuilder."""
            root = Path(root).resolve()
            plan = PackagePlanBuilder(root, mode, source_mode="package_export").build()
            rows = [(item.source, item.path) for item in plan.entries]
            validate_package_plan((rel for _, rel in rows), root=root)
            if mode == "github_source_safe":
                blocked = [
                    {"path": rel, "reason": reason}
                    for path, rel in rows
                    if (reason := private_generated_source_reason(path, rel))
                ]
                if blocked:
                    raise PackagePlanValidationError(
                        "Private generated sources remain in source-safe plan: "
                        + json.dumps(blocked[:10], ensure_ascii=False)
                    )
            return rows
        ''',
    )

    insert_after_import(
        "latka_jazn/tools/package_integrity.py",
        "from latka_jazn.packaging.zip_resource_limits import validate_zip_resources\n",
        "from latka_jazn.packaging.package_plan import package_safety_reason\n",
    )
    replace_function(
        "latka_jazn/tools/package_integrity.py",
        "path_is_forbidden",
        '''
        def path_is_forbidden(relative: str) -> bool:
            try:
                rel = validate_safe_relative_path(relative)
            except UnsafeRelativePathError:
                return True
            if rel == MANIFEST_NAME:
                return True
            return package_safety_reason(rel, "system") is not None
        ''',
    )

    # ------------------------------------------------------------------
    # 6. Release staging selects the exact canonical system plan from Git tree.
    # ------------------------------------------------------------------
    insert_after_import(
        "latka_jazn/tools/release_staging.py",
        "from latka_jazn.tools.safe_paths import resolve_safe_destination, resolve_safe_source, validate_safe_relative_path\n",
        "from latka_jazn.packaging.package_plan import select_candidate_paths\n",
    )
    # Inject selection after ls-tree parsing and before cat-file process.
    replace_once(
        "latka_jazn/tools/release_staging.py",
        "    # Read every blob through one long-lived Git process.  Each request is\n",
        "    selected_paths, excluded_paths = select_candidate_paths(\n        root, [relative for _sha, relative in entries], profile=\"system\"\n    )\n    selected_set = set(selected_paths)\n    entries = [(sha, relative) for sha, relative in entries if relative in selected_set]\n\n    # Read every blob through one long-lived Git process.  Each request is\n",
    )
    replace_once(
        "latka_jazn/tools/release_staging.py",
        '        "tracked_file_count": file_count,\n',
        '        "tracked_file_count": len(selected_paths) + len(excluded_paths),\n        "selected_file_count": file_count,\n        "excluded_file_count": len(excluded_paths),\n',
    )

    # ------------------------------------------------------------------
    # 7. Sidecar consumers read the same compatibility contract.
    # ------------------------------------------------------------------
    insert_after_import(
        "latka_jazn/packaging/split_zip_package.py",
        "from latka_jazn.packaging.zip_resource_limits import validate_zip_resources\n",
        "from latka_jazn.packaging.package_set_contract import READABLE_SCHEMAS\n",
    )
    replace_once(
        "latka_jazn/packaging/split_zip_package.py",
        'SUPPORTED_PACKAGE_SET_SCHEMAS = frozenset({"jazn_package_set/v1", "jazn_package_set/v2"})',
        "SUPPORTED_PACKAGE_SET_SCHEMAS = READABLE_SCHEMAS",
    )

    insert_after_import(
        "latka_jazn/archive/service.py",
        "import zipfile\n",
        "\nfrom latka_jazn.packaging.package_set_contract import READABLE_SCHEMAS\nfrom latka_jazn.archive.resource_policy import GENERIC_ARCHIVE\nfrom latka_jazn.tools.safe_paths import validate_safe_relative_path, portable_path_key\n",
    )
    replace_once(
        "latka_jazn/archive/service.py",
        'SUPPORTED_PACKAGE_SCHEMAS = {"jazn_package_set/v2", "jazn_package_set/v3"}',
        "SUPPORTED_PACKAGE_SCHEMAS = READABLE_SCHEMAS",
    )
    replace_once("latka_jazn/archive/service.py", "    max_members: int = 200_000", "    max_members: int = GENERIC_ARCHIVE.max_members")
    replace_once("latka_jazn/archive/service.py", "    max_total_uncompressed_bytes: int = 64 * 1024 * 1024 * 1024", "    max_total_uncompressed_bytes: int = GENERIC_ARCHIVE.max_total_uncompressed_bytes")
    replace_once("latka_jazn/archive/service.py", "    max_member_bytes: int = 16 * 1024 * 1024 * 1024", "    max_member_bytes: int = GENERIC_ARCHIVE.max_member_uncompressed_bytes")
    replace_once("latka_jazn/archive/service.py", "    max_compression_ratio: float = 500.0", "    max_compression_ratio: float = GENERIC_ARCHIVE.max_compression_ratio")
    replace_function(
        "latka_jazn/archive/service.py",
        "_normalize_member_name",
        '''
        def _normalize_member_name(value: str) -> str:
            try:
                return validate_safe_relative_path(str(value or ""))
            except Exception as exc:
                raise ArchiveError(f"unsafe_archive_member:{value}:{exc}") from exc
        ''',
    )
    replace_function(
        "latka_jazn/archive/service.py",
        "_member_key",
        '''
        def _member_key(name: str) -> str:
            try:
                return portable_path_key(name)
            except Exception as exc:
                raise ArchiveError(f"unsafe_archive_member:{name}:{exc}") from exc
        ''',
    )

    insert_after_import(
        "latka_jazn/packaging/memory_package_source.py",
        "import os\n",
        "\nfrom latka_jazn.packaging.package_set_contract import validate_package_set, PackageSetContractError\n",
    )
    replace_once(
        "latka_jazn/packaging/memory_package_source.py",
        '    if str(payload.get("schema_version") or "") != "jazn_package_set/v2":\n        raise MemoryPackageSourceError("R2 package sidecar schema is unsupported")\n    if str(payload.get("profile") or "").strip().lower() != "memory":',
        '    try:\n        payload = validate_package_set(payload)\n    except PackageSetContractError as exc:\n        raise MemoryPackageSourceError(f"R2 package sidecar schema/contract is unsupported: {exc}") from exc\n    if str(payload.get("profile") or "").strip().lower() != "memory":',
    )

    # ------------------------------------------------------------------
    # 8. Memory/path fixes: no pre-validation lstrip and cross-filesystem-safe transaction.
    # ------------------------------------------------------------------
    insert_after_import(
        "latka_jazn/packaging/memory_raw_segmentation.py",
        "from typing import Any, Iterable, Mapping\n",
        "\nfrom latka_jazn.tools.safe_paths import validate_safe_relative_path, UnsafeRelativePathError\n",
    )
    # This is a class staticmethod; AST top-level helper cannot replace it, use exact block.
    replace_once(
        "latka_jazn/packaging/memory_raw_segmentation.py",
        '''    @staticmethod\n    def _safe_memory_path(value: str) -> str:\n        normalized = value.replace("\\\\", "/").strip().lstrip("./")\n        path = PurePosixPath(normalized)\n        if not normalized or path.is_absolute() or ".." in path.parts or not normalized.startswith("memory/"):\n            raise RawMemorySegmentationError(f"unsafe memory path: {value!r}")\n        return path.as_posix()\n''',
        '''    @staticmethod\n    def _safe_memory_path(value: str) -> str:\n        try:\n            canonical = validate_safe_relative_path(str(value))\n        except UnsafeRelativePathError as exc:\n            raise RawMemorySegmentationError(f"unsafe memory path: {value!r}: {exc}") from exc\n        if not canonical.startswith("memory/"):\n            raise RawMemorySegmentationError(f"unsafe memory path outside memory/: {value!r}")\n        return canonical\n''',
    )

    # Remove classification sanitization that could hide a raw unsafe spelling.
    replace_once(
        "latka_jazn/core/private_data_export_gate.py",
        '        normalized = path.as_posix().lower().lstrip("./")',
        '        normalized = path.as_posix().lower()',
    )

    # Memory transaction helper.
    write(
        "latka_jazn/packaging/memory_transaction.py",
        r'''
        from __future__ import annotations

        from dataclasses import dataclass
        from pathlib import Path
        from typing import Callable
        import hashlib
        import os
        import shutil
        import uuid


        class MemoryTransactionError(RuntimeError):
            pass


        def _nearest_existing(path: Path) -> Path:
            current = Path(path).resolve()
            while not current.exists() and current.parent != current:
                current = current.parent
            return current


        def same_filesystem(left: Path, right: Path) -> bool:
            try:
                return os.stat(_nearest_existing(left)).st_dev == os.stat(_nearest_existing(right)).st_dev
            except OSError:
                return False


        def tree_fingerprint(root: Path) -> str:
            base = Path(root).resolve()
            digest = hashlib.sha256()
            for path in sorted(p for p in base.rglob("*") if p.is_file() and not p.is_symlink()):
                rel = path.relative_to(base).as_posix()
                item = hashlib.sha256()
                size = 0
                with path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        item.update(block); size += len(block)
                digest.update(f"{rel}\0{size}\0{item.hexdigest()}\n".encode("utf-8"))
            return digest.hexdigest()


        @dataclass(frozen=True, slots=True)
        class MemoryPromotionResult:
            target_memory: Path
            backup_memory: Path | None
            failed_memory: Path | None
            had_previous: bool
            backup_mode: str


        def promote_memory_tree(
            *,
            source_memory: Path,
            target_memory: Path,
            workspace: Path,
            fault_injector: Callable[[str], None] | None = None,
            post_promote: Callable[[], None] | None = None,
        ) -> MemoryPromotionResult:
            source_memory = Path(source_memory).resolve()
            target_memory = Path(target_memory).resolve()
            workspace = Path(workspace).resolve()
            if not source_memory.is_dir():
                raise MemoryTransactionError(f"source memory tree missing: {source_memory}")
            target_parent = target_memory.parent
            target_parent.mkdir(parents=True, exist_ok=True)
            txid = uuid.uuid4().hex
            transaction = target_parent / f".jazn-memory-attach-{txid}"
            staged_memory = transaction / "memory"
            failed_memory = transaction / "failed-memory"
            transaction.mkdir(parents=False, exist_ok=False)
            source_fp = tree_fingerprint(source_memory)
            shutil.copytree(source_memory, staged_memory)
            if tree_fingerprint(staged_memory) != source_fp:
                shutil.rmtree(transaction, ignore_errors=True)
                raise MemoryTransactionError("staged memory copy fingerprint mismatch")

            previous = target_memory if target_memory.exists() else None
            had_previous = previous is not None
            backup_root = workspace / "memory_attach_backups" / txid
            backup_mode = "workspace_same_filesystem"
            if had_previous and not same_filesystem(previous.parent, backup_root.parent):
                backup_root = target_parent / ".jazn-memory-attach-backups" / txid
                backup_mode = "target_filesystem"
            backup_memory = backup_root / "memory" if had_previous else None
            old_moved = False
            new_promoted = False
            try:
                if had_previous and backup_memory is not None:
                    backup_memory.parent.mkdir(parents=True, exist_ok=False)
                    os.replace(previous, backup_memory)
                    old_moved = True
                    if fault_injector:
                        fault_injector("after_old_renamed")
                os.replace(staged_memory, target_memory)
                new_promoted = True
                if fault_injector:
                    fault_injector("after_new_promoted")
                if post_promote:
                    post_promote()
                if fault_injector:
                    fault_injector("before_commit_complete")
            except Exception:
                if new_promoted and target_memory.exists():
                    failed_memory.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target_memory, failed_memory)
                if old_moved and backup_memory is not None and backup_memory.exists():
                    target_memory.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(backup_memory, target_memory)
                raise
            finally:
                if staged_memory.exists():
                    shutil.rmtree(staged_memory, ignore_errors=True)
            if transaction.exists() and not any(transaction.iterdir()):
                transaction.rmdir()
            return MemoryPromotionResult(
                target_memory=target_memory,
                backup_memory=backup_memory if backup_memory and backup_memory.exists() else None,
                failed_memory=failed_memory if failed_memory.exists() else None,
                had_previous=had_previous,
                backup_mode=backup_mode,
            )
        ''',
    )

    insert_after_import(
        "latka_jazn/packaging/memory_package_attach.py",
        "from latka_jazn.memory.session_continuity import SessionContinuityManager\n" if "from latka_jazn.memory.session_continuity import SessionContinuityManager\n" in read("latka_jazn/packaging/memory_package_attach.py") else "import zipfile\n",
        "from latka_jazn.packaging.memory_transaction import promote_memory_tree\n",
    )
    replace_function(
        "latka_jazn/packaging/memory_package_attach.py",
        "_install_memory_tree",
        '''
        def _install_memory_tree(
            runtime_root: Path,
            workspace: Path,
            source_memory: Path,
            report: dict[str, Any],
        ) -> tuple[Path, bool]:
            target_memory = resolve_memory_root(runtime_root, prefer_existing_legacy=False)
            previous_memory = resolve_memory_root(runtime_root, prefer_existing_legacy=True)
            # If the compatibility resolver points at an old per-version tree while the
            # new canonical root is elsewhere, preserve/copy that source first and only
            # switch the canonical target. Existing canonical targets use atomic rename.
            if previous_memory.exists() and previous_memory.resolve() != target_memory.resolve() and not target_memory.exists():
                target_memory.parent.mkdir(parents=True, exist_ok=True)
                compatibility_seed = target_memory.parent / f".jazn-legacy-memory-seed-{uuid.uuid4().hex}"
                shutil.copytree(previous_memory, compatibility_seed)
                source_memory = source_memory  # package remains authoritative; legacy tree is untouched recovery evidence
                shutil.rmtree(compatibility_seed, ignore_errors=True)
                report["legacy_memory_preserved_in_place"] = str(previous_memory)

            transactional_report: dict[str, Any] = {}
            def _post_promote() -> None:
                transactional = initialize_transactional_memory_store(runtime_root)
                transactional_report.update(transactional)
                if transactional.get("ok") is not True:
                    raise RuntimeError("transactional_memory_initialization_failed")

            promotion = promote_memory_tree(
                source_memory=source_memory,
                target_memory=target_memory,
                workspace=workspace,
                post_promote=_post_promote,
            )
            report["memory_root"] = str(target_memory)
            report["previous_memory_root"] = str(previous_memory) if promotion.had_previous else None
            report["transactional_memory_initialization"] = transactional_report
            report["memory_attach_backup_mode"] = promotion.backup_mode
            report["previous_memory_backup"] = str(promotion.backup_memory) if promotion.backup_memory else None
            return promotion.backup_memory or Path(), promotion.had_previous
        ''',
    )

    # ------------------------------------------------------------------
    # 9. Legacy repack central sidecar compatibility and safe paths.
    # ------------------------------------------------------------------
    insert_after_import(
        "latka_jazn/packaging/memory_package_legacy_repack.py",
        "import zipfile\n",
        "\nfrom latka_jazn.packaging.package_set_contract import validate_package_set, PackageSetContractError\nfrom latka_jazn.tools.safe_paths import validate_safe_relative_path, UnsafeRelativePathError\n",
    )
    replace_function(
        "latka_jazn/packaging/memory_package_legacy_repack.py",
        "_safe_memory_path",
        '''
        def _safe_memory_path(value: str) -> str:
            try:
                text = validate_safe_relative_path(str(value))
            except UnsafeRelativePathError as exc:
                raise LegacyMemoryRepackError(f"unsafe legacy ZIP member {value!r}: {exc}") from exc
            path = PurePosixPath(text)
            if not path.parts or path.parts[0] != "memory":
                raise LegacyMemoryRepackError(f"legacy package member is outside memory/: {value!r}")
            return path.as_posix()
        ''',
    )
    replace_once(
        "latka_jazn/packaging/memory_package_legacy_repack.py",
        '    if str(payload.get("schema_version") or "") not in {"jazn_package_set/v1", "jazn_package_set/v2"}:\n        raise LegacyMemoryRepackError("legacy package sidecar schema is unsupported")\n    if str(payload.get("profile") or "").strip().lower() != "memory":',
        '    try:\n        payload = validate_package_set(payload)\n    except PackageSetContractError as exc:\n        raise LegacyMemoryRepackError(f"legacy package sidecar schema is unsupported: {exc}") from exc\n    if str(payload.get("profile") or "").strip().lower() != "memory":',
    )

    # ------------------------------------------------------------------
    # 10. release-build emits canonical v3 package sidecar + checksum inventory.
    # ------------------------------------------------------------------
    insert_after_import(
        "latka_jazn/tools/release_bundle.py",
        "from latka_jazn.packaging.zip_resource_limits import validate_zip_resources\n",
        "from latka_jazn.packaging.package_set_contract import build_single_zip_sidecar\n",
    )
    # After final digest is known, persist a canonical package-set sidecar.
    marker = '        sha_path = output.with_name(output.name + ".sha256")\n'
    insertion = '''        with zipfile.ZipFile(output, "r") as final_archive:\n            integrity_payload = json.loads(final_archive.read("PACKAGE_INTEGRITY_MANIFEST.json").decode("utf-8-sig"))\n        integrity_entries = [dict(item) for item in integrity_payload.get("files") or [] if isinstance(item, dict)]\n        package_sidecar = build_single_zip_sidecar(\n            package_name=output.name,\n            profile="system",\n            package_version=PACKAGE_VERSION_FULL,\n            zip_path=output,\n            entries=integrity_entries,\n            artifact_role="system",\n            generator="latka_jazn.tools.release_bundle",\n        )\n        package_sidecar_path = output.with_name(output.name + ".package.json")\n        package_sidecar_path.write_text(json.dumps(package_sidecar, ensure_ascii=False, indent=2, sort_keys=True) + "\\n", encoding="utf-8")\n        parts_sha_path = output.with_name(output.name + ".parts.sha256")\n        parts_sha_path.write_text(f"{digest}  {output.name}\\n", encoding="ascii")\n\n'''
    replace_once("latka_jazn/tools/release_bundle.py", marker, insertion + marker)
    replace_once(
        "latka_jazn/tools/release_bundle.py",
        '            "sha256_path": str(sha_path),\n',
        '            "sha256_path": str(sha_path),\n            "package_sidecar_path": str(package_sidecar_path),\n            "parts_sha256_path": str(parts_sha_path),\n',
    )

    # ------------------------------------------------------------------
    # 11. Target-specific verified dependency release artifact.
    # ------------------------------------------------------------------
    write(
        "latka_jazn/dependencies/release_artifact.py",
        r'''
        from __future__ import annotations

        from pathlib import Path
        from typing import Any, Sequence
        import argparse
        import hashlib
        import json
        import shutil
        import tempfile
        import zipfile

        from latka_jazn.dependencies.common import activation_profile_names
        from latka_jazn.dependencies.wheelhouse import download_bundle, verify_bundle, read_manifest, sha256_file
        from latka_jazn.packaging.package_set_contract import build_single_zip_sidecar
        from latka_jazn.version import PACKAGE_VERSION_FULL


        def build_dependency_release_artifact(
            root: Path | str,
            output_dir: Path | str,
            *,
            profile_names: Sequence[str] | None = None,
            python_version: str | None = None,
            platform_alias: str | None = None,
            python_executable: str | None = None,
            system_zip: Path | None = None,
        ) -> dict[str, Any]:
            project_root = Path(root).resolve()
            destination = Path(output_dir).resolve()
            destination.mkdir(parents=True, exist_ok=True)
            profiles = list(profile_names or activation_profile_names(project_root))
            with tempfile.TemporaryDirectory(prefix="jazn-dependency-release-") as temp_raw:
                temp = Path(temp_raw)
                result = download_bundle(
                    project_root,
                    profile_names=profiles,
                    python_version=python_version,
                    platform_alias=platform_alias,
                    python_executable=python_executable,
                    wheelhouse_root=temp / "wheelhouse",
                )
                if result.get("ok") is not True:
                    raise RuntimeError(f"dependency wheelhouse download/verification failed: {result}")
                bundle = Path(str(result["bundle_dir"])).resolve()
                verified = verify_bundle(bundle)
                if verified.get("ok") is not True:
                    raise RuntimeError(f"dependency wheelhouse verification failed: {verified.get('errors')}")
                manifest = read_manifest(bundle / "JAZN_WHEELHOUSE_MANIFEST.json") or {}
                target = manifest.get("target") if isinstance(manifest.get("target"), dict) else {}
                alias = str(target.get("alias") or "unknown")
                pyver = str(target.get("python_version") or "unknown").replace(".", "")
                zip_name = f"jazn_latka_{PACKAGE_VERSION_FULL}-dependencies-{alias}-py{pyver}.zip"
                zip_path = destination / zip_name
                entries: list[dict[str, Any]] = []
                with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True, compresslevel=6) as archive:
                    for source in sorted(p for p in bundle.iterdir() if p.is_file() and not p.is_symlink()):
                        arcname = f"{bundle.name}/{source.name}"
                        archive.write(source, arcname)
                        entries.append({
                            "path": arcname,
                            "size_bytes": source.stat().st_size,
                            "sha256": sha256_file(source),
                            "classification": "dependency_wheelhouse_file",
                        })
                related: list[dict[str, Any]] = []
                if system_zip is not None:
                    syszip = Path(system_zip).resolve()
                    related.append({"role": "system", "filename": syszip.name, "sha256": sha256_file(syszip)})
                sidecar = build_single_zip_sidecar(
                    package_name=zip_path.name,
                    profile="dependencies",
                    package_version=PACKAGE_VERSION_FULL,
                    zip_path=zip_path,
                    entries=entries,
                    artifact_role="dependencies",
                    related_artifacts=related,
                    generator="latka_jazn.dependencies.release_artifact",
                )
                sidecar_path = zip_path.with_name(zip_path.name + ".package.json")
                sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                parts_path = zip_path.with_name(zip_path.name + ".parts.sha256")
                parts_path.write_text(f"{sha256_file(zip_path)}  {zip_path.name}\n", encoding="ascii")
                return {
                    "ok": True,
                    "zip_path": str(zip_path),
                    "sidecar_path": str(sidecar_path),
                    "parts_sha256_path": str(parts_path),
                    "wheelhouse_bundle_name": bundle.name,
                    "target": target,
                    "profiles": profiles,
                    "verification": verified,
                    "related_artifacts": related,
                }


        def main(argv: Sequence[str] | None = None) -> int:
            parser = argparse.ArgumentParser(allow_abbrev=False)
            parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
            parser.add_argument("--output-dir", type=Path, required=True)
            parser.add_argument("--python-version")
            parser.add_argument("--platform", default="current")
            parser.add_argument("--python-executable")
            parser.add_argument("--system-zip", type=Path)
            parser.add_argument("--json", action="store_true")
            ns = parser.parse_args(list(argv) if argv is not None else None)
            result = build_dependency_release_artifact(
                ns.root, ns.output_dir,
                python_version=ns.python_version,
                platform_alias=ns.platform,
                python_executable=ns.python_executable,
                system_zip=ns.system_zip,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if result.get("ok") else 2


        if __name__ == "__main__":
            raise SystemExit(main())
        ''',
    )

    # Add real PEP 440 parsing when packaging is available; keep a bootstrap-safe fallback.
    replace_function(
        "latka_jazn/dependencies/common.py",
        "version_satisfies_requirement",
        '''
        def version_satisfies_requirement(installed_version: str, requirement: str) -> bool | None:
            try:
                from packaging.requirements import Requirement
                from packaging.version import Version
                parsed = Requirement(requirement)
                return Version(installed_version) in parsed.specifier
            except ImportError:
                pass
            except Exception:
                return None
            specifier = _specifier_text(requirement)
            if not specifier:
                return True
            installed = _version_tuple(installed_version)
            if installed is None:
                return None
            for clause in (part.strip() for part in specifier.split(",")):
                match = re.match(r"^(>=|<=|==|!=|>|<)\\s*([^\\s]+)$", clause)
                if not match:
                    return None
                operator, raw_expected = match.groups()
                expected = _version_tuple(raw_expected)
                if expected is None:
                    return None
                width = max(len(installed), len(expected))
                left = installed + (0,) * (width - len(installed))
                right = expected + (0,) * (width - len(expected))
                comparison = (left > right) - (left < right)
                if not {">=": comparison >= 0, "<=": comparison <= 0, ">": comparison > 0, "<": comparison < 0, "==": comparison == 0, "!=": comparison != 0}[operator]:
                    return False
            return True
        ''',
    )
    # packaging becomes a normal core dependency and is included in wheelhouse resolution.
    replace_once(
        "pyproject.toml",
        '  "tzdata>=2024.1",\n',
        '  "tzdata>=2024.1",\n  "packaging>=24.2,<27",\n',
    )

    # ------------------------------------------------------------------
    # 12. Restore generator build sources and create deterministic bundle builder.
    # ------------------------------------------------------------------
    restore_generator_sources()
    write(
        "tools/build_jazn_pack_generator_bundle.py",
        r'''
        from __future__ import annotations

        import argparse
        import base64
        import hashlib
        import json
        import re
        import zlib
        from pathlib import Path
        from typing import Sequence

        ROOT = Path(__file__).resolve().parents[1]
        GENERATOR = ROOT / "tools" / "jazn_pack_generator.py"
        BEGIN = "# BEGIN AUTO-GENERATED CANONICAL PACKAGE BUNDLE"
        END = "# END AUTO-GENERATED CANONICAL PACKAGE BUNDLE"
        SOURCES = {
            "latka_jazn.memory.storage_limits": "latka_jazn/memory/storage_limits.py",
            "latka_jazn.packaging.memory_raw_segmentation": "latka_jazn/packaging/memory_raw_segmentation.py",
            "latka_jazn.tools.safe_paths": "latka_jazn/tools/safe_paths.py",
            "latka_jazn.packaging.package_profiles": "latka_jazn/packaging/package_profiles.py",
            "latka_jazn.packaging.package_plan": "latka_jazn/packaging/package_plan.py",
            "latka_jazn.packaging.package_set_contract": "latka_jazn/packaging/package_set_contract.py",
            "tools._jazn_pack_generator_core": "tools/pack_generator_sources/_jazn_pack_generator_core.py",
            "tools._jazn_pack_generator_memory_v2": "tools/pack_generator_sources/_jazn_pack_generator_memory_v2.py",
            "tools._jazn_pack_generator_v1601_policy": "tools/pack_generator_sources/_jazn_pack_generator_v1601_policy.py",
            "tools._jazn_pack_generator_v1638_archive_io": "tools/pack_generator_sources/_jazn_pack_generator_v1638_archive_io.py",
            "tools._jazn_pack_generator_v16311_profiles": "tools/pack_generator_sources/_jazn_pack_generator_v16311_profiles.py",
        }


        def payload(source: bytes) -> str:
            return base64.b85encode(zlib.compress(source, 9)).decode("ascii")


        def manifest() -> dict[str, dict[str, object]]:
            rows: dict[str, dict[str, object]] = {}
            for module, relative in SOURCES.items():
                raw = (ROOT / relative).read_bytes()
                rows[module] = {"source_path": relative, "size_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            return rows


        def generated_map() -> str:
            lines = ["_BUNDLED_MODULES = {"]
            for module, relative in SOURCES.items():
                raw = (ROOT / relative).read_bytes()
                lines.append(f"    {module!r}: {payload(raw)!r},")
            lines.append("}")
            return "\n".join(lines)


        def overlay() -> str:
            mf = json.dumps(manifest(), ensure_ascii=False, sort_keys=True)
            return f'''{BEGIN}\n_CANONICAL_PACKAGE_BUNDLE_MANIFEST = {mf}\n\n# Load current canonical package-policy modules from the same immutable bundle.\nfor _canonical_module_name in (\n    "latka_jazn.tools.safe_paths",\n    "latka_jazn.packaging.package_profiles",\n    "latka_jazn.packaging.package_plan",\n    "latka_jazn.packaging.package_set_contract",\n):\n    if _canonical_module_name not in _bundle_sys.modules:\n        _load_bundled_module(_canonical_module_name)\n\n_canonical_plan = _bundle_sys.modules["latka_jazn.packaging.package_plan"]\n_canonical_contract = _bundle_sys.modules["latka_jazn.packaging.package_set_contract"]\n\ndef _canonical_generator_discover(root, profile):\n    candidates = _canonical_plan.discover_filesystem_candidates(root)\n    selected, _excluded = _canonical_plan.select_candidate_paths(root, candidates, profile=profile)\n    return selected, f"canonical-package-plan:{{profile}}"\n\ndef _canonical_discover_system(root):\n    return _canonical_generator_discover(root, "system")\n\ndef _canonical_discover_memory(root):\n    return _canonical_generator_discover(root, "memory")\n\ndef _canonical_filter_candidates(candidates, *, profile, base_excludes, custom_excludes, manual_excludes_enabled):\n    return _canonical_plan.select_candidate_paths(\n        _impl._core.Path(_impl._core.Path.cwd()).resolve() if False else _canonical_generator_active_root(),\n        candidates, profile=profile, base_excludes=base_excludes, custom_excludes=custom_excludes,\n        manual_excludes_enabled=manual_excludes_enabled,\n    )\n\n_CANONICAL_GENERATOR_ROOT = None\ndef _canonical_generator_active_root():\n    if _CANONICAL_GENERATOR_ROOT is None:\n        raise _impl.PackError("canonical package-plan root was not initialized")\n    return _CANONICAL_GENERATOR_ROOT\n\ndef _canonical_build_plan(root, profile, custom_excludes, **kwargs):\n    global _CANONICAL_GENERATOR_ROOT\n    previous = _CANONICAL_GENERATOR_ROOT\n    _CANONICAL_GENERATOR_ROOT = root\n    try:\n        return _canonical_original_build_plan(root, profile, custom_excludes, **kwargs)\n    finally:\n        _CANONICAL_GENERATOR_ROOT = previous\n\n_core_for_canonical = getattr(_impl, "_core", None)\nif _core_for_canonical is not None:\n    _core_for_canonical.discover_candidates = _canonical_discover_system\n    _core_for_canonical.discover_memory_candidates = _canonical_discover_memory\n    _core_for_canonical.filter_candidates = _canonical_filter_candidates\n    _core_for_canonical.PACKAGE_SET_SCHEMA = _canonical_contract.CURRENT_SCHEMA\n_impl.PACKAGE_SET_SCHEMA = _canonical_contract.CURRENT_SCHEMA\n_canonical_original_build_plan = _impl.build_plan\n_impl.build_plan = _canonical_build_plan\nglobals()["build_plan"] = _canonical_build_plan\nPACKAGE_SET_SCHEMA = _canonical_contract.CURRENT_SCHEMA\n{END}\n'''


        def render(original: str) -> str:
            map_pattern = re.compile(r"_BUNDLED_MODULES = \{.*?\n\}\n\n\ndef _ensure_package", re.S)
            if not map_pattern.search(original):
                raise RuntimeError("cannot locate bundled module map")
            text = map_pattern.sub(generated_map() + "\n\n\ndef _ensure_package", original, count=1)
            block_pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)
            text = block_pattern.sub("", text)
            marker = "\n_v87_install_overrides()\n"
            if marker not in text:
                raise RuntimeError("cannot locate v8.7 override installation marker")
            text = text.replace(marker, marker + "\n" + overlay(), 1)
            return text


        def execute(*, check: bool) -> int:
            current = GENERATOR.read_text(encoding="utf-8")
            wanted = render(current)
            if check:
                if current != wanted:
                    print("Pack Generator bundle is stale. Run build_jazn_pack_generator_bundle.py --write.")
                    return 1
                print("Pack Generator bundle matches all canonical source SHA-256 values.")
                return 0
            GENERATOR.write_text(wanted, encoding="utf-8", newline="\n")
            print(json.dumps(manifest(), ensure_ascii=False, indent=2, sort_keys=True))
            return 0


        def main(argv: Sequence[str] | None = None) -> int:
            parser = argparse.ArgumentParser(allow_abbrev=False)
            mode = parser.add_mutually_exclusive_group(required=True)
            mode.add_argument("--write", action="store_true")
            mode.add_argument("--check", action="store_true")
            ns = parser.parse_args(list(argv) if argv is not None else None)
            return execute(check=bool(ns.check))


        if __name__ == "__main__":
            raise SystemExit(main())
        ''',
    )

    # Bump generator identity before regenerating its bundle.
    generator = ROOT / "tools" / "jazn_pack_generator.py"
    text = generator.read_text(encoding="utf-8")
    text = text.replace('GENERATOR_VERSION = "8.7"', 'GENERATOR_VERSION = "8.8"')
    text = text.replace('SETTINGS_SCHEMA = "jazn_pack_generator_settings/v8.7"', 'SETTINGS_SCHEMA = "jazn_pack_generator_settings/v8.8"')
    generator.write_text(text, encoding="utf-8", newline="\n")
    subprocess.run(["python", "-X", "utf8", "tools/build_jazn_pack_generator_bundle.py", "--write"], cwd=ROOT, check=True)

    # Update hardcoded generator identity tests/docs without weakening assertions.
    for path in (ROOT / "tests").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if '"8.7"' in text or "v8.7" in text:
            text = text.replace('GENERATOR_VERSION == "8.7"', 'GENERATOR_VERSION == "8.8"')
            text = text.replace('SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.7"', 'SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.8"')
            path.write_text(text, encoding="utf-8", newline="\n")

    # ------------------------------------------------------------------
    # 13. Strengthen profile resource explicitly (allowlist + hard deny documented).
    # ------------------------------------------------------------------
    profiles_path = ROOT / "latka_jazn/resources/zip_package_profiles.json"
    profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    for profile in profiles["profiles"]:
        if profile["name"] in {"system", "github_source_safe"}:
            extra = [
                ".git/**", ".codex/**", ".venv/**", "venv/**", ".archives/**",
                "latka_jazn/local_resources/python/environments/**",
                "latka_jazn/local_resources/python/wheelhouse/**",
                "latka_jazn/core/canon/local_private_canon_extension.py",
                "**/*.db", "**/*.sqlite", "**/*.7z", "**/*.rar", "**/*.tar", "**/*.tgz",
            ]
            profile["excludes"] = list(dict.fromkeys([*profile.get("excludes", []), *extra]))
    profiles["truth_boundary"] = (
        "Profiles are declarative allowlists. PackagePlanBuilder applies an additional non-disableable "
        "security policy; .gitignore is never a package security boundary."
    )
    profiles_path.write_text(json.dumps(profiles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # 14. Version bump in same implementation change.
    # ------------------------------------------------------------------
    version_path = ROOT / "latka_jazn/version.py"
    version = version_path.read_text(encoding="utf-8")
    version = re.sub(
        r"# v16\.3\.25\.3\.14 adds.*?\n# existing hardened ZIP/7z/AES-ZIP execution layer and dependency contract\.\n",
        "# v16.3.25.3.15 converges package planning, package-set v3, portable generator sources,\n# offline dependency artifacts, memory transactions, path safety and clean-room release validation.\n",
        version,
        count=1,
    )
    version = version.replace('DISTRIBUTION_VERSION = "16.3.25.3.14"', 'DISTRIBUTION_VERSION = "16.3.25.3.15"')
    version = version.replace('PACKAGE_VERSION = "16.3.25.3.14"', 'PACKAGE_VERSION = "16.3.25.3.15"')
    version = version.replace('PACKAGE_RELEASE_NAME = "archive-tools-understanding-added"', 'PACKAGE_RELEASE_NAME = "package-distribution-convergence"')
    version_path.write_text(version, encoding="utf-8", newline="\n")

    # ------------------------------------------------------------------
    # 15. Permanent regression/acceptance tests.
    # ------------------------------------------------------------------
    write(
        "tests/test_package_distribution_convergence_v16325315.py",
        r'''
        from __future__ import annotations

        import hashlib
        import json
        import os
        import subprocess
        import sys
        import zipfile
        from pathlib import Path

        import pytest

        from latka_jazn.packaging.package_plan import PackagePlanBuilder, package_safety_reason
        from latka_jazn.packaging.package_set_contract import CURRENT_SCHEMA, validate_package_set
        from latka_jazn.packaging.memory_transaction import promote_memory_tree
        from latka_jazn.tools.package_export import export_package
        from latka_jazn.tools.safe_paths import UnsafeRelativePathError, validate_safe_path_set, validate_safe_relative_path

        ROOT = Path(__file__).parents[1]


        def _write(root: Path, rel: str, data: bytes = b"x") -> None:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)


        def test_system_filesystem_plan_hard_blocks_local_private_and_runtime_artifacts(tmp_path: Path) -> None:
            allowed = [
                "run.py", "main.py", "latka_jazn/version.py", "latka_jazn/core/ok.py",
                "AGENTS.md", "README.md", "pyproject.toml", "requirements.txt",
            ]
            blocked = [
                ".codex/test.json", ".venv/pyvenv.cfg",
                "latka_jazn/local_resources/python/environments/e/python.exe",
                "latka_jazn/local_resources/python/wheelhouse/core/demo.whl",
                "latka_jazn/core/canon/local_private_canon_extension.py",
                "memory/private.json", "workspace_runtime/JAZN_ACTIVE_RUNTIME.json",
                ".env", "secret.sqlite3", "nested.zip",
            ]
            for rel in allowed + blocked:
                _write(tmp_path, rel)
            # Copy the canonical profile resource so this is a true filesystem-mode fixture.
            source_profiles = ROOT / "latka_jazn/resources/zip_package_profiles.json"
            target_profiles = tmp_path / "latka_jazn/resources/zip_package_profiles.json"
            target_profiles.parent.mkdir(parents=True, exist_ok=True)
            target_profiles.write_bytes(source_profiles.read_bytes())
            plan = PackagePlanBuilder(tmp_path, "system").build()
            assert set(allowed).issubset(set(plan.paths))
            assert set(blocked).isdisjoint(set(plan.paths))
            for rel in blocked:
                assert package_safety_reason(rel, "system") is not None or rel not in plan.paths


        @pytest.mark.security
        @pytest.mark.parametrize("value", [
            "../memory/x.jsonl", "C:/memory/x.jsonl", "//server/share/file", "file:ads",
            "CON.txt", "aux", "safe/trailing.", "safe/trailing ",
        ])
        def test_path_boundary_rejects_cross_platform_ambiguous_names(value: str) -> None:
            with pytest.raises(UnsafeRelativePathError):
                validate_safe_relative_path(value)


        @pytest.mark.security
        def test_path_inventory_rejects_casefold_collision() -> None:
            with pytest.raises(UnsafeRelativePathError):
                validate_safe_path_set(["Safe/File.txt", "safe/file.TXT"])


        def test_memory_promotion_rolls_back_after_new_tree_promoted(tmp_path: Path) -> None:
            source = tmp_path / "source-memory"; source.mkdir(); _write(source, "new.txt", b"new")
            target = tmp_path / "host" / "memory"; target.mkdir(parents=True); _write(target, "old.txt", b"old")
            workspace = tmp_path / "host" / "workspace_runtime"; workspace.mkdir(parents=True)
            def fail(stage: str) -> None:
                if stage == "after_new_promoted":
                    raise RuntimeError("controlled-failure")
            with pytest.raises(RuntimeError, match="controlled-failure"):
                promote_memory_tree(source_memory=source, target_memory=target, workspace=workspace, fault_injector=fail)
            assert (target / "old.txt").read_bytes() == b"old"
            assert not (target / "new.txt").exists()


        def test_generator_bundle_is_generated_from_current_sources() -> None:
            completed = subprocess.run(
                [sys.executable, "-X", "utf8", "tools/build_jazn_pack_generator_bundle.py", "--check"],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False,
            )
            assert completed.returncode == 0, completed.stdout + completed.stderr
            import tools.jazn_pack_generator as generator
            assert generator.GENERATOR_VERSION == "8.8"
            assert generator.SETTINGS_SCHEMA == "jazn_pack_generator_settings/v8.8"
            manifest = generator._CANONICAL_PACKAGE_BUNDLE_MANIFEST
            for row in manifest.values():
                source = ROOT / row["source_path"]
                assert hashlib.sha256(source.read_bytes()).hexdigest() == row["sha256"]


        def test_package_set_v3_validates_its_plan_and_output_hashes(tmp_path: Path) -> None:
            artifact = tmp_path / "system.zip"; artifact.write_bytes(b"zipbytes")
            out_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
            entries = [{"path": "run.py", "size_bytes": 3, "sha256": hashlib.sha256(b"run").hexdigest(), "classification": "static_project_file"}]
            from latka_jazn.packaging.package_set_contract import build_single_zip_sidecar
            payload = build_single_zip_sidecar(package_name=artifact.name, profile="system", package_version="test", zip_path=artifact, entries=entries)
            assert payload["schema_version"] == CURRENT_SCHEMA
            assert validate_package_set(payload, require_current=True)["outputs"][0]["sha256"] == out_sha
        ''',
    )

    # ------------------------------------------------------------------
    # 16. Permanent clean-room artifact workflow (consumer has no checkout/pip -e).
    # ------------------------------------------------------------------
    write(
        ".github/workflows/package-distribution-cleanroom.yml",
        r'''
        name: package-distribution-cleanroom

        on:
          pull_request:
            branches: [master]
          workflow_dispatch:

        permissions:
          contents: read

        jobs:
          build-system:
            runs-on: ubuntu-24.04
            timeout-minutes: 30
            steps:
              - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5
                with: {fetch-depth: 0}
              - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
                with: {python-version: '3.12'}
              - run: |
                  python -m pip install --upgrade pip
                  python -m pip install -e . pytest
                  python -X utf8 tools/build_jazn_pack_generator_bundle.py --check
                  python -X utf8 run.py package-smoke --profile release --json
                  python -X utf8 run.py release-build --output cleanroom-artifacts/system.zip --json
              - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
                with:
                  name: cleanroom-system
                  path: cleanroom-artifacts/
                  if-no-files-found: error
                  retention-days: 3

          build-dependencies:
            strategy:
              fail-fast: false
              matrix:
                include:
                  - os: ubuntu-24.04
                    alias: linux-x64
                  - os: windows-2025
                    alias: windows-x64
            runs-on: ${{ matrix.os }}
            timeout-minutes: 30
            steps:
              - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5
              - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
                with: {python-version: '3.12'}
              - run: |
                  python -m pip install --upgrade pip
                  python -m pip install -e .
                  python -X utf8 -m latka_jazn.dependencies.release_artifact --root . --output-dir dependency-artifact --python-version 3.12 --platform current --json
              - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
                with:
                  name: cleanroom-deps-${{ matrix.alias }}
                  path: dependency-artifact/
                  if-no-files-found: error
                  retention-days: 3

          consume:
            needs: [build-system, build-dependencies]
            strategy:
              fail-fast: false
              matrix:
                include:
                  - os: ubuntu-24.04
                    alias: linux-x64
                  - os: windows-2025
                    alias: windows-x64
            runs-on: ${{ matrix.os }}
            timeout-minutes: 30
            env:
              PYTHONNOUSERSITE: '1'
              PYTHONPATH: ''
              PIP_NO_INDEX: '1'
              JAZN_ALLOW_NETWORK: '0'
              JAZN_NETWORK_TIME_FIRST: '0'
              JAZN_NETWORK_TIME_IN_TURN: '0'
              JAZN_DICTIONARY_ALLOW_NETWORK: '0'
              JAZN_MODEL_ADAPTER: 'null'
            steps:
              # Deliberately no source checkout and no `pip install -e .` in this job.
              - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065
                with: {python-version: '3.12'}
              - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093
                with: {name: cleanroom-system, path: artifacts/system}
              - uses: actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093
                with:
                  name: cleanroom-deps-${{ matrix.alias }}
                  path: artifacts/deps
              - name: Extract exact artifacts using stdlib only
                shell: python
                run: |
                  import json, pathlib, zipfile
                  root = pathlib.Path('artifacts')
                  system = next((root/'system').glob('system.zip'))
                  bootstrap = root/'bootstrap-source'; bootstrap.mkdir()
                  with zipfile.ZipFile(system) as z: z.extractall(bootstrap)
                  deps_zip = next((root/'deps').glob('*-dependencies-*.zip'))
                  deps_root = root/'dependency-wheelhouse'; deps_root.mkdir()
                  with zipfile.ZipFile(deps_zip) as z: z.extractall(deps_root)
                  print(json.dumps({'system': str(system), 'deps': str(deps_zip), 'bootstrap': str(bootstrap)}))
              - name: Bootstrap dependencies and exact system artifact
                shell: bash
                if: runner.os != 'Windows'
                run: |
                  export JAZN_DEPENDENCY_WHEELHOUSE="$PWD/artifacts/dependency-wheelhouse"
                  python -I artifacts/bootstrap-source/run.py runtime-bootstrap --parts-dir artifacts/system --destination "$RUNNER_TEMP/jazn-active" --no-start-daemon --json
                  python -I "$RUNNER_TEMP/jazn-active/run.py" doctor --root "$RUNNER_TEMP/jazn-active" --json
                  python -I "$RUNNER_TEMP/jazn-active/run.py" start --root "$RUNNER_TEMP/jazn-active" -- --daemon-port 18787
                  python -I "$RUNNER_TEMP/jazn-active/run.py" status --root "$RUNNER_TEMP/jazn-active" --daemon-port 18787 --json
                  printf '%s\n' '{"text":"Działasz?"}' | python -I "$RUNNER_TEMP/jazn-active/run.py" chat-gpt --root "$RUNNER_TEMP/jazn-active" -- --daemon-port 18787
                  python -I "$RUNNER_TEMP/jazn-active/run.py" stop --root "$RUNNER_TEMP/jazn-active" -- --daemon-port 18787
              - name: Bootstrap dependencies and exact system artifact (Windows)
                shell: pwsh
                if: runner.os == 'Windows'
                run: |
                  $env:JAZN_DEPENDENCY_WHEELHOUSE = (Resolve-Path 'artifacts/dependency-wheelhouse').Path
                  $active = Join-Path $env:RUNNER_TEMP 'jazn-active'
                  python -I artifacts/bootstrap-source/run.py runtime-bootstrap --parts-dir artifacts/system --destination $active --no-start-daemon --json
                  python -I (Join-Path $active 'run.py') doctor --root $active --json
                  python -I (Join-Path $active 'run.py') start --root $active -- --daemon-port 18787
                  python -I (Join-Path $active 'run.py') status --root $active --daemon-port 18787 --json
                  '{"text":"Działasz?"}' | python -I (Join-Path $active 'run.py') chat-gpt --root $active -- --daemon-port 18787
                  python -I (Join-Path $active 'run.py') stop --root $active -- --daemon-port 18787
        ''',
    )

    # ------------------------------------------------------------------
    # 17. Documentation truth updates.
    # ------------------------------------------------------------------
    if "jazn_package_set/v2" in read("AGENTS.chatgpt.md"):
        text = read("AGENTS.chatgpt.md")
        text = text.replace(
            "Bieżący sidecar generatora używa schematu `jazn_package_set/v2`; loader zachowuje zgodność z `jazn_package_set/v1`.",
            "Bieżący sidecar generatora używa schematu `jazn_package_set/v3`; loader zachowuje zgodność odczytu z `jazn_package_set/v1` i `jazn_package_set/v2`.",
        )
        text = text.replace(
            "wcześniejszą pamięć zachowuje jako backup pod `workspace_runtime/memory_attach_backups/`.",
            "wcześniejszą pamięć zachowuje atomowo pod `workspace_runtime/memory_attach_backups/` gdy jest to ten sam filesystem; dla zewnętrznego `JAZN_MEMORY_ROOT` używa target-side backupu na tym samym filesystemie i raportuje jego dokładną ścieżkę.",
        )
        (ROOT / "AGENTS.chatgpt.md").write_text(text, encoding="utf-8", newline="\n")

    write(
        "docs/runtime/JAZN_PACKAGE_DISTRIBUTION_CONVERGENCE_V16325315.md",
        '''
        # v16.3.25.3.15 — package distribution convergence

        This release converges system/memory packaging on one `PackagePlanBuilder`,
        one fail-closed path boundary, one `jazn_package_set/v3` writer contract and
        one compatibility reader contract.  `.gitignore` is not a security boundary.

        The portable Pack Generator remains a two-file distribution, but its embedded
        implementation is now generated from checked-in build sources plus the current
        canonical package/path modules.  CI `--check` fails when any source SHA changes
        without regenerating the bundle.

        Runtime Python dependencies are transported as a separate target-specific,
        verified wheelhouse artifact.  A virtual environment is always recreated on the
        target and installed offline with `--no-index --find-links`; an existing `.venv`
        is never packaged.

        Memory attach stages the fully copied tree on the destination filesystem and
        uses local atomic renames for promotion/rollback.  External memory roots no
        longer depend on cross-device `os.replace` into the runtime workspace.

        Legacy oversized memory remains a migration-only input for
        `memory-repack-legacy`; normal system/memory ZIP safety limits are not raised.

        `package-distribution-cleanroom.yml` consumes the actual release ZIP and actual
        dependency artifact in a job with no source checkout and no editable install.
        Package acceptance requires plan/sidecar/manifest/ZIP agreement and a real
        bootstrap → doctor → daemon endpoint → ChatGPT turn → stop cycle.
        ''',
    )

    print("distribution convergence source tree prepared")


if __name__ == "__main__":
    main()
