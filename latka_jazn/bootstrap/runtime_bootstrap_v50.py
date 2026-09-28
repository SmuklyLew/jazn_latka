from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import hashlib
import json
import os
import shutil
import tempfile

from latka_jazn.bootstrap.chatgpt_recovery import recover_chatgpt_runtime
from latka_jazn.config import JaznConfig
from latka_jazn.core.runtime_daemon_lifecycle_hotfix import install_runtime_daemon_lifecycle_hotfix
from latka_jazn.core.runtime_lifecycle import reload_daemon
from latka_jazn.packaging.generator_v2_compat import (
    discover_generator_sidecar as _shared_discover_generator_sidecar,
    materialize_generator_v2_compat as _shared_materialize_generator_v2_compat,
)

PACK_GENERATOR_V2 = "jazn_pack_generator_package/v2"
LEGACY_COMPAT_SCHEMA = "jazn_package_set/v3"
CHUNK_SIZE = 8 * 1024 * 1024


def _mapping(value: Any) -> dict[str, Any]:
    """Return a concrete mapping so static narrowing and runtime validation agree."""

    return dict(value) if isinstance(value, Mapping) else {}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_verified(source: Path, destination: Path, expected_sha: str | None, expected_size: int | None) -> None:
    source = source.resolve(); destination.parent.mkdir(parents=True, exist_ok=True)
    if expected_size is not None and source.stat().st_size != int(expected_size):
        raise ValueError(f"package transport size mismatch for {source.name}")
    if expected_sha and _sha256_file(source) != expected_sha.lower():
        raise ValueError(f"package transport sha256 mismatch for {source.name}")
    tmp = destination.with_name(f".{destination.name}.copying.tmp")
    try:
        shutil.copy2(source, tmp)
        if expected_size is not None and tmp.stat().st_size != int(expected_size):
            raise ValueError(f"copied package transport size mismatch for {source.name}")
        if expected_sha and _sha256_file(tmp) != expected_sha.lower():
            raise ValueError(f"copied package transport sha256 mismatch for {source.name}")
        os.replace(tmp, destination)
    finally:
        tmp.unlink(missing_ok=True)


def _discover_generator_sidecar(
    parts_dir: Path,
    zip_name: str | None,
) -> tuple[Path, dict[str, Any]] | None:
    return _shared_discover_generator_sidecar(
        parts_dir,
        zip_name,
        allowed_contents={"system", "system+memory"},
    )


def _materialize_v2_compat(
    parts_dir: Path,
    payload: dict[str, Any],
    compat_dir: Path,
) -> str:
    return _shared_materialize_generator_v2_compat(parts_dir, payload, compat_dir)

def bootstrap_and_reload(
    *,
    operator_root: Path,
    parts_dir: Path,
    destination: Path,
    zip_name: str | None = None,
    memory_zip_name: str | None = None,
    no_auto_memory: bool = False,
    work_dir: Path | None = None,
    time_budget_seconds: float = 25.0,
    no_crc: bool = False,
    force_reextract: bool = False,
    no_start_daemon: bool = False,
    daemon_host: str = "127.0.0.1",
    daemon_port: int = 8787,
    startup_timeout: float = 12.0,
    stop_timeout: float = 5.0,
) -> dict[str, Any]:
    install_runtime_daemon_lifecycle_hotfix()
    operator_root = Path(operator_root).resolve(); parts_dir = Path(parts_dir).resolve(); destination = Path(destination).resolve()
    base_work = Path(work_dir).resolve() if work_dir else destination.parent
    base_work.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="jazn-v50-bootstrap-", dir=str(base_work)) as temporary:
        temp_root = Path(temporary)
        compat_parts = parts_dir
        resolved_zip_name = zip_name
        v2 = _discover_generator_sidecar(parts_dir, zip_name)
        if v2 is not None:
            compat_parts = temp_root / "compat-parts"; compat_parts.mkdir()
            resolved_zip_name = _materialize_v2_compat(parts_dir, v2[1], compat_parts)
            # Preserve a legacy memory package next to the adapted system package
            # only when auto-memory is requested. Existing recovery performs the
            # final memory contract verification.
            if not no_auto_memory:
                for candidate in parts_dir.iterdir():
                    if candidate.is_file() and (candidate.name.endswith(".sha256") or ".package" in candidate.name or ".zip." in candidate.name):
                        if candidate.name.startswith(resolved_zip_name):
                            continue
                        try:
                            shutil.copy2(candidate, compat_parts / candidate.name)
                        except OSError:
                            pass
        isolated_workspace = temp_root / "workspace"
        old_workspace = os.environ.get("JAZN_RUNTIME_WORKSPACE_DIR")
        os.environ["JAZN_RUNTIME_WORKSPACE_DIR"] = str(isolated_workspace)
        try:
            installed = recover_chatgpt_runtime(
                parts_dir=compat_parts,
                destination=destination,
                base_zip_name=resolved_zip_name,
                work_dir=temp_root / "recovery-work",
                time_budget_seconds=float(time_budget_seconds),
                run_crc=not no_crc,
                force_reextract=bool(force_reextract),
                start_runtime_daemon=False,
                auto_attach_memory=not no_auto_memory,
                memory_zip_name=memory_zip_name,
            )
        finally:
            if old_workspace is None:
                os.environ.pop("JAZN_RUNTIME_WORKSPACE_DIR", None)
            else:
                os.environ["JAZN_RUNTIME_WORKSPACE_DIR"] = old_workspace

    installation = installed.to_dict()
    if not installed.ok:
        return {"ok": False, "state": "installation_failed", "active_root": installed.active_root, "installation": installation, "exit_code": installed.exit_code}
    if no_start_daemon:
        return {"ok": True, "state": "installed_inactive", "active_root": str(destination), "installation": installation, "lifecycle_reload": None, "exit_code": 0}

    lifecycle = reload_daemon(
        JaznConfig(root=operator_root), target_root=destination,
        host=daemon_host, port=int(daemon_port),
        startup_timeout=float(startup_timeout), stop_timeout=float(stop_timeout),
    )
    ok = lifecycle.get("ok") is True
    return {
        "ok": ok,
        "state": "active" if ok else "installed_reload_failed",
        "active_root": str(destination),
        "installation": installation,
        "lifecycle_reload": lifecycle,
        "exit_code": 0 if ok else 13,
    }
