from __future__ import annotations

"""Common, format-neutral model produced by every Memory Rebuild adapter."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Protocol
import hashlib
import json

from .settings import MemoryRebuildSettings
from .source_detection import SourceProbe


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_file(path: Path, *, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class IntermediateRecord:
    logical_key: str
    source_record_id: str
    record_kind: str
    content: str
    title: str = ""
    event_time_start: str | None = None
    event_time_end: str | None = None
    timestamp_status: str = "missing"
    conversation_id: str | None = None
    role: str | None = None
    truth_status: str = "source_recorded"
    importance: float = 0.5
    raw: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.logical_key.strip():
            raise ValueError("IntermediateRecord.logical_key nie może być pusty")
        if not self.source_record_id.strip():
            raise ValueError("IntermediateRecord.source_record_id nie może być pusty")
        if not self.record_kind.strip():
            raise ValueError("IntermediateRecord.record_kind nie może być pusty")
        if not self.content.strip():
            raise ValueError("IntermediateRecord.content nie może być pusty")
        if not 0.0 <= float(self.importance) <= 1.0:
            raise ValueError("IntermediateRecord.importance musi mieścić się w zakresie 0..1")

    @property
    def content_sha256(self) -> str:
        payload = canonical_json({
            "title": self.title,
            "content": self.content,
            "event_time_start": self.event_time_start,
            "event_time_end": self.event_time_end,
            "role": self.role,
            "truth_status": self.truth_status,
            "raw": self.raw,
        })
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


RecordFactory = Callable[[], Iterator[IntermediateRecord]]


@dataclass(frozen=True, slots=True)
class PreparedSource:
    adapter_id: str
    source_kind: str
    source_sha256: str
    source_name: str
    source_member: str | None
    metadata: Mapping[str, Any]
    record_factory: RecordFactory
    native_projection: str

    def iter_records(self) -> Iterator[IntermediateRecord]:
        return self.record_factory()


class ImportAdapter(Protocol):
    adapter_id: str

    def supports(self, path: Path, probe: SourceProbe) -> bool: ...

    def prepare(
        self,
        path: Path,
        probe: SourceProbe,
        settings: MemoryRebuildSettings,
    ) -> PreparedSource: ...


__all__ = [
    "ImportAdapter", "IntermediateRecord", "PreparedSource", "RecordFactory",
    "canonical_json", "sha256_file",
]
