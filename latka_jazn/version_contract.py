from __future__ import annotations

import re
from typing import Final

from latka_jazn.version import PACKAGE_VERSION, PACKAGE_VERSION_FULL, version_number

COMPONENT_SCHEMA_MAJOR: Final[int] = 1
LEGACY_CURRENT_LINE_VERSION: Final[str] = "v" + ".".join(("15", "1", "0", "3", "89"))
LEGACY_MEMORY_SOURCE_VERSION: Final[str] = "v" + ".".join(("15", "0", "3", "222"))
_VERSION_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z0-9])v?(?P<version>1[45](?:[._]\d+){2,6})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def component_schema_version(component: str, *, major: int = COMPONENT_SCHEMA_MAJOR) -> str:
    """Return a format identifier independent from the package release number."""
    normalized = str(component or "").strip().strip("/")
    if not normalized:
        raise ValueError("component must be a non-empty schema family")
    if int(major) < 1:
        raise ValueError("schema major must be >= 1")
    return f"{normalized}/v{int(major)}"


def legacy_component_schema_version(component: str) -> str:
    normalized = str(component or "").strip().strip("/")
    if not normalized:
        raise ValueError("component must be a non-empty schema family")
    return f"{normalized}/{LEGACY_CURRENT_LINE_VERSION}"


def component_schema_aliases(component: str) -> tuple[str, ...]:
    """Accepted identifiers for the unchanged v1 format during the v90 migration."""
    current = component_schema_version(component)
    return (current, legacy_component_schema_version(component), LEGACY_CURRENT_LINE_VERSION)


def normalize_component_schema(component: str, value: object) -> str:
    """Normalize the former release-coupled identifier to the stable v1 family."""
    current = component_schema_version(component)
    raw = str(value or "").strip()
    if not raw or raw in component_schema_aliases(component):
        return current
    return raw


def runtime_version() -> str:
    return PACKAGE_VERSION


def runtime_version_full() -> str:
    return PACKAGE_VERSION_FULL


def runtime_version_number() -> str:
    return version_number(PACKAGE_VERSION)


def extract_jazn_versions(text: object) -> tuple[str, ...]:
    found: list[str] = []
    for match in _VERSION_TOKEN_RE.finditer(str(text or "")):
        normalized = "v" + match.group("version").replace("_", ".").lstrip("vV")
        if normalized not in found:
            found.append(normalized)
    return tuple(found)


def mentions_jazn_version(text: object) -> bool:
    return bool(extract_jazn_versions(text))


def mentions_current_jazn_version(text: object) -> bool:
    current = "v" + version_number(PACKAGE_VERSION)
    return current in extract_jazn_versions(text)
