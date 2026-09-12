from __future__ import annotations

from dataclasses import replace

import pytest

from latka_jazn.memory.memory_cloud_gateway import InMemoryMemoryCloudRepository
from latka_jazn.memory.memory_cloud_server import MemoryCloudServerConfig, MemoryCloudServerFactory


class MemoryObjectStore:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def put_immutable(self, *, object_id: str, data: bytes) -> None:
        previous = self.values.get(object_id)
        if previous is not None and previous != data:
            raise RuntimeError("immutable collision")
        self.values[object_id] = bytes(data)

    def get(self, *, object_id: str) -> bytes:
        return self.values[object_id]

    def exists(self, *, object_id: str) -> bool:
        return object_id in self.values


def test_server_config_never_exposes_bearer_secret(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_TOKEN_ENV", "very-secret-token")
    cfg = MemoryCloudServerConfig(
        postgres_dsn="postgresql://example.invalid/jazn",
        bearer_token_env="SECRET_TOKEN_ENV",
        s3_bucket="memory-bucket",
    )
    public = cfg.public_dict()
    assert public["bearer_token_present"] is True
    assert public["secret_material_exposed"] is False
    assert "very-secret-token" not in repr(public)


def test_factory_builds_full_wsgi_boundary_with_injected_storage(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_TOKEN_ENV", "server-test-token")
    cfg = MemoryCloudServerConfig(
        postgres_dsn="injected",
        bearer_token_env="SECRET_TOKEN_ENV",
        s3_bucket="injected",
    )
    repository = InMemoryMemoryCloudRepository()
    objects = MemoryObjectStore()
    app = MemoryCloudServerFactory(
        cfg,
        repository_factory=lambda _: repository,
        object_store_factory=lambda _: objects,
    ).build()
    assert callable(app)
    assert repository.status("stream-x").remote_seq == 0


def test_factory_fails_closed_when_required_deployment_configuration_missing(monkeypatch) -> None:
    monkeypatch.delenv("MISSING_TOKEN", raising=False)
    cfg = MemoryCloudServerConfig(postgres_dsn="", bearer_token_env="MISSING_TOKEN", s3_bucket="")
    errors = cfg.validate()
    assert "postgres_dsn_missing" in errors
    assert "s3_bucket_missing" in errors
    assert "secret_env_missing:MISSING_TOKEN" in errors
    with pytest.raises(Exception):
        MemoryCloudServerFactory(cfg).build()
