from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import json
import os
import re

from .models import RebuildProject, utc_iso

PROJECT_FILE_SUFFIX = ".memory-rebuild.json"


def default_project_root() -> Path:
    override = os.environ.get("JAZN_MEMORY_REBUILD_PROJECTS")
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".jazn" / "memory_rebuild_projects").resolve()


def slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return normalized.casefold() or "memory-rebuild"


@dataclass(slots=True, frozen=True)
class ProjectDescriptor:
    path: Path
    project_id: str
    name: str
    target_root: str
    updated_at_utc: str
    revision: int


class ProjectStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or default_project_root()).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.history_root = self.root / ".history"

    def project_path(self, project: RebuildProject) -> Path:
        filename = f"{slugify(project.name)}-{project.project_id[-12:]}{PROJECT_FILE_SUFFIX}"
        return self.root / filename

    def _resolve_project_file(self, identifier: str | Path) -> Path:
        candidate = Path(identifier).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        raw = str(identifier).strip()
        matches: list[Path] = []
        for path in self.root.glob(f"*{PROJECT_FILE_SUFFIX}"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("project_id") == raw or path.stem == raw or payload.get("name") == raw:
                matches.append(path)
        if not matches:
            raise FileNotFoundError(f"Nie znaleziono projektu: {identifier}")
        if len(matches) > 1:
            raise RuntimeError(f"Identyfikator projektu jest niejednoznaczny: {identifier}")
        return matches[0].resolve()

    def list(self) -> list[ProjectDescriptor]:
        result: list[ProjectDescriptor] = []
        for path in sorted(self.root.glob(f"*{PROJECT_FILE_SUFFIX}"), key=lambda item: item.name.casefold()):
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                project = RebuildProject.from_dict(payload)
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                continue
            result.append(
                ProjectDescriptor(
                    path=path.resolve(),
                    project_id=project.project_id,
                    name=project.name,
                    target_root=project.target_root,
                    updated_at_utc=project.updated_at_utc,
                    revision=project.revision,
                )
            )
        return sorted(result, key=lambda item: item.updated_at_utc, reverse=True)

    def load(self, identifier: str | Path) -> RebuildProject:
        path = self._resolve_project_file(identifier)
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError(f"Projekt nie jest obiektem JSON: {path}")
        project = RebuildProject.from_dict(payload)
        project.settings["_project_file"] = str(path)
        return project

    def save(self, project: RebuildProject, *, path: str | Path | None = None) -> Path:
        project.normalized()
        explicit = Path(path).expanduser().resolve() if path else None
        remembered = project.settings.pop("_project_file", None)
        target = explicit or (Path(remembered).resolve() if remembered else self.project_path(project))
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.is_file():
            self._archive_existing(project.project_id, target)

        project.updated_at_utc = utc_iso()
        payload = project.to_dict()
        payload["updated_at_utc"] = project.updated_at_utc
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, target)
        project.settings["_project_file"] = str(target)
        return target

    def create(self, project: RebuildProject) -> Path:
        if any(item.project_id == project.project_id for item in self.list()):
            raise FileExistsError(project.project_id)
        return self.save(project)

    def delete(self, identifier: str | Path) -> Path:
        path = self._resolve_project_file(identifier)
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        project_id = str(payload.get("project_id") or path.stem)
        self._archive_existing(project_id, path)
        path.unlink()
        return path

    def _archive_existing(self, project_id: str, path: Path) -> Path:
        history = self.history_root / project_id
        history.mkdir(parents=True, exist_ok=True)
        stamp = utc_iso().replace(":", "").replace("+", "_")
        destination = history / f"{stamp}-{path.name}"
        destination.write_bytes(path.read_bytes())
        return destination

    def import_projects(self, paths: Iterable[str | Path]) -> list[Path]:
        imported: list[Path] = []
        for item in paths:
            source = Path(item).expanduser().resolve()
            payload = json.loads(source.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                raise ValueError(f"Projekt nie jest obiektem JSON: {source}")
            project = RebuildProject.from_dict(payload)
            imported.append(self.save(project))
        return imported


__all__ = [
    "PROJECT_FILE_SUFFIX",
    "ProjectDescriptor",
    "ProjectStore",
    "default_project_root",
    "slugify",
]
