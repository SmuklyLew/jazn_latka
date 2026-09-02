from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import hashlib
import io
import json
import subprocess
import zipfile

from latka_jazn.core.version_source import read_runtime_version_from_version_py
from latka_jazn.packaging.zip_resource_limits import validate_zip_resources
from latka_jazn.packaging.package_plan import package_safety_reason
from latka_jazn.tools.safe_paths import (
    UnsafeRelativePathError,
    resolve_safe_path,
    resolve_safe_source,
    validate_safe_relative_path,
)
from latka_jazn.version import (
    schema_contract_metadata,
    schema_version,
    schema_version_compatibility,
)

MANIFEST_NAME = "PACKAGE_INTEGRITY_MANIFEST.json"
REQUIRED_STATIC_PATHS = {"SOURCE_PROVENANCE.json", "run.py", "main.py", "latka_jazn/version.py"}
FORBIDDEN_ROOT_NAMES = {
    ".git", ".archives", "memory", "workspace_runtime", "backups", "backups_git",
    "exports", "processed", "requests", "responses", "status", "checkpoints",
    ".pytest_cache", "__pycache__",
}
FORBIDDEN_FILE_NAMES = {
    MANIFEST_NAME, "MANIFEST_CURRENT.json", "VERSION.txt", "RUNTIME_STATE.json",
    "JAZN_ACTIVE_RUNTIME.json", "BOOTSTRAP_JAZN_CURRENT.json",
    "__jazn_pack_generator.lock.json", "__jazn_pack_generator_settings.json",
    "_jazn_pack_generator.before.py",
}
FORBIDDEN_SUFFIXES = {
    ".sqlite", ".sqlite3", ".db", ".db-wal", ".db-shm", ".sqlite-wal", ".sqlite-shm",
    ".zip", ".log", ".tmp", ".temp", ".bak", ".pyc", ".before.py",
}
_VERSION_VARIABLES = ("PACKAGE_VERSION", "__version__", "VERSION", "DISTRIBUTION_VERSION")
_GIT_PROBE_TIMEOUT_SECONDS = 15.0
_GIT_BATCH_TIMEOUT_SECONDS = 60.0


class _GitCommandTimeout(RuntimeError):
    def __init__(self, args: tuple[str, ...], timeout_seconds: float) -> None:
        self.args_tuple = args
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"git command timed out after {timeout_seconds:.1f}s: git {' '.join(args)}"
        )


