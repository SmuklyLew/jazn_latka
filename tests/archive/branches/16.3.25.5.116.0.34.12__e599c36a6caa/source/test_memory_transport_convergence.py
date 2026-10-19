from __future__ import annotations

import hashlib
import json
from pathlib import Path

from latka_jazn.bootstrap import chatgpt_recovery
from latka_jazn.cli import build_parser
from latka_jazn.core.host_operations import build_host_operation_target_argv
from latka_jazn.packaging.generator_v2_compat import (
    discover_generator_sidecar,
    materialize_generator_v2_compat,
    memory_package_requires_v3_repack,
)


def _generator_payload(
    *,
    content: str,
    logical_name: str,
    payload_bytes: bytes,
    source_entries: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "jazn_pack_generator_package/v2",
        "package_version": "16.3.25.5.88.0",
        "content": content,
        "archive": {
            "logical_filename": logical_name,
            "logical_size_bytes": len(payload_bytes),
            "logical_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        },
        "split": {"parts": []},
        "source": {"entries": source_entries or []},
    }


def _write_generator_package(
    root: Path,
    *,
    content: str,
    logical_name: str,
    payload_bytes: bytes,
    source_entries: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    payload = _generator_payload(
        content=content,
        logical_name=logical_name,
        payload_bytes=payload_bytes,
        source_entries=source_entries,
    )
    (root / logical_name).write_bytes(payload_bytes)
    (root / f"{logical_name}.package.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return payload


def test_generator_v2_discovery_filters_system_and_memory_before_ambiguity(
    tmp_path: Path,
) -> None:
    _write_generator_package(
        tmp_path,
        content="system",
        logical_name="jazn.system.zip",
        payload_bytes=b"system-bytes",
    )
    _write_generator_package(
        tmp_path,
        content="memory",
        logical_name="jazn.memory.zip",
        payload_bytes=b"memory-bytes",
    )

    system = discover_generator_sidecar(
        tmp_path,
        allowed_contents={"system", "system+memory"},
    )
    memory = discover_generator_sidecar(
        tmp_path,
        allowed_contents={"memory"},
    )

    assert system is not None
    assert system[1]["content"] == "system"
    assert memory is not None
    assert memory[1]["content"] == "memory"


def test_runtime_memory_discovery_accepts_generator_v2_memory(
    tmp_path: Path,
) -> None:
    _write_generator_package(
        tmp_path,
        content="system",
        logical_name="jazn.system.zip",
        payload_bytes=b"system-bytes",
    )
    _write_generator_package(
        tmp_path,
        content="memory",
        logical_name="jazn.memory.zip",
        payload_bytes=b"memory-bytes",
    )

    discovered = chatgpt_recovery._discover_memory_package(tmp_path)

    assert discovered["ok"] is True
    assert discovered["state"] == "memory_package_discovered"
    assert discovered["package_name"] == "jazn.memory.zip"
    assert discovered["generator_v2"] is True
    assert discovered["transport_schema"] == "jazn_pack_generator_package/v2"


def test_generator_v2_memory_compat_preserves_entry_inventory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    compat = tmp_path / "compat"
    memory_bytes = b"memory-transport"
    entry_bytes = b'{"synthetic":true}\n'
    payload = _write_generator_package(
        source,
        content="memory",
        logical_name="jazn.memory.zip",
        payload_bytes=memory_bytes,
        source_entries=[
            {
                "path": "memory/raw/synthetic.jsonl",
                "kind": "file",
                "size_bytes": len(entry_bytes),
                "sha256": hashlib.sha256(entry_bytes).hexdigest(),
            },
            {
                "path": "memory/raw",
                "kind": "directory",
                "size_bytes": 0,
            },
        ],
    )

    logical = materialize_generator_v2_compat(source, payload, compat)
    sidecar = json.loads((compat / f"{logical}.package.json").read_text(encoding="utf-8"))

    assert logical == "jazn.memory.zip"
    assert sidecar["profile"] == "memory"
    assert sidecar["compatibility_source_schema"] == "jazn_pack_generator_package/v2"
    assert [row["path"] for row in sidecar["entries"]] == [
        "memory/raw/synthetic.jsonl"
    ]


def test_large_legacy_memory_requires_safe_v3_repack() -> None:
    decision = memory_package_requires_v3_repack(
        {
            "archive_format": "binary",
            "entries": [
                {
                    "path": "memory/raw/huge.jsonl",
                    "size_bytes": 9 * 1024**3,
                }
            ],
        }
    )

    assert decision["required"] is True
    assert decision["reason"] == "legacy_transport_exceeds_safe_zip_limits"
    assert decision["oversized_members"] == ["memory/raw/huge.jsonl"]


def test_cli_exposes_memory_converge_and_durable_host_kind() -> None:
    parser = build_parser()

    converge = parser.parse_args(
        [
            "memory-converge",
            "--parts-dir",
            "parts",
            "--zip-name",
            "jazn.memory.zip",
        ]
    )
    assert converge.command == "memory-converge"
    assert converge.parts_dir == Path("parts")

    op = parser.parse_args(
        [
            "host-op-submit",
            "--operation-id",
            "memory-converge-test-12345678",
            "--kind",
            "memory-converge",
            "--",
            "--parts-dir",
            "parts",
        ]
    )
    assert op.kind == "memory-converge"


def test_durable_memory_converge_reenters_public_run_py(tmp_path: Path) -> None:
    (tmp_path / "run.py").write_text("# synthetic\n", encoding="utf-8")

    argv = build_host_operation_target_argv(
        tmp_path,
        kind="memory-converge",
        remainder=["--parts-dir", "parts"],
        python_executable="python-test",
    )

    assert argv[:4] == [
        "python-test",
        "-X",
        "utf8",
        str(tmp_path / "run.py"),
    ]
    assert "memory-converge" in argv
    assert "--parts-dir" in argv
    assert "parts" in argv
