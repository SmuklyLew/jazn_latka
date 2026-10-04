from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterator
import json
import zipfile

from latka_jazn.tools.chat_export_reader import probe_json_source_kind

SOURCE_KINDS = (
    "chat", "journal", "music", "episodic", "semantic", "affective", "procedural",
    "provenance_ledger", "runtime_events", "legacy_sqlite", "reference",
)


class DuplicateJsonKeyError(ValueError):
    """Raised when repeated JSON object keys would silently discard evidence."""


def _unique_object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKeyError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def load_json_strict(path: str | Path) -> Any:
    source = Path(path).expanduser().resolve()
    return json.loads(
        source.read_text(encoding="utf-8-sig"),
        object_pairs_hook=_unique_object_pairs,
    )


_AFFECTIVE_SCHEMA_MARKERS = (
    '"latka_ai_pamiec"',
    '"pytania_z_ciszy"',
    '"relacje"',
    '"projekty_meta"',
)


def _looks_like_legacy_affective_json(raw: str) -> bool:
    return sum(marker in raw for marker in _AFFECTIVE_SCHEMA_MARKERS) >= 2


def _repair_legacy_json_syntax(raw: str) -> tuple[str, list[str]]:
    """Repair only unambiguous separators outside JSON strings.

    The source file is never modified.  Repairs are returned as evidence and are
    limited to trailing commas and a missing comma between adjacent object
    elements inside an array.
    """

    output: list[str] = []
    notes: list[str] = []
    stack: list[str] = []
    in_string = False
    escaped = False
    length = len(raw)

    def next_nonspace(index: int) -> str | None:
        while index < length and raw[index].isspace():
            index += 1
        return raw[index] if index < length else None

    for index, char in enumerate(raw):
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            output.append(char)
            continue
        if char in "[{":
            stack.append(char)
            output.append(char)
            continue
        if char in "]}":
            if stack:
                stack.pop()
            output.append(char)
            if (
                char == "}"
                and stack
                and stack[-1] == "["
                and next_nonspace(index + 1) == "{"
            ):
                output.append(",")
                notes.append(f"inserted_missing_array_comma_after_offset:{index}")
            continue
        if char == "," and next_nonspace(index + 1) in {"]", "}"}:
            notes.append(f"removed_trailing_comma_at_offset:{index}")
            continue
        output.append(char)

    return "".join(output), notes


def load_legacy_affective_json(path: str | Path) -> tuple[Any, dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    raw = source.read_text(encoding="utf-8-sig")
    if not _looks_like_legacy_affective_json(raw):
        raise ValueError("legacy_affective_schema_markers_missing")

    repaired, repairs = _repair_legacy_json_syntax(raw)
    duplicate_keys: list[str] = []

    def merge_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key not in result:
                result[key] = value
                continue
            duplicate_keys.append(key)
            previous = result[key]
            if isinstance(previous, list) and isinstance(value, list):
                result[key] = [*previous, *value]
            else:
                left = previous if isinstance(previous, list) else [previous]
                right = value if isinstance(value, list) else [value]
                result[key] = [*left, *right]
        return result

    payload = json.loads(repaired, object_pairs_hook=merge_pairs)
    return payload, {
        "repaired": bool(repairs or duplicate_keys),
        "syntax_repairs": repairs,
        "duplicate_keys_merged": sorted(set(duplicate_keys)),
        "source_bytes_preserved": True,
    }


@dataclass(slots=True, frozen=True)
class SourceProbe:
    path: str
    kind: str
    confidence: float
    reasons: tuple[str, ...]
    sampled_records: int = 0
    schema_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def iter_jsonl_objects(path: Path, *, limit: int | None = None) -> Iterator[dict[str, Any]]:
    seen = 0
    with path.open("r", encoding="utf-8-sig", errors="strict", newline="") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_no}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL line {line_no} is not an object")
            yield value
            seen += 1
            if limit is not None and seen >= limit:
                return


def _sample_jsonl(path: Path, limit: int = 8) -> list[dict[str, Any]]:
    return list(iter_jsonl_objects(path, limit=limit))


def _name_hints(path: Path) -> set[str]:
    name = path.as_posix().casefold()
    result: set[str] = set()
    hints = {
        "runtime_events": ("runtime_event", "runtime-events"),
        "provenance_ledger": ("source_origin_ledger", "provenance", "truth_audit", "turn_logic_audit", "requirements_ledger"),
        "episodic": ("episodic", "episode"),
        "semantic": ("semantic", "knowledge"),
        "affective": ("affective", "emotion", "emocj"),
        "procedural": ("procedural", "procedure", "procedur"),
        "journal": ("dziennik", "journal"),
        "music": ("analizy_utwor", "music_anal"),
    }
    for kind, markers in hints.items():
        if any(marker in name for marker in markers):
            result.add(kind)
    return result


