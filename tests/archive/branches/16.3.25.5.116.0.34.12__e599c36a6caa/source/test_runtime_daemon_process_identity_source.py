from __future__ import annotations

from latka_jazn.core import process_identity
from latka_jazn.core import runtime_daemon_lifecycle_hotfix as hotfix


def test_lifecycle_hotfix_reexports_shared_process_identity_contract() -> None:
    assert (
        hotfix.PROCESS_FINGERPRINT_SCHEMA_VERSION
        == process_identity.PROCESS_FINGERPRINT_SCHEMA_VERSION
    )
    assert hotfix.process_fingerprint is process_identity.process_fingerprint
    assert (
        hotfix.process_fingerprint_matches
        is process_identity.process_fingerprint_matches
    )


def test_lifecycle_hotfix_has_no_private_fingerprint_implementation() -> None:
    assert not hasattr(hotfix, "_linux_process_start_token")
    assert not hasattr(hotfix, "_windows_process_creation_filetime")
