from __future__ import annotations

# v16.3.15 hardens the v16.3.14 Memory Rebuild Test00/Recall release after
# deterministic CI exposed Studio slots/super and release-contract regressions.
# Test00 remains source-fidelity-only; Recall remains benchmark-first/FTS5-first
# with model training disabled.
DISTRIBUTION_VERSION = "16.3.15"
PACKAGE_VERSION = "16.3.15"
PACKAGE_RELEASE_NAME = "memory-rebuild-test00-recall-baseline"
PACKAGE_VERSION_FULL = (
    f"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}" if PACKAGE_RELEASE_NAME else PACKAGE_VERSION
)
RUNTIME_CONTRACT_VERSION = PACKAGE_VERSION
RUNTIME_CONTRACT_VERSION_FULL = PACKAGE_VERSION_FULL


def schema_version(component: str, *, version: str = PACKAGE_VERSION) -> str:
    """Return a current active-runtime schema/version marker for a component."""
    return f"{component}/{version}"


def version_number(version: str = PACKAGE_VERSION) -> str:
    value = str(version or PACKAGE_VERSION).strip().split("-", 1)[0].lstrip("v")
    return value or PACKAGE_VERSION.lstrip("v")


def active_line(component: str) -> str:
    return schema_version(component, version=PACKAGE_VERSION)


def version_slug(version: str = PACKAGE_VERSION) -> str:
    return "v" + version_number(version).replace(".", "_")


def generation_mode(prefix: str, *, version: str = PACKAGE_VERSION) -> str:
    return f"{prefix}_{version_slug(version)}"