def _keys(samples: list[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for row in samples:
        result.update(str(key).casefold() for key in row)
    return result


def _classify_records(path: Path, samples: list[dict[str, Any]]) -> SourceProbe:
    hints = _name_hints(path)
    keys = _keys(samples)
    reasons: list[str] = []
    scores: dict[str, int] = {kind: 0 for kind in SOURCE_KINDS}
    for hint in hints:
        scores[hint] += 4
        reasons.append(f"path_hint:{hint}")
    rules = {
        "runtime_events": {"event_type", "turn_id", "trace_id", "runtime_event", "event_id"},
        "provenance_ledger": {"source_sha256", "source_path", "source_type", "origin", "provenance"},
        "episodic": {"episode_id", "episodic", "memory_id", "event_time", "timestamp"},
        "semantic": {"fact", "subject", "predicate", "object", "semantic", "statement"},
        "affective": {"emotions", "feelings", "affect", "emocje", "uczucia", "reflection"},
        "procedural": {"procedure", "steps", "rule", "instruction", "procedural"},
        "journal": {"entry_id", "title", "content", "wpis", "treść", "tresc"},
        "chat": {"mapping", "current_node", "conversation_id"},
    }
    for kind, expected in rules.items():
        hits = len(keys & expected)
        scores[kind] += hits * 2
        if hits:
            reasons.append(f"schema_keys:{kind}:{hits}")
    winner = max(scores, key=lambda candidate: scores[candidate])
    score = scores[winner]
    if score <= 0:
        winner = "reference"
    confidence = 0.2 if winner == "reference" else min(0.99, 0.45 + score * 0.07)
    return SourceProbe(str(path), winner, confidence, tuple(reasons), len(samples), tuple(sorted(keys))[:64])


def _probe_zip(path: Path) -> SourceProbe:
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name.casefold() for name in archive.namelist()[:10000]]
    except (OSError, zipfile.BadZipFile) as exc:
        return SourceProbe(str(path), "reference", 0.0, (f"invalid_zip:{type(exc).__name__}",))
    if any("memory_package_manifest" in name or "raw_memory_manifest" in name for name in names):
        return SourceProbe(str(path), "reference", 0.95, ("zip_memory_package_requires_explicit_attach",))
    if any(name.endswith("conversations.json") for name in names):
        return SourceProbe(str(path), "chat", 0.98, ("zip_member:conversations.json",))
    chat_html_names = {"chat.html", "chatgpt.html", "chat_export.html", "chatgpt_export.html"}
    if any(Path(name).name in chat_html_names for name in names):
        return SourceProbe(str(path), "chat", 0.9, ("zip_member:explicit_chat_html",))
    return SourceProbe(str(path), "reference", 0.5, ("zip_unknown_schema",))


def probe_source(path: str | Path) -> SourceProbe:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    suffix = source.suffix.casefold()
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        return SourceProbe(str(source), "legacy_sqlite", 1.0, ("sqlite_extension",))
    if suffix in {".html", ".htm"}:
        return SourceProbe(str(source), "chat", 0.95, ("html_chat_export",))
    if suffix == ".zip":
        return _probe_zip(source)
    if suffix in {".jsonl", ".ndjson"}:
        samples = _sample_jsonl(source)
        return _classify_records(source, samples)
    if suffix == ".json":
        name_hints = _name_hints(source)
        if "music" in name_hints:
            return SourceProbe(str(source), "music", 0.95, ("path_hint:music",))
        try:
            if probe_json_source_kind(source) == "conversation":
                return SourceProbe(str(source), "chat", 0.98, ("chat_export_probe",))
        except Exception:
            pass
        if source.stat().st_size > 64 * 1024 * 1024:
            return SourceProbe(str(source), "reference", 0.4, ("large_json_requires_explicit_type",))
        try:
            payload = load_json_strict(source)
            recovery: dict[str, Any] | None = None
        except (OSError, UnicodeError, json.JSONDecodeError, DuplicateJsonKeyError) as exc:
            try:
                payload, recovery = load_legacy_affective_json(source)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                return SourceProbe(
                    str(source),
                    "reference",
                    0.0,
                    (f"invalid_json:{type(exc).__name__}:{exc}",),
                )
        if isinstance(payload, dict) and isinstance(payload.get("analizy"), list):
            return SourceProbe(str(source), "music", 0.99, ("json_schema:analizy",))
        if isinstance(payload, dict) and {
            "latka_ai_pamiec", "pytania_z_ciszy", "relacje", "projekty_meta",
        } & set(payload):
            reasons = ["json_schema:legacy_affective_memory"]
            if recovery and recovery.get("repaired"):
                reasons.append("legacy_json_recovery_applied")
            return SourceProbe(
                str(source),
                "affective",
                0.99 if not recovery else 0.97,
                tuple(reasons),
                schema_keys=tuple(sorted(str(key).casefold() for key in payload))[:64],
            )
        if isinstance(payload, dict) and isinstance(payload.get("entries"), list):
            samples = [item for item in payload["entries"][:8] if isinstance(item, dict)]
            probe = _classify_records(source, samples)
            if probe.kind == "reference":
                return SourceProbe(str(source), "journal", 0.8, ("json_schema:entries",), len(samples), probe.schema_keys)
            return probe
        if isinstance(payload, list):
            samples = [item for item in payload[:8] if isinstance(item, dict)]
            return _classify_records(source, samples)
    return SourceProbe(str(source), "reference", 0.2, ("unsupported_or_unknown_schema",))


__all__ = [
    "DuplicateJsonKeyError",
    "SOURCE_KINDS",
    "SourceProbe",
    "iter_jsonl_objects",
    "load_json_strict",
    "load_legacy_affective_json",
    "probe_source",
]
