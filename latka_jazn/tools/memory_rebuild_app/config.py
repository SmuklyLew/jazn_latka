from __future__ import annotations

"""Stable command and repository-discovery configuration for Memory Rebuild."""

from pathlib import Path
import os
import sys

# These identify the stable operator-tool/application contract. Feature hardening
# is versioned separately so compatible releases do not break launchers, tests
# or project-format consumers.
TOOL_VERSION = "memory-rebuild/v16.1"
APP_VERSION = "3.0.0"
TOOL_REVISION = "15.3.23.01"
TOOL_RELEASE_NAME = "Poprawione narzędzie odbudowy pamięci"
TOOL_RELEASE_LABEL = f"{TOOL_REVISION} - {TOOL_RELEASE_NAME}"

STAGE4_COMMAND = "stage4"
TEST04_COMMAND = "test04"
PROFILE_ALIASES = frozenset({"test01", "test02", "test03", "final"})
LEGACY_FLAGS = frozenset({
    "--legacy-five-db", "--config", "--write-example-config", "--no-ui",
    "--plan-only", "--all-discovered", "--source", "--self-test", "--confirm",
})


def candidate_repo_roots(entrypoint: str | Path) -> tuple[Path, ...]:
    """Return deterministic candidates without changing the process environment."""

    raw: list[Path] = []
    configured = os.environ.get("JAZN_ROOT", "").strip()
    if configured:
        raw.append(Path(configured).expanduser())
    here = Path(entrypoint).resolve()
    raw.extend((here.parent, here.parent.parent, Path.cwd(), Path.cwd().parent))
    seen: set[str] = set()
    result: list[Path] = []
    for value in raw:
        try:
            path = value.resolve()
        except OSError:
            path = value.absolute()
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return tuple(result)


def resolve_repo_root(entrypoint: str | Path) -> Path:
    for root in candidate_repo_roots(entrypoint):
        if (root / "latka_jazn" / "__init__.py").is_file():
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            return root
    raise RuntimeError(
        "Nie znaleziono repozytorium Jaźni (latka_jazn/__init__.py). "
        "Uruchom narzędzie z katalogu repo, umieść je w tools/ albo ustaw JAZN_ROOT."
    )


__all__ = [
    "APP_VERSION",
    "LEGACY_FLAGS",
    "PROFILE_ALIASES",
    "STAGE4_COMMAND",
    "TEST04_COMMAND",
    "TOOL_RELEASE_LABEL",
    "TOOL_RELEASE_NAME",
    "TOOL_REVISION",
    "TOOL_VERSION",
    "candidate_repo_roots",
    "resolve_repo_root",
]
