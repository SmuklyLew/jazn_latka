from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol
import base64
import hashlib
import os

from latka_jazn.memory.memory_sync_contracts import (
    MemorySyncContractError,
    MemorySyncEvent,
    MemorySyncPlainEvent,
    b64encode,
)


class MemoryCryptoUnavailable(RuntimeError):
    pass


class MemoryKeyProvider(Protocol):
    def active_key_version(self) -> int: ...
    def key_for_version(self, version: int) -> bytes: ...
    def status(self) -> dict[str, object]: ...


@dataclass(slots=True, frozen=True)
class StaticMemoryKeyProvider:
    """Explicit keyring for tests, operator-injected secrets, or secure-store adapters.

    Keys are never generated silently and are never persisted by this class. Production
    deployments should populate this provider from an OS secure store or another
    secret manager outside the memory database and cloud object store.
    """

    keys: Mapping[int, bytes]
    active_version: int

    def __post_init__(self) -> None:
        normalized = {int(version): bytes(value) for version, value in self.keys.items()}
        if self.active_version not in normalized:
            raise MemorySyncContractError("active key version is not present in keyring")
        if any(version < 1 for version in normalized):
            raise MemorySyncContractError("key versions must be positive")
        if any(len(value) != 32 for value in normalized.values()):
            raise MemorySyncContractError("memory sync keys must be exactly 32 bytes")
        object.__setattr__(self, "keys", normalized)

    def active_key_version(self) -> int:
        return self.active_version

    def key_for_version(self, version: int) -> bytes:
        try:
            return bytes(self.keys[int(version)])
        except KeyError as exc:
            raise MemoryCryptoUnavailable(f"memory key version {version} is unavailable") from exc

    def status(self) -> dict[str, object]:
        return {
            "ready": True,
            "active_key_version": self.active_version,
            "available_key_versions": sorted(self.keys),
            "key_material_exposed": False,
        }


@dataclass(slots=True, frozen=True)
class EnvironmentMemoryKeyProvider:
    """Operator-controlled key provider for headless deployments.

    ``JAZN_MEMORY_SYNC_KEY_B64`` contains one 32-byte key. The environment is a
    transport from an external secret manager, not a persistence mechanism. The key
    is never written to SQLite, logs, manifests, or status payloads.
    """

    env_name: str = "JAZN_MEMORY_SYNC_KEY_B64"
    version_env_name: str = "JAZN_MEMORY_SYNC_KEY_VERSION"

    def _load(self) -> tuple[int, bytes]:
        raw = os.environ.get(self.env_name, "").strip()
        if not raw:
            raise MemoryCryptoUnavailable(f"{self.env_name} is not configured")
        try:
            key = base64.b64decode(raw.encode("ascii"), validate=True)
        except Exception as exc:
            raise MemoryCryptoUnavailable(f"{self.env_name} is not valid base64") from exc
        if len(key) != 32:
            raise MemoryCryptoUnavailable(f"{self.env_name} must decode to exactly 32 bytes")
        try:
            version = int(os.environ.get(self.version_env_name, "1"))
        except ValueError as exc:
            raise MemoryCryptoUnavailable(f"{self.version_env_name} must be an integer") from exc
        if version < 1:
            raise MemoryCryptoUnavailable(f"{self.version_env_name} must be positive")
        return version, key

    def active_key_version(self) -> int:
        return self._load()[0]

    def key_for_version(self, version: int) -> bytes:
        active, key = self._load()
        if int(version) != active:
            raise MemoryCryptoUnavailable(
                f"requested key version {version} is unavailable; configured version is {active}"
            )
        return key

    def status(self) -> dict[str, object]:
        try:
            version, _ = self._load()
        except MemoryCryptoUnavailable as exc:
            return {"ready": False, "error": str(exc), "key_material_exposed": False}
        return {"ready": True, "active_key_version": version, "key_material_exposed": False}


class MemoryCryptoProvider(Protocol):
    def encrypt_event(self, plain: MemorySyncPlainEvent, *, key_provider: MemoryKeyProvider) -> MemorySyncEvent: ...
    def decrypt_event(self, event: MemorySyncEvent, *, key_provider: MemoryKeyProvider) -> dict[str, object]: ...
    def status(self) -> dict[str, object]: ...


