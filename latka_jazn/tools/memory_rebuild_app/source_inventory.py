from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
import hashlib
import json
import os
import re
import stat
import zipfile

from .models import SourceSpec

_DATE_RE = re.compile(r"(?<!\d)(20\d{2})[._-](0[1-9]|1[0-2])[._-](0[1-9]|[12]\d|3[01])(?!\d)")
_CHAT_MEMBER_RE = re.compile(r"(^|/)(conversations(?:[-_]\d+)?\.json)$", re.IGNORECASE)
_LAYERED_NAMES = {
    "affective.jsonl",
    "continuity.jsonl",
    "episodic.jsonl",
    "procedural.jsonl",
    "reflections.jsonl",
    "semantic.jsonl",
    "truth_audits.jsonl",
    "turn_logic_audit.jsonl",
}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".svg"}
_REFERENCE_SUFFIXES = {".txt", ".md", ".pdf", ".docx", ".odt", ".rtf"}


@dataclass(slots=True)
class SourceInspection:
    path: str
    exists: bool
    is_file: bool
    size_bytes: int | None = None
    sha256: str | None = None
    suffix: str = ""
    role: str = "unknown"
    source_family: str = ""
    truth_domain: str = "unknown"
    pipeline: str = "catalog_only"
    status: str = "uninspected"
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exists and self.is_file and not any(item.startswith("blocking:") for item in self.warnings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "exists": self.exists,
            "is_file": self.is_file,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "suffix": self.suffix,
            "role": self.role,
            "source_family": self.source_family,
            "truth_domain": self.truth_domain,
            "pipeline": self.pipeline,
            "status": self.status,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }

    def to_source_spec(self, *, approved: bool = False) -> SourceSpec:
        return SourceSpec.create(
            self.path,
            role=self.role,
            source_family=self.source_family,
            truth_domain=self.truth_domain,
            pipeline=self.pipeline,
            approved=approved,
            size_bytes=self.size_bytes,
            sha256=self.sha256,
            status=self.status,
            warnings=list(self.warnings),
            metadata=dict(self.metadata),
        )


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_member(name: str) -> PurePosixPath:
    return PurePosixPath(name.replace("\\", "/"))


def _unsafe_member_reason(name: str) -> str | None:
    member = _normalized_member(name)
    raw = str(member)
    if not raw or raw == ".":
        return "empty_member"
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        return "absolute_path"
    if any(part == ".." for part in member.parts):
        return "path_traversal"
    return None


def _zip_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def inspect_zip(path: Path, *, verify_crc: bool = False) -> dict[str, Any]:
    names: list[str] = []
    casefold_seen: set[str] = set()
    exact_seen: set[str] = set()
    duplicates: list[str] = []
    case_collisions: list[str] = []
    unsafe: list[dict[str, str]] = []
    symlinks: list[str] = []
    conversation_members: list[str] = []
    html_members: list[str] = []
    image_members: list[str] = []
    json_members: list[str] = []
    package_profiles: list[str] = []

    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        for info in infos:
            name = info.filename
            names.append(name)
            key = name.casefold()
            if name in exact_seen:
                duplicates.append(name)
            exact_seen.add(name)
            if key in casefold_seen and name not in duplicates:
                case_collisions.append(name)
            casefold_seen.add(key)
            reason = _unsafe_member_reason(name)
            if reason:
                unsafe.append({"name": name, "reason": reason})
            if _zip_symlink(info):
                symlinks.append(name)
            normalized = str(_normalized_member(name))
            lower = normalized.casefold()
            if _CHAT_MEMBER_RE.search(normalized):
                conversation_members.append(name)
            if lower.endswith((".html", ".htm")):
                html_members.append(name)
            if Path(lower).suffix in _IMAGE_SUFFIXES:
                image_members.append(name)
            if lower.endswith((".json", ".jsonl", ".ndjson")):
                json_members.append(name)
            if lower.endswith(".package.json"):
                try:
                    payload = json.loads(archive.read(info).decode("utf-8-sig", errors="strict"))
                    profile = str(payload.get("profile") or "").strip()
                    if profile:
                        package_profiles.append(profile)
                except (UnicodeDecodeError, json.JSONDecodeError, OSError, KeyError):
                    pass
        crc_error = archive.testzip() if verify_crc else None

    return {
        "member_count": len(names),
        "total_uncompressed_bytes": sum(info.file_size for info in infos),
        "conversation_members": sorted(conversation_members),
        "html_members": sorted(html_members),
        "image_member_count": len(image_members),
        "json_member_count": len(json_members),
        "duplicate_members": sorted(set(duplicates)),
        "case_collisions": sorted(set(case_collisions)),
        "unsafe_members": unsafe,
        "symlink_members": sorted(set(symlinks)),
        "package_profiles": sorted(set(package_profiles)),
        "crc_checked": bool(verify_crc),
        "crc_error_member": crc_error,
    }