def _run_git(
    root: Path,
    *args: str,
    text: bool = False,
    encoding: str = "utf-8",
    timeout_seconds: float = _GIT_PROBE_TIMEOUT_SECONDS,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[Any]:
    command = ["git", "-C", str(root), *args]
    try:
        if text:
            return subprocess.run(
                command,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding=encoding,
                errors="replace",
                check=False,
                timeout=timeout_seconds,
            )
        if input_bytes is not None:
            return subprocess.run(
                command,
                capture_output=True,
                input=input_bytes,
                check=False,
                timeout=timeout_seconds,
            )
        return subprocess.run(
            command,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise _GitCommandTimeout(tuple(args), timeout_seconds) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_checkout_head_for_verification(root: Path) -> tuple[str | None, str]:
    """Return a trusted HEAD for canonical verification or a fallback reason.

    A clean Git checkout may contain platform-specific worktree bytes, such as
    CRLF produced by Git on Windows, while the release manifest intentionally
    protects canonical Git blobs. Canonical verification is allowed only for
    the exact repository root, a clean index/worktree and ordinary tracked
    files without ``assume-unchanged`` or ``skip-worktree`` flags. Every Git
    probe has a finite timeout so startup cannot block indefinitely.
    """

    try:
        top_level = _run_git(
            root, "rev-parse", "--show-toplevel", text=True, encoding="utf-8"
        )
        if top_level.returncode != 0:
            return None, "not_a_git_checkout"
        try:
            repository_root = Path(top_level.stdout.strip()).resolve()
        except (OSError, RuntimeError):
            return None, "git_root_unresolvable"
        if repository_root != root:
            return None, "not_a_git_checkout"

        unstaged = _run_git(root, "diff", "--quiet", "--ignore-submodules", "--")
        if unstaged.returncode not in {0, 1}:
            return None, "git_diff_failed"
        if unstaged.returncode == 1:
            return None, "dirty"

        staged = _run_git(
            root, "diff", "--cached", "--quiet", "--ignore-submodules", "--"
        )
        if staged.returncode not in {0, 1}:
            return None, "git_diff_failed"
        if staged.returncode == 1:
            return None, "dirty"

        untracked = _run_git(root, "ls-files", "--others", "--exclude-standard", "-z")
        if untracked.returncode != 0:
            return None, "git_untracked_probe_failed"
        if untracked.stdout:
            return None, "dirty"

        assume_flags = _run_git(root, "ls-files", "-v", "-z")
        if assume_flags.returncode != 0:
            return None, "git_index_flags_unavailable"
        for record in assume_flags.stdout.split(b"\0"):
            tag = record[:1]
            if tag and tag.isalpha() and tag.islower():
                return None, "assume_unchanged_present"

        stage_flags = _run_git(root, "ls-files", "-t", "-z")
        if stage_flags.returncode != 0:
            return None, "git_index_flags_unavailable"
        if any(record[:1] == b"S" for record in stage_flags.stdout.split(b"\0") if record):
            return None, "skip_worktree_present"

        head = _run_git(root, "rev-parse", "HEAD", text=True, encoding="ascii")
        value = head.stdout.strip().lower()
        if (
            head.returncode != 0
            or len(value) != 40
            or any(ch not in "0123456789abcdef" for ch in value)
        ):
            return None, "git_head_invalid"
        return value, "clean"
    except _GitCommandTimeout:
        return None, "git_timeout"
    except OSError:
        return None, "git_unavailable"


def _git_tree_blob_oids(root: Path, head: str) -> tuple[dict[str, str], set[str]]:
    completed = _run_git(
        root,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        head,
        timeout_seconds=_GIT_BATCH_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git ls-tree failed: {stderr}")

    blob_oids: dict[str, str] = {}
    tree_paths: set[str] = set()
    for record in completed.stdout.split(b"\0"):
        if not record:
            continue
        try:
            metadata, raw_path = record.split(b"\t", 1)
            _mode, object_type, object_id = metadata.split(b" ", 2)
        except ValueError as exc:
            raise RuntimeError("git ls-tree returned malformed output") from exc
        relative = raw_path.decode("utf-8", errors="surrogateescape").replace("\\", "/")
        tree_paths.add(relative)
        if object_type == b"blob":
            blob_oids[relative] = object_id.decode("ascii")
    return blob_oids, tree_paths


def _git_blob_bytes_batch(
    root: Path,
    head: str,
    relatives: Iterable[str],
) -> tuple[dict[str, bytes], set[str]]:
    """Read canonical HEAD blobs with one long-lived ``git cat-file`` process.

    The former implementation spawned one ``git cat-file blob`` process for
    every manifest entry. On Windows that could take minutes or block startup
    indefinitely. This implementation resolves paths once and streams all
    unique object IDs through ``git cat-file --batch`` under a finite timeout.
    """

    blob_oids, tree_paths = _git_tree_blob_oids(root, head)
    requested = list(dict.fromkeys(str(item) for item in relatives))
    unique_oids = list(
        dict.fromkeys(blob_oids[item] for item in requested if item in blob_oids)
    )
    if not unique_oids:
        return {}, tree_paths

    completed = _run_git(
        root,
        "cat-file",
        "--batch",
        input_bytes=("\n".join(unique_oids) + "\n").encode("ascii"),
        timeout_seconds=_GIT_BATCH_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git cat-file --batch failed: {stderr}")

    stream = io.BytesIO(completed.stdout)
    by_oid: dict[str, bytes] = {}
    for expected_oid in unique_oids:
        header = stream.readline()
        parts = header.rstrip(b"\n").split(b" ")
        if len(parts) != 3:
            raise RuntimeError("git cat-file --batch returned malformed header")
        actual_oid = parts[0].decode("ascii", errors="replace")
        object_type = parts[1]
        try:
            size = int(parts[2])
        except ValueError as exc:
            raise RuntimeError("git cat-file --batch returned invalid size") from exc
        if actual_oid != expected_oid or object_type != b"blob" or size < 0:
            raise RuntimeError("git cat-file --batch returned an unexpected object")
        raw = stream.read(size)
        if len(raw) != size or stream.read(1) != b"\n":
            raise RuntimeError("git cat-file --batch returned truncated content")
        by_oid[expected_oid] = raw

    return (
        {relative: by_oid[oid] for relative, oid in blob_oids.items() if oid in by_oid},
        tree_paths,
    )


def path_is_forbidden(relative: str) -> bool:
    try:
        rel = validate_safe_relative_path(relative)
    except UnsafeRelativePathError:
        return True
    if rel == MANIFEST_NAME:
        return True
    return package_safety_reason(rel, "system") is not None


def _git_name_set(root: Path, *args: str) -> set[str]:
    try:
        completed = _run_git(root, *args, text=True, encoding="utf-8")
    except _GitCommandTimeout as exc:
        raise RuntimeError(str(exc)) from exc
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return {line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()}


def _git_paths(root: Path) -> tuple[list[str], list[str]]:
    candidates = _git_name_set(root, "ls-files", "--cached", "--others", "--exclude-standard")
    deleted = _git_name_set(root, "diff", "--name-only", "--diff-filter=D", "--")
    deleted |= _git_name_set(root, "diff", "--cached", "--name-only", "--diff-filter=D", "--")
    # A release candidate is built from the current worktree. Paths that Git
    # explicitly reports as deleted are intentional members of that state and
    # must not be mistaken for a truncated checkout. Any other absent tracked
    # or unignored path remains a hard error below.
    candidates -= deleted
    ordered = sorted(candidates)
    missing = [path for path in ordered if not (root / path).is_file()]
    return ordered, missing


def _walk_paths(root: Path) -> Iterable[str]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path.relative_to(root).as_posix()


def _normalized_overrides(overrides: Mapping[str, bytes] | None) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for raw_path, raw_bytes in dict(overrides or {}).items():
        try:
            relative = validate_safe_relative_path(str(raw_path))
        except UnsafeRelativePathError as exc:
            raise RuntimeError(f"unsafe manifest override path: {raw_path!r}") from exc
        if path_is_forbidden(relative):
            raise RuntimeError(f"manifest override points at a forbidden path: {relative}")
        result[relative] = bytes(raw_bytes)
    return result


def _selected_paths(
    root: Path,
    relative_paths: Iterable[str] | None,
    overrides: Mapping[str, bytes] | None = None,
) -> list[str]:
    override_paths = set(overrides or {})
    if relative_paths is None:
        if (root / ".git").exists():
            candidates, missing = _git_paths(root)
            if missing:
                raise RuntimeError(f"tracked/unignored files missing from working tree: {missing[:10]}")
            return sorted(set(candidates) | override_paths)
        return sorted(set(_walk_paths(root)) | override_paths)

    selected: set[str] = set()
    missing: list[str] = []
    for raw in relative_paths:
        try:
            relative = validate_safe_relative_path(str(raw))
        except UnsafeRelativePathError:
            continue
        if relative in override_paths:
            selected.add(relative)
            continue
        try:
            path = resolve_safe_source(root, relative)
        except UnsafeRelativePathError:
            continue
        if not path.is_file():
            missing.append(relative)
            continue
        selected.add(relative)
    if missing:
        raise RuntimeError(f"selected package files missing from source tree: {missing[:10]}")
    return sorted(selected)


def build_package_integrity_manifest(
    root: Path | str,
    *,
    relative_paths: Iterable[str] | None = None,
    overrides: Mapping[str, bytes] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build the canonical static manifest.

    ``relative_paths`` narrows the manifest to the exact immutable package plan.
    ``overrides`` supplies immutable in-memory bytes for selected paths, primarily
    ``SOURCE_PROVENANCE.json`` generated from canonical Git objects. This lets an
    exporter freeze provenance and manifest without mutating the source checkout.
    ``generated_at_utc`` may pin the manifest timestamp to the provenance commit,
    making repeated previews and builds byte-for-byte deterministic. The manifest
    file itself and runtime/memory artifacts remain excluded.
    """

    root = Path(root).resolve()
    override_map = _normalized_overrides(overrides)
    runtime_version = read_runtime_version_from_version_py(root)
    if not runtime_version:
        raise RuntimeError("latka_jazn/version.py is missing or invalid")
    candidates = _selected_paths(root, relative_paths, override_map)
    files: list[dict[str, Any]] = []
    excluded: list[str] = []
    for relative in candidates:
        try:
            relative = validate_safe_relative_path(relative)
        except UnsafeRelativePathError:
            excluded.append(str(relative))
            continue
        if path_is_forbidden(relative):
            excluded.append(relative)
            continue
        if relative in override_map:
            raw = override_map[relative]
            size_bytes = len(raw)
            sha256 = hashlib.sha256(raw).hexdigest()
        else:
            try:
                path = resolve_safe_source(root, relative)
            except UnsafeRelativePathError:
                excluded.append(relative)
                continue
            size_bytes = path.stat().st_size
            sha256 = sha256_file(path)
        files.append({
            "path": relative,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "mutable_runtime": False,
            "classification": "static_project_file",
            "archive": False,
            "hash_policy": "sha256_file_bytes",
        })
    present = {entry["path"] for entry in files}
    missing_required = sorted(REQUIRED_STATIC_PATHS - present)
    if missing_required:
        raise RuntimeError(f"required static files missing: {missing_required}")
    generated_at = str(generated_at_utc or datetime.now(timezone.utc).isoformat())
    return {
        "schema_version": schema_version("package_integrity_manifest"),
        "schema_contract": schema_contract_metadata("package_integrity_manifest"),
        "version": runtime_version,
        "runtime_version": runtime_version,
        "package_version": runtime_version,
        "release_version": runtime_version,
        "artifact_identity": {
            "runtime_version": runtime_version,
            "package_version": runtime_version,
            "release_version": runtime_version,
        },
        "legacy_aliases": {"version": "release_version"},
        "generated_at_utc": generated_at,
        "updated_at_utc": generated_at,
        "start_file": "run.py",
        "file_count": len(files),
        "static_file_count": len(files),
        "mutable_runtime_file_count": 0,
        "runtime_mutable_file_count": 0,
        "excluded_file_count": len(excluded),
        "runtime_state_file": "RUNTIME_STATE.json",
        "runtime_memory_split_policy": {
            "static_manifest": "PACKAGE_INTEGRITY_MANIFEST.json protects static project files only.",
            "runtime_state": "Runtime state, memory, SQLite and workspace_runtime are excluded.",
        },
        "excluded_policy": {
            "roots": sorted(FORBIDDEN_ROOT_NAMES),
            "file_names": sorted(FORBIDDEN_FILE_NAMES),
            "suffixes": sorted(FORBIDDEN_SUFFIXES),
        },
        "truth_boundary": (
            "The manifest hashes the exact static package plan including SOURCE_PROVENANCE.json. "
            "Its contract schema is versioned independently from the runtime/release identity. "
            "It excludes itself, Git history, memory, runtime state, SQLite, archives, secrets, logs, "
            "backups, generator state and temporary files."
        ),
        "files": files,
        "excluded_files": excluded,
        "deferred_hash_files": [],
    }


def serialize_package_integrity_manifest(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_package_integrity_manifest(
    root: Path | str,
    *,
    relative_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    payload = build_package_integrity_manifest(root, relative_paths=relative_paths)
    path = root / MANIFEST_NAME
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(serialize_package_integrity_manifest(payload))
    try:
        temp.replace(path)
    except PermissionError:
        # Windows can deny replacement of an existing tracked file even when
        # overwriting its contents is allowed. Preserve the same complete
        # serialized payload and remove only the generator-owned temp file.
        path.write_bytes(temp.read_bytes())
        temp.unlink(missing_ok=True)
    return payload


def _manifest_entries(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    entries = payload.get("files")
    if not isinstance(entries, list):
        return None
    return [entry for entry in entries if isinstance(entry, dict)]


def verify_package_integrity_manifest(root: Path | str) -> dict[str, Any]:
    root = Path(root).resolve()
    path = root / MANIFEST_NAME
    errors: list[dict[str, Any]] = []
    if not path.is_file():
        return {"ok": False, "configuration_error": True, "errors": [{"code": "manifest_missing"}]}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"ok": False, "configuration_error": True, "errors": [{"code": "manifest_invalid_json", "detail": repr(exc)}]}
    entries = _manifest_entries(payload) if isinstance(payload, dict) else None
    if entries is None:
        return {"ok": False, "configuration_error": True, "errors": [{"code": "manifest_files_missing"}]}

    manifest_schema_compatibility = schema_version_compatibility(
        "package_integrity_manifest",
        str(payload.get("schema_version") or ""),
    )
    if not manifest_schema_compatibility.get("compatible"):
        errors.append({
            "code": "unsupported_manifest_schema",
            "observed": manifest_schema_compatibility.get("observed_schema_version"),
            "expected": manifest_schema_compatibility.get("current_schema_version"),
        })

    git_head, worktree_state = _git_checkout_head_for_verification(root)
    verification_basis = "canonical_git_head_blobs" if git_head else "filesystem_bytes"
    seen: set[str] = set()
    prepared: list[tuple[dict[str, Any], str, Path]] = []
    for entry in entries:
        raw_relative = entry.get("path")
        relative = str(raw_relative) if raw_relative is not None else ""
        try:
            canonical = validate_safe_relative_path(relative)
            file_path = resolve_safe_path(root, canonical)
        except UnsafeRelativePathError as exc:
            errors.append({"code": "unsafe_manifest_path", "path": relative, "detail": str(exc)})
            continue
        if canonical in seen or path_is_forbidden(canonical):
            errors.append({"code": "invalid_or_duplicate_manifest_path", "path": canonical})
            continue
        seen.add(canonical)
        if not file_path.is_file():
            errors.append({"code": "file_missing", "path": canonical})
            continue
        prepared.append((entry, canonical, file_path))

    git_blobs: dict[str, bytes] = {}
    git_tree_paths: set[str] | None = None
    git_batch_failed = False
    if git_head:
        try:
            git_blobs, git_tree_paths = _git_blob_bytes_batch(
                root, git_head, [canonical for _entry, canonical, _file_path in prepared]
            )
        except (_GitCommandTimeout, OSError, RuntimeError) as exc:
            errors.append({"code": "git_blob_batch_failed", "detail": str(exc)})
            git_batch_failed = True

    for entry, canonical, file_path in prepared:
        if git_head:
            if git_batch_failed:
                continue
            raw = git_blobs.get(canonical)
            if raw is None:
                errors.append({"code": "git_blob_missing", "path": canonical})
                continue
            size = len(raw)
            digest = hashlib.sha256(raw).hexdigest()
        else:
            size = file_path.stat().st_size
            digest = sha256_file(file_path)
        if size != int(entry.get("size_bytes", -1)):
            errors.append({"code": "size_mismatch", "path": canonical})
        if digest != str(entry.get("sha256") or ""):
            errors.append({"code": "sha256_mismatch", "path": canonical})
    for required in sorted(REQUIRED_STATIC_PATHS):
        if required not in seen:
            errors.append({"code": "required_path_unprotected", "path": required})
    # Old manifests predate a complete inventory contract. Preserve their
    # hash verification for recovery compatibility, but require exact static
    # membership whenever the manifest declares file_count (all current packs).
    if "file_count" in payload:
        declared_count: object = payload.get("file_count")
        if isinstance(declared_count, bool):
            normalized_declared_count = -1
        elif isinstance(declared_count, int):
            normalized_declared_count = declared_count
        elif isinstance(declared_count, str):
            try:
                normalized_declared_count = int(declared_count)
            except ValueError:
                normalized_declared_count = -1
        else:
            normalized_declared_count = -1
        if normalized_declared_count != len(entries):
            errors.append(
                {
                    "code": "manifest_file_count_mismatch",
                    "declared": declared_count,
                    "actual": len(entries),
                }
            )
        try:
            if git_head:
                candidate_paths = git_tree_paths or set()
                if git_tree_paths is None and not git_batch_failed:
                    candidate_paths = _git_name_set(root, "ls-tree", "-r", "--name-only", git_head)
            else:
                candidate_paths = set(_walk_paths(root))
        except (OSError, RuntimeError) as exc:
            errors.append({"code": "static_file_inventory_failed", "detail": str(exc)})
            candidate_paths = set()
        actual_static_paths: set[str] = set()
        for relative in candidate_paths:
            try:
                canonical = validate_safe_relative_path(relative)
            except UnsafeRelativePathError:
                continue
            if not path_is_forbidden(canonical):
                actual_static_paths.add(canonical)
        for unexpected in sorted(actual_static_paths - seen):
            errors.append({"code": "unexpected_static_file", "path": unexpected})
    if git_head and not git_batch_failed:
        version_bytes = git_blobs.get("latka_jazn/version.py")
        runtime_version = _version_from_python_bytes(version_bytes) if version_bytes is not None else None
    elif git_head:
        runtime_version = None
    else:
        runtime_version = read_runtime_version_from_version_py(root)
    if not runtime_version or str(payload.get("runtime_version") or payload.get("version") or "") != runtime_version:
        errors.append({"code": "version_mismatch"})
    return {
        "schema_version": schema_version("package_integrity_verification"),
        "ok": not errors,
        "configuration_error": False,
        "manifest_path": str(path),
        "manifest_sha256": sha256_file(path),
        "checked_file_count": len(entries),
        "errors": errors,
        "manifest_schema_compatibility": manifest_schema_compatibility,
        "verification_basis": verification_basis,
        "worktree_state": worktree_state,
        "git_head": git_head,
    }


def _version_from_python_bytes(raw: bytes) -> str | None:
    """Read the canonical full package version from archived ``version.py``.

    ``PACKAGE_VERSION`` and ``PACKAGE_RELEASE_NAME`` are separate literal fields
    in the authoritative module. ``PACKAGE_VERSION_FULL`` is commonly an f-string,
    so it cannot be recovered by reading constants alone and must be reconstructed.
    """

    try:
        tree = ast.parse(raw.decode("utf-8-sig"))
    except Exception:
        return None
    values: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    values[target.id] = node.value.value.strip()
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                values[node.target.id] = value.value.strip()

    package_version = values.get("PACKAGE_VERSION", "").strip()
    release_name = values.get("PACKAGE_RELEASE_NAME", "").strip()
    if package_version:
        if release_name and not package_version.lower().endswith(f"-{release_name}".lower()):
            return f"{package_version}-{release_name}"
        return package_version

    for name in _VERSION_VARIABLES:
        value = values.get(name)
        if value:
            return value
    return None


def verify_package_integrity_manifest_in_zips(
    zip_paths: Path | str | Iterable[Path | str],
    *,
    allowed_unprotected_prefixes: Iterable[str] = (),
) -> dict[str, Any]:
    """Verify one ZIP or a set of independent ZIP volumes against the embedded manifest."""

    if isinstance(zip_paths, (str, Path)):
        paths = [Path(zip_paths).resolve()]
    else:
        paths = [Path(path).resolve() for path in zip_paths]
    allowed_prefixes = tuple(
        validate_safe_relative_path(str(prefix).rstrip("/")) + "/"
        for prefix in allowed_unprotected_prefixes
        if str(prefix).strip()
    )
    errors: list[dict[str, Any]] = []
    members: dict[str, tuple[Path, zipfile.ZipInfo]] = {}
    manifest_bytes: bytes | None = None

    for zip_path in paths:
        if not zip_path.is_file():
            errors.append({"code": "zip_missing", "path": str(zip_path)})
            continue
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                validate_zip_resources(archive)
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    try:
                        canonical = validate_safe_relative_path(info.filename)
                    except UnsafeRelativePathError as exc:
                        errors.append({"code": "unsafe_zip_member", "path": info.filename, "detail": str(exc)})
                        continue
                    if canonical in members:
                        errors.append({"code": "duplicate_zip_member", "path": canonical})
                        continue
                    members[canonical] = (zip_path, info)
                    if canonical == MANIFEST_NAME:
                        manifest_bytes = archive.read(info)
        except Exception as exc:
            errors.append({"code": "zip_open_failed", "path": str(zip_path), "detail": repr(exc)})

    payload: dict[str, Any] = {}
    if manifest_bytes is None:
        errors.append({"code": "manifest_missing"})
        entries: list[dict[str, Any]] = []
    else:
        try:
            decoded = json.loads(manifest_bytes.decode("utf-8-sig"))
            if not isinstance(decoded, dict):
                raise ValueError("manifest is not a JSON object")
            payload = decoded
        except Exception as exc:
            errors.append({"code": "manifest_invalid_json", "detail": repr(exc)})
        entries = _manifest_entries(payload) or []
        if not isinstance(payload.get("files"), list):
            errors.append({"code": "manifest_files_missing"})

    manifest_schema_compatibility = schema_version_compatibility(
        "package_integrity_manifest",
        str(payload.get("schema_version") or ""),
    )
    if payload and not manifest_schema_compatibility.get("compatible"):
        errors.append({
            "code": "unsupported_manifest_schema",
            "observed": manifest_schema_compatibility.get("observed_schema_version"),
            "expected": manifest_schema_compatibility.get("current_schema_version"),
        })

    listed: set[str] = set()
    checked = 0
    for entry in entries:
        relative = str(entry.get("path") or "")
        try:
            canonical = validate_safe_relative_path(relative)
        except UnsafeRelativePathError as exc:
            errors.append({"code": "unsafe_manifest_path", "path": relative, "detail": str(exc)})
            continue
        if canonical in listed or path_is_forbidden(canonical):
            errors.append({"code": "invalid_or_duplicate_manifest_path", "path": canonical})
            continue
        listed.add(canonical)
        member = members.get(canonical)
        if member is None:
            errors.append({"code": "file_missing", "path": canonical})
            continue
        zip_path, info = member
        expected_size = int(entry.get("size_bytes", -1))
        if info.file_size != expected_size:
            errors.append({"code": "size_mismatch", "path": canonical, "expected": expected_size, "actual": info.file_size})
        digest = hashlib.sha256()
        with zipfile.ZipFile(zip_path, "r") as archive:
            validate_zip_resources(archive)
            with archive.open(info, "r") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        actual_hash = digest.hexdigest()
        expected_hash = str(entry.get("sha256") or "")
        if actual_hash != expected_hash:
            errors.append({"code": "sha256_mismatch", "path": canonical, "expected": expected_hash, "actual": actual_hash})
        checked += 1

    for required in sorted(REQUIRED_STATIC_PATHS):
        if required not in listed:
            errors.append({"code": "required_path_unprotected", "path": required})

    version_member = members.get("latka_jazn/version.py")
    archive_version = None
    if version_member is not None:
        version_zip, version_info = version_member
        with zipfile.ZipFile(version_zip, "r") as archive:
            archive_version = _version_from_python_bytes(archive.read(version_info))
    manifest_version = str(payload.get("runtime_version") or payload.get("version") or "")
    if not archive_version or manifest_version != archive_version:
        errors.append({"code": "version_mismatch", "manifest": manifest_version, "archive": archive_version})

    allowed = set(listed)
    allowed.add(MANIFEST_NAME)
    for relative in sorted(set(members) - allowed):
        if any(relative.startswith(prefix) for prefix in allowed_prefixes):
            continue
        errors.append({"code": "unexpected_zip_member", "path": relative})

    return {
        "schema_version": schema_version("package_integrity_zip_verification"),
        "ok": not errors,
        "zip_paths": [str(path) for path in paths],
        "manifest_runtime_version": manifest_version,
        "archive_runtime_version": archive_version,
        "manifest_schema_compatibility": manifest_schema_compatibility,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest() if manifest_bytes is not None else None,
        "checked_file_count": checked,
        "member_count": len(members),
        "errors": errors,
    }
