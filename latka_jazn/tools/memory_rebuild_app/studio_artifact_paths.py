from __future__ import annotations

"""Project-scoped destinations for private Memory Rebuild Studio artifacts.

The code checkout contains application sources, never a default destination for
private file-check reports or Test00--Final protocol state.
"""

from pathlib import Path
from typing import Iterable

from .studio_write_safety import require_isolated_staging_path


def project_artifact_paths(
    *,
    target_root: str | Path,
    tool_root: str | Path,
    source_directory: str | Path | None = None,
    source_paths: Iterable[str | Path] = (),
) -> tuple[Path, Path]:
    """Return (protocols, reports), with fail-closed source/code isolation.

    With a standard project layout of lab/work, artifacts are placed alongside
    staging in lab/protocols and lab/reports. For other layouts use a nested
    _studio_artifacts directory to avoid collisions between nearby projects.
    No directories are created until the caller explicitly performs an action.
    """
    if not str(target_root).strip():
        raise ValueError("Najpierw ustaw katalog docelowy projektu.")
    target = Path(target_root).expanduser().resolve()
    checkout = Path(tool_root).expanduser().resolve()
    root = target.parent if target.name.casefold() == "work" else target / "_studio_artifacts"

    # Memory Studio must never write personal artifacts to its source checkout.
    if root == checkout or checkout in root.parents:
        raise ValueError("Artefakty Studio nie mogą być zapisywane w repozytorium Jaźni.")

    inputs: list[Path] = []
    if source_directory and str(source_directory).strip():
        inputs.append(Path(source_directory).expanduser().resolve())
    inputs.extend(Path(path).expanduser().resolve() for path in source_paths)

    paths = (root / "protocols", root / "reports")
    for output in paths:
        require_isolated_staging_path(output, tool_root=checkout)
        for source in inputs:
            if output == source or source in output.parents or output in source.parents:
                raise ValueError(
                    "Artefakty Studio nie mogą pokrywać się z katalogiem ani plikiem źródłowym."
                )
    return paths


__all__ = ["project_artifact_paths"]