def _sniff_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    result: dict[str, Any] = {"json_type": type(payload).__name__}
    if isinstance(payload, dict):
        keys = sorted(str(key) for key in payload.keys())
        result["top_level_keys"] = keys[:100]
        if isinstance(payload.get("entries"), list):
            result["entry_count"] = len(payload["entries"])
        if isinstance(payload.get("mapping"), dict):
            result["conversation_mapping"] = True
    elif isinstance(payload, list):
        result["item_count"] = len(payload)
        if payload and isinstance(payload[0], dict):
            result["first_item_keys"] = sorted(str(key) for key in payload[0].keys())[:100]
    return result


def _sniff_jsonl(path: Path, *, max_lines: int = 25) -> dict[str, Any]:
    valid = 0
    invalid = 0
    keys: set[str] = set()
    samples: list[str] = []
    try:
        with path.open("r", encoding="utf-8-sig", errors="strict") as stream:
            for line in stream:
                if not line.strip():
                    continue
                if valid + invalid >= max_lines:
                    break
                try:
                    payload = json.loads(line)
                    valid += 1
                    if isinstance(payload, dict):
                        keys.update(str(key) for key in payload.keys())
                except json.JSONDecodeError:
                    invalid += 1
                    samples.append(line[:160])
    except (OSError, UnicodeDecodeError):
        return {}
    return {
        "sampled_nonempty_lines": valid + invalid,
        "sample_valid_json": valid,
        "sample_invalid_json": invalid,
        "sample_keys": sorted(keys),
        "invalid_samples": samples[:3],
    }


def _source_family(path: Path) -> str:
    match = _DATE_RE.search(path.name) or _DATE_RE.search(str(path.parent))
    if match:
        return "chatgpt-" + "-".join(match.groups())
    stem = path.stem.casefold()
    stem = re.sub(r"(?:[-_.](?:part|chunk|copy|export)?\d+)$", "", stem)
    return stem or path.name.casefold()


