from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
import hashlib
import importlib
import json
import os

from latka_jazn.core.runtime_root import workspace_runtime_path


class MemoryPackageSourceError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class MaterializedMemoryPackageSource:
    parts_dir: Path
    source_kind: str
    report: dict[str, Any]


_MAX_SIDECAR_BYTES = 4 * 1024 * 1024
_COPY_BLOCK_BYTES = 4 * 1024 * 1024


def _safe_filename(value: str) -> str:
    text = str(value or "").strip()
    path = PurePosixPath(text.replace("\\", "/"))
    if not text or path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
        raise MemoryPackageSourceError(f"unsafe package object filename: {value!r}")
    return path.name


def _r2_endpoint_from_env(explicit: str | None) -> str | None:
    if explicit and explicit.strip():
        return explicit.strip()
    configured = os.environ.get("JAZN_MEMORY_CLOUD_S3_ENDPOINT", "").strip()
    if configured:
        return configured
    account_id = os.environ.get("JAZN_MEMORY_CLOUD_R2_ACCOUNT_ID", "").strip()
    if account_id:
        return f"https://{account_id}.r2.cloudflarestorage.com"
    return None


def _r2_client(*, endpoint_url: str | None, region_name: str, client: Any | None) -> Any:
    if client is not None:
        return client
    try:
        boto3: Any = importlib.import_module("boto3")
    except Exception as exc:  # pragma: no cover - optional dependency
        raise MemoryPackageSourceError(
            "boto3 is required for Cloudflare R2 memory package attach; "
            "install the memory-cloud server extras or provide a compatible client"
        ) from exc
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region_name or "auto",
    )


