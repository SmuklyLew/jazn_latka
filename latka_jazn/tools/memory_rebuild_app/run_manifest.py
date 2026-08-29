from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import os
import uuid

from .report_sanitizer import sanitize_report


RUN_MANIFEST_SCHEMA = "jazn_memory_rebuild_run_manifest/v4"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class RunManifest:
    run_id: str
    started_at: str
    completed_at: str | None
    tool_version: str
    system_version: str
    base_commit: str
    source_bundle_inventory: tuple[Mapping[str, Any], ...] = ()
    source_roles: Mapping[str, str] = field(default_factory=dict)
    source_sha256: Mapping[str, str] = field(default_factory=dict)
    results: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    source_union_fingerprint: str | None = None
    database_sha256: str | None = None
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    operator_decisions: tuple[Mapping[str, Any], ...] = ()
    validation_results: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def begin(
        cls,
        *,
        tool_version: str,
        system_version: str,
        base_commit: str,
        source_bundle_inventory: tuple[Mapping[str, Any], ...] = (),
        source_roles: Mapping[str, str] | None = None,
        source_sha256: Mapping[str, str] | None = None,
        run_id: str | None = None,
    ) -> "RunManifest":
        return cls(
            run_id=run_id or str(uuid.uuid4()),
            started_at=_utc_now(),
            completed_at=None,
            tool_version=tool_version,
            system_version=system_version,
            base_commit=base_commit,
            source_bundle_inventory=source_bundle_inventory,
            source_roles=dict(source_roles or {}),
            source_sha256=dict(source_sha256 or {}),
        )

    def with_result(self, name: str, result: Mapping[str, Any]) -> "RunManifest":
        if self.completed_at is not None:
            raise RuntimeError("completed RunManifest is immutable")
        updated = dict(self.results)
        updated[str(name)] = dict(result)
        return replace(self, results=updated)

    def complete(
        self,
        *,
        source_union_fingerprint: str | None = None,
        database_sha256: str | None = None,
        warnings: tuple[str, ...] = (),
        blockers: tuple[str, ...] = (),
        operator_decisions: tuple[Mapping[str, Any], ...] = (),
        validation_results: Mapping[str, Any] | None = None,
    ) -> "RunManifest":
        if self.completed_at is not None:
            raise RuntimeError("completed RunManifest is immutable")
        return replace(
            self,
            completed_at=_utc_now(),
            source_union_fingerprint=source_union_fingerprint,
            database_sha256=database_sha256,
            warnings=warnings,
            blockers=blockers,
            operator_decisions=operator_decisions,
            validation_results=dict(validation_results or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RUN_MANIFEST_SCHEMA,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "tool_version": self.tool_version,
            "system_version": self.system_version,
            "base_commit": self.base_commit,
            "source_bundle_inventory": [dict(item) for item in self.source_bundle_inventory],
            "source_roles": dict(self.source_roles),
            "source_sha256": dict(self.source_sha256),
            "results": {key: dict(value) for key, value in self.results.items()},
            "source_union_fingerprint": self.source_union_fingerprint,
            "database_sha256": self.database_sha256,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "operator_decisions": [dict(item) for item in self.operator_decisions],
            "validation_results": dict(self.validation_results),
        }

    def sanitized_dict(self) -> dict[str, Any]:
        value = sanitize_report(self.to_dict())
        assert isinstance(value, dict)
        value["source_bundle_inventory"] = [
            {
                "role": item.get("role"),
                "sha256": item.get("sha256"),
                "size_bytes": item.get("size_bytes"),
            }
            for item in self.source_bundle_inventory
        ]
        value["source_roles"] = {
            str(index): role for index, role in enumerate(self.source_roles.values(), start=1)
        }
        value["source_sha256"] = {
            str(index): digest for index, digest in enumerate(self.source_sha256.values(), start=1)
        }
        return value

    def write_once(self, directory: str | Path) -> dict[str, str]:
        root = Path(directory).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        private = root / "run-manifest.private.json"
        sanitized = root / "run-manifest.sanitized.json"
        if private.exists() or sanitized.exists():
            raise FileExistsError("RunManifest artifacts are immutable and already exist")
        _write_once(private, self.to_dict())
        _write_once(sanitized, self.sanitized_dict())
        return {"private": str(private), "sanitized": str(sanitized)}


def _write_once(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


__all__ = ["RUN_MANIFEST_SCHEMA", "RunManifest"]