class PyNaClXChaCha20Poly1305Provider:
    """Authenticated client-side encryption using libsodium XChaCha20-Poly1305.

    The dependency is optional at import time so local Jaźń remains fully functional
    with cloud sync disabled. Enabling cloud sync requires the ``memory-cloud`` extra.
    """

    algorithm = "xchacha20poly1305_ietf"

    @staticmethod
    def _bindings():
        try:
            from nacl import bindings
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise MemoryCryptoUnavailable(
                "PyNaCl is required for encrypted memory sync; install latka-jazn[memory-cloud]"
            ) from exc
        return bindings

    def status(self) -> dict[str, object]:
        try:
            bindings = self._bindings()
        except MemoryCryptoUnavailable as exc:
            return {"ready": False, "algorithm": self.algorithm, "error": str(exc)}
        return {
            "ready": True,
            "algorithm": self.algorithm,
            "key_bytes": int(bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES),
            "nonce_bytes": int(bindings.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES),
        }

    def encrypt_event(self, plain: MemorySyncPlainEvent, *, key_provider: MemoryKeyProvider) -> MemorySyncEvent:
        bindings = self._bindings()
        version = key_provider.active_key_version()
        key = key_provider.key_for_version(version)
        if len(key) != bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES:
            raise MemorySyncContractError("invalid XChaCha20-Poly1305 key length")
        nonce = os.urandom(bindings.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES)
        aad_dict = plain.aad(key_version=version, payload_codec="json")
        from latka_jazn.memory.memory_sync_contracts import canonical_json_bytes

        aad = canonical_json_bytes(aad_dict)
        ciphertext = bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(
            plain.payload_bytes(), aad, nonce, key
        )
        return MemorySyncEvent(
            stream_id=plain.stream_id,
            event_id=plain.event_id,
            idempotency_key=plain.idempotency_key,
            device_id=plain.device_id,
            device_seq=plain.device_seq,
            event_type=plain.event_type,
            aggregate_id=plain.aggregate_id,
            aggregate_revision=plain.aggregate_revision,
            parent_event_id=plain.parent_event_id,
            turn_id=plain.turn_id,
            thought_id=plain.thought_id,
            payload_codec="json",
            ciphertext_b64=b64encode(ciphertext),
            ciphertext_sha256=hashlib.sha256(ciphertext).hexdigest(),
            key_version=version,
            nonce_b64=b64encode(nonce),
            aad_sha256=hashlib.sha256(aad).hexdigest(),
            created_at_utc=plain.created_at_utc,
            previous_device_event_sha256=plain.previous_device_event_sha256,
        )

    def decrypt_event(self, event: MemorySyncEvent, *, key_provider: MemoryKeyProvider) -> dict[str, object]:
        bindings = self._bindings()
        key = key_provider.key_for_version(event.key_version)
        try:
            plaintext = bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(
                event.ciphertext_bytes(), event.aad_bytes(), event.nonce_bytes(), key
            )
        except Exception as exc:
            raise MemorySyncContractError("memory event authentication/decryption failed") from exc
        if event.payload_codec != "json":
            raise MemorySyncContractError(f"unsupported event payload codec: {event.payload_codec}")
        import json

        try:
            value = json.loads(plaintext.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MemorySyncContractError("decrypted memory event is not valid UTF-8 JSON") from exc
        if not isinstance(value, dict):
            raise MemorySyncContractError("decrypted memory event payload must be an object")
        return value


@dataclass(slots=True, frozen=True)
class MemorySnapshotEncryptedChunk:
    ciphertext: bytes
    nonce: bytes
    key_version: int
    aad_sha256: str


class MemorySnapshotChunkCrypto(Protocol):
    def encrypt_chunk(
        self, plaintext: bytes, *, aad: bytes, key_provider: MemoryKeyProvider
    ) -> MemorySnapshotEncryptedChunk: ...

    def decrypt_chunk(
        self, ciphertext: bytes, *, nonce: bytes, key_version: int, aad: bytes, key_provider: MemoryKeyProvider
    ) -> bytes: ...

    def status(self) -> dict[str, object]: ...


class PyNaClMemorySnapshotChunkCrypto:
    """Authenticated bounded-chunk encryption for memory snapshots.

    Snapshot files are already split into bounded chunks by the snapshot manager,
    so each chunk is independently authenticated with XChaCha20-Poly1305. This
    permits resumable object transfer and corruption isolation without loading a
    complete database into memory.
    """

    algorithm = "xchacha20poly1305_ietf_chunked"

    @staticmethod
    def _bindings():
        return PyNaClXChaCha20Poly1305Provider._bindings()

    def status(self) -> dict[str, object]:
        try:
            bindings = self._bindings()
        except MemoryCryptoUnavailable as exc:
            return {"ready": False, "algorithm": self.algorithm, "error": str(exc)}
        return {
            "ready": True,
            "algorithm": self.algorithm,
            "key_bytes": int(bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES),
            "nonce_bytes": int(bindings.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES),
        }

    def encrypt_chunk(
        self, plaintext: bytes, *, aad: bytes, key_provider: MemoryKeyProvider
    ) -> MemorySnapshotEncryptedChunk:
        bindings = self._bindings()
        key_version = key_provider.active_key_version()
        key = key_provider.key_for_version(key_version)
        if len(key) != bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES:
            raise MemorySyncContractError("invalid XChaCha20-Poly1305 key length")
        nonce = os.urandom(bindings.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES)
        ciphertext = bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(plaintext, aad, nonce, key)
        return MemorySnapshotEncryptedChunk(
            ciphertext=ciphertext,
            nonce=nonce,
            key_version=key_version,
            aad_sha256=hashlib.sha256(aad).hexdigest(),
        )

    def decrypt_chunk(
        self, ciphertext: bytes, *, nonce: bytes, key_version: int, aad: bytes, key_provider: MemoryKeyProvider
    ) -> bytes:
        bindings = self._bindings()
        key = key_provider.key_for_version(key_version)
        try:
            return bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(ciphertext, aad, nonce, key)
        except Exception as exc:
            raise MemorySyncContractError("snapshot chunk authentication/decryption failed") from exc


@dataclass(slots=True, frozen=True)
class RecoveryKeyBundle:
    """Portable encrypted root-key bundle for disaster recovery.

    This object stores only salt/parameters/ciphertext. It never stores the recovery
    passphrase or plaintext root key.
    """

    salt_b64: str
    nonce_b64: str
    ciphertext_b64: str
    opslimit: int
    memlimit: int
    key_version: int
    algorithm: str = "argon2id+xchacha20poly1305"

    @classmethod
    def wrap(
        cls,
        root_key: bytes,
        *,
        recovery_passphrase: str,
        key_version: int,
        opslimit: int | None = None,
        memlimit: int | None = None,
    ) -> "RecoveryKeyBundle":
        if len(root_key) != 32:
            raise MemorySyncContractError("root key must be 32 bytes")
        if len(recovery_passphrase) < 12:
            raise MemorySyncContractError("recovery passphrase must contain at least 12 characters")
        try:
            from nacl import bindings, pwhash
        except Exception as exc:  # pragma: no cover - optional dependency
            raise MemoryCryptoUnavailable("PyNaCl is required to create a recovery bundle") from exc
        ops = int(opslimit or pwhash.argon2id.OPSLIMIT_MODERATE)
        mem = int(memlimit or pwhash.argon2id.MEMLIMIT_MODERATE)
        salt = os.urandom(pwhash.argon2id.SALTBYTES)
        wrapping_key = pwhash.argon2id.kdf(
            bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES,
            recovery_passphrase.encode("utf-8"),
            salt,
            opslimit=ops,
            memlimit=mem,
        )
        nonce = os.urandom(bindings.crypto_aead_xchacha20poly1305_ietf_NPUBBYTES)
        aad = f"jazn-memory-recovery|v1|key-version={key_version}".encode("utf-8")
        ciphertext = bindings.crypto_aead_xchacha20poly1305_ietf_encrypt(root_key, aad, nonce, wrapping_key)
        return cls(
            salt_b64=b64encode(salt),
            nonce_b64=b64encode(nonce),
            ciphertext_b64=b64encode(ciphertext),
            opslimit=ops,
            memlimit=mem,
            key_version=key_version,
        )

    def unwrap(self, *, recovery_passphrase: str) -> bytes:
        try:
            from nacl import bindings, pwhash
        except Exception as exc:  # pragma: no cover
            raise MemoryCryptoUnavailable("PyNaCl is required to open a recovery bundle") from exc
        try:
            salt = base64.b64decode(self.salt_b64, validate=True)
            nonce = base64.b64decode(self.nonce_b64, validate=True)
            ciphertext = base64.b64decode(self.ciphertext_b64, validate=True)
        except Exception as exc:
            raise MemorySyncContractError("recovery bundle contains invalid base64") from exc
        wrapping_key = pwhash.argon2id.kdf(
            bindings.crypto_aead_xchacha20poly1305_ietf_KEYBYTES,
            recovery_passphrase.encode("utf-8"),
            salt,
            opslimit=int(self.opslimit),
            memlimit=int(self.memlimit),
        )
        aad = f"jazn-memory-recovery|v1|key-version={self.key_version}".encode("utf-8")
        try:
            value = bindings.crypto_aead_xchacha20poly1305_ietf_decrypt(ciphertext, aad, nonce, wrapping_key)
        except Exception as exc:
            raise MemorySyncContractError("recovery bundle authentication failed") from exc
        if len(value) != 32:
            raise MemorySyncContractError("recovered key has invalid length")
        return value


__all__ = [
    "EnvironmentMemoryKeyProvider",
    "MemoryCryptoProvider",
    "MemoryCryptoUnavailable",
    "MemoryKeyProvider",
    "MemorySnapshotChunkCrypto",
    "MemorySnapshotEncryptedChunk",
    "PyNaClMemorySnapshotChunkCrypto",
    "PyNaClXChaCha20Poly1305Provider",
    "RecoveryKeyBundle",
    "StaticMemoryKeyProvider",
]
