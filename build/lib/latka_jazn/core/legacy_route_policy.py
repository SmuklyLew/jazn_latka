from __future__ import annotations

from dataclasses import asdict, dataclass
import re

from latka_jazn.version import PACKAGE_VERSION, schema_version, version_number

SCHEMA_VERSION = schema_version("legacy_route_policy")
_VERSION_RE = re.compile(r"(?<![0-9A-Za-z.])v?(?P<version>\d+(?:\.\d+){1,6})(?![0-9.])", re.IGNORECASE)


def legacy_token(*parts: str) -> str:
    return "_".join(parts)


LEGACY_FEEDBACK_ROUTE_TOKENS: tuple[str, ...] = (
    legacy_token("correction", "acknowledged"),
    legacy_token("positive", "continuation"),
)

# Nazwy semantyczne pozostają stabilne między wydaniami. Historyczne numery
# pakietów nie są częścią aktywnego kontraktu routingu.
LEGACY_NLP_ROUTE_TOKENS: tuple[str, ...] = (
    "legacy_nlp_adapter_update",
    "legacy_stale_nlp_route_hotfix",
    "legacy_full_update_scope",
)

LEGACY_SYSTEM_UPDATE_INTENTS: tuple[str, ...] = (
    "legacy_behavioral_runtime_dialogue_update_reference",
    "current_hotfix_for_stale_nlp_route",
)


def _version_tuple(raw: str) -> tuple[int, ...] | None:
    value = str(raw or "").strip().lower().lstrip("v").split("-", 1)[0]
    try:
        return tuple(int(part) for part in value.split("."))
    except (TypeError, ValueError):
        return None


def _padded(parts: tuple[int, ...], width: int = 7) -> tuple[int, ...]:
    return (parts + (0,) * width)[:width]


def is_legacy_package_version(raw: str, *, current: str = PACKAGE_VERSION) -> bool:
    """Return True only for an explicit package version older than current.

    Two-component values such as ``15.0`` are intentionally ignored because
    they are commonly timeouts, schema revisions or tool versions rather than
    Jaźń package versions. Package-line comparisons require at least three
    numeric components and the same major lineage used by the repository.
    """

    candidate = _version_tuple(raw)
    active = _version_tuple(version_number(current))
    if candidate is None or active is None or len(candidate) < 3:
        return False
    if candidate[0] not in {14, 15}:
        return False
    return _padded(candidate) < _padded(active)


def contains_legacy_feedback_token(text: str) -> bool:
    low = (text or "").lower()
    return any(token in low for token in LEGACY_FEEDBACK_ROUTE_TOKENS)


def contains_legacy_dotted_version(text: str) -> bool:
    return any(is_legacy_package_version(match.group("version")) for match in _VERSION_RE.finditer(text or ""))


def contains_legacy_route_token(text: str) -> bool:
    low = (text or "").lower()
    return (
        contains_legacy_feedback_token(low)
        or any(token in low for token in LEGACY_NLP_ROUTE_TOKENS)
        or contains_legacy_dotted_version(low)
    )


def legacy_forbidden_routes_for(priority: int) -> list[str]:
    return list(LEGACY_FEEDBACK_ROUTE_TOKENS) if priority > 50 else []


@dataclass(slots=True)
class LegacyRouteDecision:
    schema_version: str
    route: str
    blocked: bool
    safe_route: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def block_legacy_route(route: str, *, allow_legacy_route: bool = False) -> LegacyRouteDecision:
    value = route or ""
    if allow_legacy_route:
        return LegacyRouteDecision(SCHEMA_VERSION, value, False, value, "legacy_route_explicitly_allowed")
    if contains_legacy_route_token(value):
        return LegacyRouteDecision(SCHEMA_VERSION, value, True, "legacy_diagnostic_only", "active_runtime_blocks_legacy_route")
    return LegacyRouteDecision(SCHEMA_VERSION, value, False, value, "route_allowed")
