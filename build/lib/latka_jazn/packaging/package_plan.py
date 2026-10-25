from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

SUPPORTED_DISTRIBUTION_MODES = frozenset({
    "system-thin",
    "system-portable",
    "memory-only",
    "dependencies-only",
    "system+memory",
    "system+memory+dependencies",
})


@dataclass(frozen=True, slots=True)
class DistributionPackagePlan:
    mode: str
    include_system: bool
    include_memory: bool
    include_dependencies: bool
    target_required: bool
    target_alias: str | None = None
    python_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_distribution_package_plan(mode: str, *, target_alias: str | None = None,
                                    python_version: str | None = None) -> DistributionPackagePlan:
    normalized = str(mode or "").strip().lower()
    if normalized not in SUPPORTED_DISTRIBUTION_MODES:
        raise ValueError(f"unsupported distribution package mode: {mode!r}")
    include_system = normalized in {"system-thin", "system-portable", "system+memory", "system+memory+dependencies"}
    include_memory = normalized in {"memory-only", "system+memory", "system+memory+dependencies"}
    include_dependencies = normalized in {"dependencies-only", "system-portable", "system+memory+dependencies"}
    target_required = include_dependencies
    if target_required and (not target_alias or not python_version):
        raise ValueError("dependency-bearing package modes require target_alias and python_version")
    return DistributionPackagePlan(normalized, include_system, include_memory, include_dependencies,
                                   target_required, target_alias, python_version)
