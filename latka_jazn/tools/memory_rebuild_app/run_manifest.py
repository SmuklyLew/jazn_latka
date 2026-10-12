from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import hashlib
import json
import os
import uuid

from .report_sanitizer import sanitize_report


RUN_MANIFEST_SCHEMA = "jazn_memory_rebuild_run_manifest/v4"
_PROTOCOL_NAMES = ("test00", "test01", "test02", "test03", "test04", "final")
_DRAFT_PRIVATE_NAME = "run-manifest.draft.private.json"
_DRAFT_SANITIZED_NAME = "run-manifest.draft.sanitized.json"
_FINAL_PRIVATE_NAME = "run-manifest.private.json"
_FINAL_SANITIZED_NAME = "run-manifest.sanitized.json"
_PRIVATE_RESULT_KEYS = {
    "conversation_id",
    "conversation_ids",
    "requested_conversation_ids",
    "query",
    "content",
    "text",
    "title",
    "raw_json",
    "source_record_id",
}


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
            results={name: {"outcome": "NOT RUN", "ok": False} for name in _PROTOCOL_NAMES},
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunManifest":
        if payload.get("schema_version") != RUN_MANIFEST_SCHEMA:
            raise ValueError("unsupported RunManifest schema")

        def required_text(name: str) -> str:
            value = payload.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"RunManifest {name} must be a non-empty string")
            return value

        completed_value = payload.get("completed_at")
        if completed_value is not None and not isinstance(completed_value, str):
            raise ValueError("RunManifest completed_at must be a string or null")

        inventory_value = payload.get("source_bundle_inventory")
        if not isinstance(inventory_value, list) or any(
            not isinstance(item, Mapping) for item in inventory_value
        ):
            raise ValueError("RunManifest source_bundle_inventory must be a list of objects")
        roles_value = payload.get("source_roles")
        digests_value = payload.get("source_sha256")
        results_value = payload.get("results")
        validation_value = payload.get("validation_results")
        if not isinstance(roles_value, Mapping) or not isinstance(digests_value, Mapping):
            raise ValueError("RunManifest source roles and digests must be objects")
        if not isinstance(results_value, Mapping) or set(results_value) != set(_PROTOCOL_NAMES):
            raise ValueError("RunManifest results must contain the exact protocol chain")
        if any(not isinstance(item, Mapping) for item in results_value.values()):
            raise ValueError("RunManifest protocol results must be objects")
        if not isinstance(validation_value, Mapping):
            raise ValueError("RunManifest validation_results must be an object")

        warnings_value = payload.get("warnings")
        blockers_value = payload.get("blockers")
        decisions_value = payload.get("operator_decisions")
        if not isinstance(warnings_value, list) or not isinstance(blockers_value, list):
            raise ValueError("RunManifest warnings and blockers must be lists")
        if not isinstance(decisions_value, list) or any(
            not isinstance(item, Mapping) for item in decisions_value
        ):
            raise ValueError("RunManifest operator_decisions must be a list of objects")

        source_union_fingerprint = payload.get("source_union_fingerprint")
        database_sha256 = payload.get("database_sha256")
        if source_union_fingerprint is not None and not isinstance(
            source_union_fingerprint, str
        ):
            raise ValueError("RunManifest source_union_fingerprint must be a string or null")
        if database_sha256 is not None and not isinstance(database_sha256, str):
            raise ValueError("RunManifest database_sha256 must be a string or null")

        return cls(
            run_id=required_text("run_id"),
            started_at=required_text("started_at"),
            completed_at=completed_value,
            tool_version=required_text("tool_version"),
            system_version=required_text("system_version"),
            base_commit=required_text("base_commit"),
            source_bundle_inventory=tuple(dict(item) for item in inventory_value),
            source_roles={str(key): str(value) for key, value in roles_value.items()},
            source_sha256={str(key): str(value) for key, value in digests_value.items()},
            results={str(key): dict(value) for key, value in results_value.items()},
            source_union_fingerprint=source_union_fingerprint,
            database_sha256=database_sha256,
            warnings=tuple(str(item) for item in warnings_value),
            blockers=tuple(str(item) for item in blockers_value),
            operator_decisions=tuple(dict(item) for item in decisions_value),
            validation_results=dict(validation_value),
        )

    @classmethod
    def load_draft(
        cls,
        directory: str | Path,
        *,
        run_id: str,
        tool_version: str,
        system_version: str,
        base_commit: str,
    ) -> "RunManifest":
        root = Path(directory).expanduser().resolve()
        final_paths = (root / _FINAL_PRIVATE_NAME, root / _FINAL_SANITIZED_NAME)
        if any(path.exists() for path in final_paths):
            raise RuntimeError("sealed RunManifest cannot be resumed")
        private = root / _DRAFT_PRIVATE_NAME
        sanitized = root / _DRAFT_SANITIZED_NAME
        if not private.is_file() or not sanitized.is_file():
            raise FileNotFoundError("complete RunManifest draft pair is required for resume")
        private_payload = json.loads(private.read_text(encoding="utf-8"))
        sanitized_payload = json.loads(sanitized.read_text(encoding="utf-8"))
        if not isinstance(private_payload, Mapping) or not isinstance(
            sanitized_payload, Mapping
        ):
            raise ValueError("RunManifest draft files must contain JSON objects")
        manifest = cls.from_dict(private_payload)
        expected = {
            "run_id": run_id,
            "tool_version": tool_version,
            "system_version": system_version,
            "base_commit": base_commit,
        }
        actual = {
            "run_id": manifest.run_id,
            "tool_version": manifest.tool_version,
            "system_version": manifest.system_version,
            "base_commit": manifest.base_commit,
        }
        mismatches = [name for name in expected if actual[name] != expected[name]]
        if mismatches:
            raise ValueError(
                "RunManifest draft provenance mismatch: " + ", ".join(mismatches)
            )
        if manifest.completed_at is not None:
            raise RuntimeError("completed RunManifest cannot be resumed")
        if dict(sanitized_payload) != manifest.sanitized_dict():
            raise ValueError("RunManifest draft private/sanitized pair mismatch")
        return manifest

    def with_sources(self, inventory: tuple[Mapping[str, Any], ...]) -> "RunManifest":
        if self.completed_at is not None:
            raise RuntimeError("completed RunManifest is immutable")
        roles: dict[str, str] = {}
        digests: dict[str, str] = {}
        for index, item in enumerate(inventory, start=1):
            key = str(item.get("relative_path") or item.get("path") or index)
            roles[key] = str(item.get("role") or "unknown_sidecar")
            digests[key] = str(item.get("sha256") or "")
        return replace(
            self,
            source_bundle_inventory=tuple(dict(item) for item in inventory),
            source_roles=roles,
            source_sha256=digests,
        )

    def with_result(self, name: str, result: Mapping[str, Any]) -> "RunManifest":
        if self.completed_at is not None:
            raise RuntimeError("completed RunManifest is immutable")
        updated = dict(self.results)
        updated[str(name)] = dict(result)
        return replace(self, results=updated)

    def with_checkpoint(
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
            source_union_fingerprint=source_union_fingerprint,
            database_sha256=database_sha256,
            warnings=warnings,
            blockers=blockers,
            operator_decisions=operator_decisions,
            validation_results=dict(validation_results or {}),
        )

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
        checkpoint = self.with_checkpoint(
            source_union_fingerprint=source_union_fingerprint,
            database_sha256=database_sha256,
            warnings=warnings,
            blockers=blockers,
            operator_decisions=operator_decisions,
            validation_results=dict(validation_results or {}),
        )
        return replace(checkpoint, completed_at=_utc_now())

    def to_dict(self) -> dict[str, Any]:
        payload = {
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
        normalized = json.loads(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        )
        if not isinstance(normalized, dict):
            raise TypeError("RunManifest serialization must produce a JSON object")
        return normalized

    def sanitized_dict(self) -> dict[str, Any]:
        value = _sanitize_manifest_value(sanitize_report(self.to_dict()))
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
        if self.completed_at is None:
            raise RuntimeError("open RunManifest cannot be written as final")
        root = Path(directory).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        private = root / _FINAL_PRIVATE_NAME
        sanitized = root / _FINAL_SANITIZED_NAME
        if private.exists() or sanitized.exists():
            raise FileExistsError("RunManifest artifacts are immutable and already exist")
        _write_atomic(sanitized, self.sanitized_dict())
        _write_atomic(private, self.to_dict())
        return {"private": str(private), "sanitized": str(sanitized)}

    def write_draft(self, directory: str | Path) -> dict[str, str]:
        if self.completed_at is not None:
            raise RuntimeError("completed RunManifest cannot be written as a draft")
        root = Path(directory).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        private = root / _DRAFT_PRIVATE_NAME
        sanitized = root / _DRAFT_SANITIZED_NAME
        _write_atomic(sanitized, self.sanitized_dict())
        _write_atomic(private, self.to_dict())
        return {"draft_private": str(private), "draft_sanitized": str(sanitized)}

    @staticmethod
    def remove_draft(directory: str | Path) -> None:
        root = Path(directory).expanduser().resolve()
        for name in (_DRAFT_PRIVATE_NAME, _DRAFT_SANITIZED_NAME):
            path = root / name
            if path.exists():
                path.unlink()


def _sanitize_manifest_value(value: Any, *, key: str = "") -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            child_key = str(raw_key)
            if child_key in _PRIVATE_RESULT_KEYS or child_key.endswith("_conversation_id"):
                serialized = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                result[child_key + "_removed"] = True
                result[child_key + "_sha256"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            else:
                result[child_key] = _sanitize_manifest_value(item, key=child_key)
        return result
    if isinstance(value, (list, tuple)):
        return [_sanitize_manifest_value(item, key=key) for item in value]
    return value


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


__all__ = ["RUN_MANIFEST_SCHEMA", "RunManifest"]