def _classification(path: Path, metadata: dict[str, Any]) -> tuple[str, str, str]:
    name = path.name.casefold()
    suffix = path.suffix.casefold()
    zip_meta = metadata.get("zip", {})
    if suffix == ".zip":
        if zip_meta.get("conversation_members"):
            return "chatgpt_export", "conversation_event", "memory_rebuild"
        if zip_meta.get("package_profiles") == ["memory"]:
            return "approved_l0", "source_recorded", "catalog_only"
        if int(zip_meta.get("image_member_count") or 0) > 0 and not zip_meta.get("json_member_count"):
            return "visual_asset", "symbolic", "catalog_only"
        return "approved_l0", "source_recorded", "catalog_only"
    if suffix in {".html", ".htm"}:
        return "chatgpt_html_export", "conversation_event", "html_control"
    if suffix in {".jsonl", ".ndjson"}:
        if any(token in name for token in ("journal", "dziennik")):
            return "journal", "source_recorded", "memory_rebuild"
        if any(token in name for token in ("runtime_event", "turn_checkpoint", "conversation_turn")):
            return "runtime_event_ledger", "runtime_claim", "catalog_only"
        if name in _LAYERED_NAMES or any(token in name for token in ("episodic", "semantic", "affective", "reflection", "procedural", "continuity", "truth_audit")):
            return "layered_memory", "assistant_claim", "catalog_only"
        return "approved_l0", "source_recorded", "catalog_only"
    if suffix == ".json":
        json_meta = metadata.get("json", {})
        keys = set(json_meta.get("top_level_keys") or [])
        first_keys = set(json_meta.get("first_item_keys") or [])
        if any(token in name for token in ("journal", "dziennik")) or "entries" in keys:
            return "journal", "source_recorded", "memory_rebuild"
        if "mapping" in first_keys or json_meta.get("conversation_mapping"):
            return "chatgpt_export", "conversation_event", "memory_rebuild"
        if any(token in name for token in ("identity", "canon", "emotion", "memory", "episodic", "semantic")):
            return "layered_memory", "assistant_claim", "catalog_only"
        return "approved_l0", "source_recorded", "catalog_only"
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        return "sqlite_snapshot", "technical", "sqlite_baseline"
    if suffix in _IMAGE_SUFFIXES:
        return "visual_asset", "symbolic", "catalog_only"
    if suffix in _REFERENCE_SUFFIXES:
        return "reference_document", "technical", "catalog_only"
    return "unknown", "unknown", "excluded"


def inspect_source(
    value: str | Path,
    *,
    calculate_sha256: bool = True,
    verify_zip_crc: bool = False,
) -> SourceInspection:
    path = Path(value).expanduser().resolve()
    result = SourceInspection(path=str(path), exists=path.exists(), is_file=path.is_file(), suffix=path.suffix.casefold())
    result.source_family = _source_family(path)
    if not path.exists():
        result.status = "missing"
        result.warnings.append("blocking:source_missing")
        return result
    if not path.is_file():
        result.status = "not_file"
        result.warnings.append("blocking:source_not_file")
        return result

    result.size_bytes = path.stat().st_size
    if calculate_sha256:
        result.sha256 = sha256_file(path)
    metadata: dict[str, Any] = {}
    try:
        if path.suffix.casefold() == ".zip":
            metadata["zip"] = inspect_zip(path, verify_crc=verify_zip_crc)
            zip_meta = metadata["zip"]
            if zip_meta.get("unsafe_members"):
                result.warnings.append("blocking:zip_unsafe_paths")
            if zip_meta.get("symlink_members"):
                result.warnings.append("blocking:zip_symlinks")
            if zip_meta.get("duplicate_members") or zip_meta.get("case_collisions"):
                result.warnings.append("blocking:zip_duplicate_members")
            if zip_meta.get("crc_checked") and zip_meta.get("crc_error_member"):
                result.warnings.append("blocking:zip_crc_failed")
        elif path.suffix.casefold() == ".json":
            metadata["json"] = _sniff_json(path)
        elif path.suffix.casefold() in {".jsonl", ".ndjson"}:
            metadata["jsonl"] = _sniff_jsonl(path)
            if metadata["jsonl"].get("sample_invalid_json"):
                result.warnings.append("jsonl_sample_contains_invalid_records")
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        result.warnings.append(f"blocking:inspection_error:{type(exc).__name__}")
        metadata["inspection_error"] = str(exc)

    result.metadata = metadata
    result.role, result.truth_domain, result.pipeline = _classification(path, metadata)
    result.status = "ready" if result.ok else "blocked"
    return result


def inspect_sources(
    paths: Iterable[str | Path],
    *,
    calculate_sha256: bool = True,
    verify_zip_crc: bool = False,
) -> list[SourceInspection]:
    return [
        inspect_source(path, calculate_sha256=calculate_sha256, verify_zip_crc=verify_zip_crc)
        for path in paths
    ]


__all__ = [
    "SourceInspection",
    "inspect_source",
    "inspect_sources",
    "inspect_zip",
    "sha256_file",
]