def _list_keys(client: Any, *, bucket: str, prefix: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    continuation: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        response = client.list_objects_v2(**kwargs)
        contents = response.get("Contents") or []
        for item in contents:
            if isinstance(item, Mapping) and item.get("Key"):
                rows.append(dict(item))
        if not response.get("IsTruncated"):
            break
        continuation = str(response.get("NextContinuationToken") or "").strip() or None
        if continuation is None:
            raise MemoryPackageSourceError("R2 listing was truncated without continuation token")
    return rows


def _download_object(
    client: Any,
    *,
    bucket: str,
    key: str,
    destination: Path,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
    hard_max_bytes: int | None = None,
) -> dict[str, Any]:
    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"]
    declared_length = response.get("ContentLength")
    if hard_max_bytes is not None and declared_length is not None and int(declared_length) > hard_max_bytes:
        raise MemoryPackageSourceError(
            f"R2 object exceeds hard download limit: {key}: {declared_length}>{hard_max_bytes}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".downloading")
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as handle:
            while True:
                block = body.read(_COPY_BLOCK_BYTES)
                if not block:
                    break
                size += len(block)
                if hard_max_bytes is not None and size > hard_max_bytes:
                    raise MemoryPackageSourceError(
                        f"R2 object exceeds hard download limit while streaming: {key}"
                    )
                handle.write(block)
                digest.update(block)
            handle.flush()
            os.fsync(handle.fileno())
        actual_sha = digest.hexdigest()
        if expected_size is not None and size != int(expected_size):
            raise MemoryPackageSourceError(
                f"R2 object size mismatch: {key}: {size}!={expected_size}"
            )
        if expected_sha256 and actual_sha != expected_sha256.strip().lower():
            raise MemoryPackageSourceError(f"R2 object SHA-256 mismatch: {key}")
        os.replace(temporary, destination)
        return {"key": key, "filename": destination.name, "size_bytes": size, "sha256": actual_sha}
    finally:
        try:
            body.close()
        except Exception:
            pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def materialize_r2_memory_package(
    runtime_root: Path,
    *,
    key_prefix: str,
    bucket: str | None = None,
    endpoint_url: str | None = None,
    region_name: str = "auto",
    work_dir: Path | None = None,
    client: Any | None = None,
) -> MaterializedMemoryPackageSource:
    runtime_root = Path(runtime_root).expanduser().resolve()
    bucket_name = str(bucket or os.environ.get("JAZN_MEMORY_CLOUD_S3_BUCKET", "")).strip()
    if not bucket_name:
        raise MemoryPackageSourceError(
            "Cloudflare R2 memory attach requires --r2-bucket or JAZN_MEMORY_CLOUD_S3_BUCKET"
        )
    prefix = str(key_prefix or "").strip().strip("/")
    if not prefix or ".." in PurePosixPath(prefix).parts:
        raise MemoryPackageSourceError("R2 package prefix must be a safe non-empty object prefix")
    endpoint = _r2_endpoint_from_env(endpoint_url)
    if not endpoint:
        raise MemoryPackageSourceError(
            "Cloudflare R2 endpoint is missing; provide --r2-endpoint, "
            "JAZN_MEMORY_CLOUD_S3_ENDPOINT or JAZN_MEMORY_CLOUD_R2_ACCOUNT_ID"
        )
    resolved_client = _r2_client(endpoint_url=endpoint, region_name=region_name, client=client)
    workspace = workspace_runtime_path(runtime_root)
    cache_key = hashlib.sha256(
        f"{bucket_name}\0{endpoint}\0{prefix}".encode("utf-8")
    ).hexdigest()[:24]
    destination = (
        Path(work_dir).expanduser().resolve()
        if work_dir is not None
        else workspace / "memory_attach_sources" / "r2" / cache_key
    )
    destination.mkdir(parents=True, exist_ok=True)

    rows = _list_keys(resolved_client, bucket=bucket_name, prefix=prefix + "/")
    by_basename: dict[str, str] = {}
    for row in rows:
        key = str(row.get("Key") or "")
        suffix = key[len(prefix) + 1 :] if key.startswith(prefix + "/") else ""
        if not suffix or "/" in suffix:
            continue
        safe = _safe_filename(suffix)
        if safe in by_basename and by_basename[safe] != key:
            raise MemoryPackageSourceError(f"duplicate package filename in R2 prefix: {safe}")
        by_basename[safe] = key
    sidecars = sorted(name for name in by_basename if name.endswith(".package.json"))
    if len(sidecars) != 1:
        raise MemoryPackageSourceError(
            f"R2 prefix must contain exactly one package sidecar, found {len(sidecars)}"
        )
    sidecar_name = sidecars[0]
    sidecar_path = destination / sidecar_name
    _download_object(
        resolved_client,
        bucket=bucket_name,
        key=by_basename[sidecar_name],
        destination=sidecar_path,
        hard_max_bytes=_MAX_SIDECAR_BYTES,
    )
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise MemoryPackageSourceError(f"invalid R2 package sidecar: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise MemoryPackageSourceError("R2 package sidecar root must be a JSON object")
    if str(payload.get("schema_version") or "") != "jazn_package_set/v2":
        raise MemoryPackageSourceError("R2 package sidecar schema is unsupported")
    if str(payload.get("profile") or "").strip().lower() != "memory":
        raise MemoryPackageSourceError("R2 package sidecar is not profile=memory")
    outputs = payload.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise MemoryPackageSourceError("R2 package sidecar has no outputs")

    downloaded: list[dict[str, Any]] = []
    declared_filenames: set[str] = set()
    for item in outputs:
        if not isinstance(item, Mapping):
            raise MemoryPackageSourceError("R2 package sidecar output entry is invalid")
        filename = _safe_filename(str(item.get("filename") or ""))
        if filename in declared_filenames:
            raise MemoryPackageSourceError(f"R2 package sidecar declares duplicate output: {filename}")
        declared_filenames.add(filename)
        key = by_basename.get(filename)
        if not key:
            raise MemoryPackageSourceError(f"R2 package part missing: {filename}")
        downloaded.append(
            _download_object(
                resolved_client,
                bucket=bucket_name,
                key=key,
                destination=destination / filename,
                expected_size=int(item["size_bytes"]) if item.get("size_bytes") is not None else None,
                expected_sha256=str(item.get("sha256") or "").strip().lower() or None,
            )
        )
    report = {
        "source_kind": "cloudflare_r2_s3",
        "bucket": bucket_name,
        "key_prefix": prefix,
        "endpoint": endpoint,
        "region_name": region_name or "auto",
        "sidecar": sidecar_name,
        "package_name": payload.get("package_name"),
        "downloaded_objects": downloaded,
        "parts_dir": str(destination),
        "direct_s3_transport": True,
        "worker_proxy_required": False,
        "truth_boundary": (
            "Cloudflare R2 is only a transport source. Downloaded bytes are staged locally and must pass "
            "the same package SHA/CRC/manifest/SQLite verification as a local memory package before activation."
        ),
    }
    return MaterializedMemoryPackageSource(destination, "cloudflare_r2_s3", report)


__all__ = [
    "MaterializedMemoryPackageSource",
    "MemoryPackageSourceError",
    "materialize_r2_memory_package",
]
