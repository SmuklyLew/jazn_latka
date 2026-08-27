from __future__ import annotations

# v16.3.19 completes the unified Memory Rebuild Studio CI correction: dialog
# input cancellation is normalized to the public str contract and the retired
# P0 Studio regression suite now validates the canonical Studio/test specs
# instead of importing implementations removed by the v16.3.18 cleanup.
DISTRIBUTION_VERSION = "16.3.19"
PACKAGE_VERSION = "16.3.19"
PACKAGE_RELEASE_NAME = "memory-rebuild-unified-studio-ci-fix"
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
