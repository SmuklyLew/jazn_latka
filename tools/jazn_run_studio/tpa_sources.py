"""Finite, explicit source preparation outside active SYSTEM and runtime.

Git sources use detached worktrees. Exports use canonical package verification;
ZIP members are treated as untrusted data, never as commands. No daemon runs here.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile

from latka_jazn.tools.application_shell.operator_paths import validate_operator_path
from .external import run
from .local_acceptance import scope_version
from .tpa_release_identity import verified_release_source

KINDS = ("master", "branch", "pr", "merge", "local", "zip")
MAX_ZIP_BYTES = 512 * 1024 * 1024
MAX_ZIP_FILES = 20000


def git(root: Path, *args: str, timeout: float = 60) -> str:
    result = run(["git", "-C", str(root), *args], cwd=root, timeout=timeout)
    if result.returncode:
        # Git errors may contain private remote URLs. Keep diagnostics bounded.
        raise ValueError("Git odmówił operacji źródła: " + args[0] + " (kod " + str(result.returncode) + ")")
    return result.stdout.decode("utf-8", "strict").strip()


def _fresh_destination(root: Path, destination: Path) -> Path:
    if not destination.is_absolute() or ".." in destination.parts:
        raise ValueError("Wymagany nowy absolutny katalog źródła")
    for part in (destination, *destination.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Dowiązanie w katalogu źródła")
    validate_operator_path(destination, root, directory=True, allow_acceptance_operator=True)
    if destination.exists():
        raise ValueError("Katalog źródła już istnieje; nie nadpisano danych")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _extract_zip(archive: Path, destination: Path) -> Path:
    if (not archive.is_absolute() or archive.is_symlink() or not archive.is_file()
            or archive.stat().st_size > MAX_ZIP_BYTES):
        raise ValueError("Wskaż zwykły plik ZIP przez ścieżkę absolutną")
    with zipfile.ZipFile(archive) as source:
        items = source.infolist()
        if len(items) > MAX_ZIP_FILES or sum(i.file_size for i in items) > MAX_ZIP_BYTES:
            raise ValueError("ZIP przekracza limit źródła TPA")
        file_names = {i.filename for i in items if not i.is_dir()}
        prefixes = {PurePosixPath(n).parent for n in file_names if PurePosixPath(n).name == "run.py"
                    and str(PurePosixPath(n).parent / "main.py") in file_names
                    and str(PurePosixPath(n).parent / "latka_jazn/version.py") in file_names}
        if len(prefixes) != 1:
            raise ValueError("ZIP musi zawierać jeden jednoznaczny SYSTEM")
        prefix = next(iter(prefixes))
        names: set[str] = set()
        for info in items:
            path = PurePosixPath(info.filename)
            if not path.is_relative_to(prefix):
                raise ValueError("ZIP zawiera dane poza wybranym SYSTEM")
            relative = path.relative_to(prefix)
            if (not info.filename or info.orig_filename != info.filename or "\\" in info.filename or path.is_absolute()
                    or any(p.casefold() in {"..", ".git"} for p in path.parts)
                    or relative.parts and relative.parts[0].casefold() in {"memory", "workspace_runtime", ".settings_local"}
                    or any(":" in p or p.endswith((".", " ")) for p in path.parts)
                    or stat.S_ISLNK(info.external_attr >> 16)
                    or info.filename.casefold() in names):
                raise ValueError("Niedozwolona ścieżka lub dowiązanie w ZIP")
            names.add(info.filename.casefold())
        destination.mkdir(exist_ok=False)
        for info in items:
            path = destination.joinpath(*PurePosixPath(info.filename).parts)
            if info.is_dir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            with source.open(info) as src, path.open("xb") as dst:
                copied = 0
                while chunk := src.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > info.file_size or copied > MAX_ZIP_BYTES:
                        raise ValueError("Niezgodna wielkość pliku ZIP")
                    dst.write(chunk)
        roots = [destination] if (destination / "run.py").is_file() else [
            p for p in destination.iterdir() if p.is_dir() and (p / "run.py").is_file()]
        if len(roots) != 1:
            raise ValueError("ZIP musi zawierać jeden jednoznaczny SYSTEM")
        return roots[0]


def prepare_source(root: Path, destination: Path, *, kind: str = "master", value: str = "", fetch: bool = True) -> dict:
    """Prepare an owned copy, retaining it on refusal for diagnosis (no cleanup)."""
    root = root.resolve()
    if kind not in KINDS:
        raise ValueError("Nieznany rodzaj źródła")
    destination = _fresh_destination(root, destination)
    source_root = root
    if kind == "local" and value:
        raw = Path(value)
        if not raw.is_absolute() or raw.is_symlink() or raw.is_junction():
            raise ValueError("Nieprawidłowy lokalny SYSTEM")
        source_root = raw.resolve()
        validate_operator_path(destination, source_root, directory=True, allow_acceptance_operator=True)
    if kind == "zip":
        selected = _extract_zip(Path(value), destination)
        identity = verified_release_source(selected)
        if identity.get("release_verified") is not True:
            raise ValueError("ZIP nie ma potwierdzonej integralności i provenance")
        identity.update(git_sha=identity["release_source_commit"], git_dirty=False,
                        archive_sha256=sha256(Path(value).read_bytes()).hexdigest(), integrity="verified_release_manifest")
    elif kind == "local" and not (source_root / ".git").exists():
        identity = verified_release_source(source_root)
        if identity.get("release_verified") is not True:
            raise ValueError("Lokalny SYSTEM nie ma potwierdzonej integralności")
        from latka_jazn.tools.release_staging import create_system_smoke_staging
        create_system_smoke_staging(source_root, destination)
        selected = destination
        if verified_release_source(selected) != identity:
            raise ValueError("Tożsamość kopii SYSTEM jest niezgodna ze źródłem")
        identity.update(git_sha=identity["release_source_commit"], git_dirty=False, integrity="verified_release_manifest")
    else:
        if not (source_root / ".git").exists():
            raise ValueError("Źródło wymaga repozytorium Git")
        if kind == "local":
            if git(source_root, "status", "--porcelain"):
                raise ValueError("Lokalny SYSTEM ma niezapisane zmiany; zapisz je przed odbiorem")
            ref = "HEAD"
        elif kind in {"master", "branch"}:
            branch = "master" if kind == "master" else value
            if (not branch or branch.startswith("-") or git(source_root, "check-ref-format", "--branch", branch) != branch):
                raise ValueError("Nieprawidłowy branch źródła")
            remote_ref = "refs/heads/" + branch
            ref = "refs/remotes/origin/" + branch
            if fetch:
                git(source_root, "fetch", "--no-tags", "origin", remote_ref + ":" + ref)
        else:
            if not re.fullmatch(r"[1-9][0-9]{0,8}", value):
                raise ValueError("Wymagany numer Pull Request")
            suffix = "head" if kind == "pr" else "merge"
            remote_ref = "refs/pull/" + value + "/" + suffix
            ref = "refs/tpa/pull/" + value + "/" + suffix
            if fetch:
                git(source_root, "fetch", "--no-tags", "origin", remote_ref + ":" + ref)
        commit = git(source_root, "rev-parse", "--verify", ref + "^{commit}")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Nie ustalono dokładnego SHA źródła")
        git(source_root, "worktree", "add", "--detach", str(destination), commit)
        selected = destination
        if git(selected, "rev-parse", "HEAD") != commit or git(selected, "status", "--porcelain"):
            raise ValueError("Kopia testowa nie odpowiada dokładnemu commitowi")
        identity = {"git_sha": commit, "git_dirty": False,
                    "git_tree": git(selected, "rev-parse", "HEAD^{tree}"), "integrity": "clean_detached_git_tree"}
    version_file = selected / "latka_jazn/version.py"
    version = scope_version(selected)
    if version == "unverified-source" or not all((selected / n).is_file() for n in ("run.py", "main.py")):
        raise ValueError("Nieprawidłowa wersja lub brak publicznego startera SYSTEM")
    identity.update(version=version, version_sha256=sha256(version_file.read_bytes()).hexdigest(),
                    source_kind=kind, source_value=value or ("origin/master" if kind == "master" else str(source_root)))
    return {"root": str(selected), "source": identity, "retained": True}


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--kind", choices=KINDS, default="master")
    parser.add_argument("--value", default="")
    args = parser.parse_args()
    try:
        result = prepare_source(args.root, args.destination, kind=args.kind, value=args.value)
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print(json.dumps({"ok": False, "reason": "Odmowa przygotowania źródła: " + type(exc).__name__}))
        return 1
    print(json.dumps({"ok": True, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
