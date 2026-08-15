from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import os

from latka_jazn.memory.memory_cloud_gateway import (
    CloudObjectStore,
    MemoryCloudGatewayService,
    MemoryCloudGatewayWSGIApplication,
    MemoryCloudRepository,
    MemoryCloudRepositoryError,
    PostgresMemoryCloudRepository,
    S3CompatibleObjectStore,
)


@dataclass(slots=True, frozen=True)
class MemoryCloudServerConfig:
    """Environment-resolved deployment configuration for the memory gateway.

    Secrets are referenced by environment-variable name and are never returned by
    ``public_dict``. PostgreSQL and object-store credentials stay in their native
    provider mechanisms; the Jaźń server does not copy them into memory manifests.
    """

    postgres_dsn: str
    bearer_token_env: str
    s3_bucket: str
    s3_prefix: str = "jazn-memory"
    s3_endpoint_url: str | None = None
    s3_region_name: str | None = None
    require_writer_lease: bool = False
    max_json_body_bytes: int = 4 * 1024 * 1024
    max_object_body_bytes: int = 32 * 1024 * 1024

    @classmethod
    def from_environment(cls) -> "MemoryCloudServerConfig":
        return cls(
            postgres_dsn=os.environ.get("JAZN_MEMORY_CLOUD_POSTGRES_DSN", "").strip(),
            bearer_token_env=os.environ.get("JAZN_MEMORY_CLOUD_SERVER_TOKEN_ENV", "JAZN_MEMORY_CLOUD_SERVER_TOKEN").strip(),
            s3_bucket=os.environ.get("JAZN_MEMORY_CLOUD_S3_BUCKET", "").strip(),
            s3_prefix=os.environ.get("JAZN_MEMORY_CLOUD_S3_PREFIX", "jazn-memory").strip(),
            s3_endpoint_url=os.environ.get("JAZN_MEMORY_CLOUD_S3_ENDPOINT", "").strip() or None,
            s3_region_name=os.environ.get("JAZN_MEMORY_CLOUD_S3_REGION", "").strip() or None,
            require_writer_lease=os.environ.get("JAZN_MEMORY_CLOUD_REQUIRE_WRITER_LEASE", "0").strip().lower()
            in {"1", "true", "yes", "on"},
            max_json_body_bytes=_env_int("JAZN_MEMORY_CLOUD_MAX_JSON_BYTES", 4 * 1024 * 1024, 64 * 1024, 16 * 1024 * 1024),
            max_object_body_bytes=_env_int("JAZN_MEMORY_CLOUD_MAX_OBJECT_BYTES", 32 * 1024 * 1024, 64 * 1024, 128 * 1024 * 1024),
        )

    def validate(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.postgres_dsn:
            errors.append("postgres_dsn_missing")
        if not self.bearer_token_env:
            errors.append("bearer_token_env_missing")
        elif not os.environ.get(self.bearer_token_env, "").strip():
            errors.append(f"secret_env_missing:{self.bearer_token_env}")
        if not self.s3_bucket:
            errors.append("s3_bucket_missing")
        return tuple(errors)

    def public_dict(self) -> dict[str, Any]:
        return {
            "postgres_configured": bool(self.postgres_dsn),
            "bearer_token_env": self.bearer_token_env or None,
            "bearer_token_present": bool(self.bearer_token_env and os.environ.get(self.bearer_token_env, "").strip()),
            "s3_bucket": self.s3_bucket or None,
            "s3_prefix": self.s3_prefix,
            "s3_endpoint_url": self.s3_endpoint_url,
            "s3_region_name": self.s3_region_name,
            "require_writer_lease": self.require_writer_lease,
            "max_json_body_bytes": self.max_json_body_bytes,
            "max_object_body_bytes": self.max_object_body_bytes,
            "validation_errors": list(self.validate()),
            "secret_material_exposed": False,
        }


class MemoryCloudServerFactory:
    """Composition root for the deployable encrypted-memory WSGI service."""

    def __init__(
        self,
        config: MemoryCloudServerConfig,
        *,
        repository_factory: Callable[[MemoryCloudServerConfig], MemoryCloudRepository] | None = None,
        object_store_factory: Callable[[MemoryCloudServerConfig], CloudObjectStore] | None = None,
    ) -> None:
        self.config = config
        self.repository_factory = repository_factory or self._default_repository
        self.object_store_factory = object_store_factory or self._default_object_store

    def build(self) -> MemoryCloudGatewayWSGIApplication:
        errors = self.config.validate()
        if errors:
            raise MemoryCloudRepositoryError("memory cloud server configuration invalid: " + ", ".join(errors))
        repository = self.repository_factory(self.config)
        repository.ensure_schema()
        object_store = self.object_store_factory(self.config)
        service = MemoryCloudGatewayService(
            repository=repository,
            object_store=object_store,
            require_writer_lease=self.config.require_writer_lease,
        )
        token = os.environ[self.config.bearer_token_env].strip()
        return MemoryCloudGatewayWSGIApplication(
            service,
            bearer_tokens=(token,),
            max_json_body_bytes=self.config.max_json_body_bytes,
            max_object_body_bytes=self.config.max_object_body_bytes,
        )

    @staticmethod
    def _default_repository(config: MemoryCloudServerConfig) -> MemoryCloudRepository:
        return PostgresMemoryCloudRepository(config.postgres_dsn)

    @staticmethod
    def _default_object_store(config: MemoryCloudServerConfig) -> CloudObjectStore:
        return S3CompatibleObjectStore(
            bucket=config.s3_bucket,
            prefix=config.s3_prefix,
            endpoint_url=config.s3_endpoint_url,
            region_name=config.s3_region_name,
        )


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError as exc:
        raise MemoryCloudRepositoryError(f"{name} must be an integer") from exc
    return max(minimum, min(value, maximum))


__all__ = ["MemoryCloudServerConfig", "MemoryCloudServerFactory"]
