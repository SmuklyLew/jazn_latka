from __future__ import annotations

import json
import os
from typing import Any

PROFILE_CHOICES: tuple[str, ...] = ("system", "dual", "memory")
PACK_PROFILE_CHOICES: tuple[str, ...] = PROFILE_CHOICES + ("combined",)
MEMORY_SQLITE_MEMBER_MAX_BYTES = int(
    os.environ.get("JAZN_MEMORY_PACKAGE_SQLITE_MEMBER_MAX_BYTES", str(1024 * 1024 * 1024))
)
MEMORY_TRANSPORT_CONTRACT = "jazn_memory_package_transport/v1"

PROFILE_DISPLAY = {
    "dual": "SYSTEM + PAMIĘĆ (2 OSOBNE ZIP-y)",
    "system": "SYSTEM",
    "memory": "PAMIĘĆ",
    "combined": "SYSTEM + PAMIĘĆ (legacy combined)",
}
PROFILE_DESCRIPTIONS = {
    "dual": "Tworzy dwie niezależne paczki: SYSTEM bez memory/ oraz osobną PAMIĘĆ profile=memory gotową do późniejszego memory-attach.",
    "system": "Pakuje wyłącznie kod i pliki statyczne systemu, bez memory/ i bez workspace_runtime/.",
    "memory": "Pakuje wyłącznie pamięć jako niezależny transport, z bezpiecznymi snapshotami SQLite i segmentacją dużych JSONL.",
    "combined": "Tryb zgodności wstecznej dla programmatic PackOptions: system i pamięć w jednym zestawie ZIP.",
}


def apply(impl: Any) -> None:
    """Apply the v16.0.1 package policy without rewriting the stable v8.5 core."""

    if getattr(impl, "_JAZN_V1601_POLICY_APPLIED", False):
        return
    core = impl._core

    impl.PROFILE_CHOICES = PROFILE_CHOICES
    impl.PACK_PROFILE_CHOICES = PACK_PROFILE_CHOICES
    impl.PROFILE_DISPLAY = PROFILE_DISPLAY
    impl.PROFILE_DESCRIPTIONS = PROFILE_DESCRIPTIONS
    impl.MEMORY_SQLITE_MEMBER_MAX_BYTES = MEMORY_SQLITE_MEMBER_MAX_BYTES
    impl.MEMORY_TRANSPORT_CONTRACT = MEMORY_TRANSPORT_CONTRACT
    core.PROFILE_CHOICES = PROFILE_CHOICES
    core.PROFILE_DISPLAY = PROFILE_DISPLAY
    core.PROFILE_DESCRIPTIONS = PROFILE_DESCRIPTIONS

    original_parser = core.parser
    original_choose_format = core.choose_format
    original_snapshot_sqlite_entry = impl._snapshot_sqlite_entry
    original_build_memory_plan = impl.build_memory_plan
    original_sidecar_payload = impl.sidecar_payload

    def parser() -> Any:
        parsed = original_parser()
        for action in getattr(parsed, "_actions", []):
            choices = getattr(action, "choices", None)
            if not isinstance(choices, dict):
                continue
            pack_parser = choices.get("pack")
            if pack_parser is None:
                continue
            for pack_action in getattr(pack_parser, "_actions", []):
                if getattr(pack_action, "dest", None) == "profile":
                    pack_action.choices = PACK_PROFILE_CHOICES
                    break
        return parsed

    def choose_format(requested: str, plan: Any, part_size: int) -> str:
        if requested in {"independent", "binary"}:
            return requested
        if getattr(plan, "profile", None) == "memory":
            return "independent"
        return original_choose_format(requested, plan, part_size)

    def snapshot_sqlite_entry(root: Any, relative: str, snapshot_root: Any) -> tuple[Any, dict[str, Any]]:
        entry, database = original_snapshot_sqlite_entry(root, relative, snapshot_root)
        sqlite_limit = int(getattr(impl, "MEMORY_SQLITE_MEMBER_MAX_BYTES", MEMORY_SQLITE_MEMBER_MAX_BYTES))
        if int(entry.size_bytes) > sqlite_limit:
            raise core.PackError(
                f"SQLite snapshot exceeds transport member limit for {relative}: "
                f"{entry.size_bytes}>{sqlite_limit}. "
                "Shard/roll the database before packaging; binary splitting a live SQLite file is not allowed."
            )
        return entry, database

    def build_memory_plan(*args: Any, **kwargs: Any) -> Any:
        plan = original_build_memory_plan(*args, **kwargs)
        independent_contract = kwargs.get("independent_contract")
        if independent_contract is False:
            return plan
        manifest_relative = str(getattr(core, "MEMORY_PACKAGE_MANIFEST", "memory/MEMORY_PACKAGE_MANIFEST.json"))
        for index, entry in enumerate(plan.entries):
            if entry.relative != manifest_relative or entry.virtual_bytes is None:
                continue
            payload = json.loads(entry.virtual_bytes.decode("utf-8"))
            if str(payload.get("schema_version") or "") != "jazn_memory_package_manifest/v3":
                break
            raw_limit = int(getattr(impl, "MEMORY_RAW_SEGMENT_MAX_BYTES"))
            sqlite_limit = int(getattr(impl, "MEMORY_SQLITE_MEMBER_MAX_BYTES", MEMORY_SQLITE_MEMBER_MAX_BYTES))
            payload["package_member_limit_bytes"] = max(raw_limit, sqlite_limit)
            payload["raw_segment_member_limit_bytes"] = raw_limit
            payload["sqlite_snapshot_member_limit_bytes"] = sqlite_limit
            payload["transport_contract"] = MEMORY_TRANSPORT_CONTRACT
            plan.entries[index] = core.virtual_entry(
                manifest_relative,
                core.serialize_json(payload),
                "memory_package_manifest",
            )
            plan.entries.sort(key=lambda item: item.relative)
            break
        return plan

    def sidecar_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = original_sidecar_payload(*args, **kwargs)
        plan = args[1] if len(args) > 1 else kwargs.get("plan")
        outputs = args[5] if len(args) > 5 else kwargs.get("outputs", ())
        base_zip_name = args[0] if args else kwargs.get("base_zip_name", "memory.zip")
        if getattr(plan, "profile", None) == "memory":
            payload.update(
                {
                    "memory_transport_contract": MEMORY_TRANSPORT_CONTRACT,
                    "cloud_attach_compatible": True,
                    "cloud_object_layout": {
                        "kind": "flat_package_set",
                        "provider": "s3_compatible",
                        "required_objects": [str(getattr(item, "filename", "")) for item in outputs],
                        "sidecar": f"{base_zip_name}.package.json",
                    },
                }
            )
        return payload

    impl.parser = parser
    impl.choose_format = choose_format
    impl._snapshot_sqlite_entry = snapshot_sqlite_entry
    impl.build_memory_plan = build_memory_plan
    impl.sidecar_payload = sidecar_payload
    core.parser = parser
    core.choose_format = choose_format
    core.build_memory_plan = build_memory_plan
    core.sidecar_payload = sidecar_payload
    impl._JAZN_V1601_POLICY_APPLIED = True
