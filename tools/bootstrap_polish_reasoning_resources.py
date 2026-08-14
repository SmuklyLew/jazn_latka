from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

INSTALL_SCHEMA = "latka_polish_reasoning_install/v2"
MORFEUSZ_REQUIREMENT = "morfeusz2==1.99.15"
STANZA_REQUIREMENT = "stanza>=1.14,<2"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_data_root() -> Path:
    return (project_root() / "latka_jazn" / "local_resources" / "nlp").resolve()


def _run(command: list[str], *, dry_run: bool) -> None:
    print("+", subprocess.list2cmdline(command))
    if not dry_run:
        subprocess.run(command, check=True)


def _pip_install(requirements: list[str], *, dry_run: bool, only_binary: bool = False) -> None:
    command = [sys.executable, "-m", "pip", "install", "--upgrade"]
    if only_binary:
        command.append("--only-binary=:all:")
    command.extend(requirements)
    _run(command, dry_run=dry_run)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_manifest(root: Path) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    if root.exists():
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            files.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )
    return {"file_count": len(files), "files": files}


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def install_morfeusz(*, dry_run: bool) -> dict[str, Any]:
    _pip_install([MORFEUSZ_REQUIREMENT], dry_run=dry_run, only_binary=True)
    version = None if dry_run else _package_version("morfeusz2")
    return {
        "provider": "morfeusz2-sgjp",
        "planned": dry_run,
        "installed": False if dry_run else version is not None,
        "version": version,
        "requirement": MORFEUSZ_REQUIREMENT,
        "license": "BSD-2-Clause; Morfeusz2 with SGJP data",
        "source_url": "https://pypi.org/project/morfeusz2/",
        "distribution": "PyPI wheel",
    }


def install_stanza(data_root: Path, *, dry_run: bool) -> dict[str, Any]:
    _pip_install([STANZA_REQUIREMENT], dry_run=dry_run)
    model_dir = data_root / "stanza"
    if dry_run:
        return {
            "provider": "stanza-pl",
            "planned": True,
            "installed": False,
            "requirement": STANZA_REQUIREMENT,
            "data_path": str(model_dir),
        }

    import stanza  # type: ignore

    model_dir.mkdir(parents=True, exist_ok=True)
    stanza.download(
        "pl",
        model_dir=str(model_dir),
        processors="tokenize,pos,lemma,depparse",
        verbose=False,
    )
    pipeline = stanza.Pipeline(
        lang="pl",
        processors="tokenize,pos,lemma,depparse",
        dir=str(model_dir),
        download_method=None,
        use_gpu=False,
        verbose=False,
    )
    probe = pipeline("To jest test polskiego modelu Stanza.")
    if not getattr(probe, "sentences", None):
        raise RuntimeError("stanza_pl_validation_failed:no_sentences")
    if not (model_dir / "resources.json").is_file() or not (model_dir / "pl").is_dir():
        raise RuntimeError("stanza_pl_validation_failed:missing_local_resources")

    return {
        "provider": "stanza-pl",
        "planned": False,
        "installed": True,
        "version": _package_version("stanza"),
        "requirement": STANZA_REQUIREMENT,
        "data_path": str(model_dir),
        "license": "Apache-2.0 library; model-specific licenses are recorded in resources.json",
        "source_url": "https://stanfordnlp.github.io/stanza/download_models.html",
        "tree": _tree_manifest(model_dir),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install verified Polish NLP resources next to the Jaźń package."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=(
            "Persistent data directory. Defaults to "
            "<project>/latka_jazn/local_resources/nlp."
        ),
    )
    parser.add_argument(
        "--profile",
        choices=("core", "recommended"),
        default="core",
        help=(
            "core installs Morfeusz2; recommended additionally installs and validates "
            "the Polish Stanza tokenize/POS/lemma/depparse models."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_root = (
        args.data_dir.expanduser().resolve()
        if args.data_dir is not None
        else default_data_root()
    )
    print(f"NLP data root: {data_root}")
    if not args.dry_run:
        data_root.mkdir(parents=True, exist_ok=True)

    resources = [install_morfeusz(dry_run=args.dry_run)]
    if args.profile == "recommended":
        resources.append(install_stanza(data_root, dry_run=args.dry_run))

    manifest = {
        "schema_version": INSTALL_SCHEMA,
        "python": sys.version,
        "profile": args.profile,
        "data_root": str(data_root),
        "dry_run": args.dry_run,
        "resources": resources,
        "truth_boundary": (
            "Only declared upstream packages and the Polish Stanza model are installed. "
            "The installer stores persistent data under latka_jazn/local_resources/nlp, "
            "which is excluded from Git. Runtime providers never download during a turn."
        ),
    }
    rendered = json.dumps(manifest, ensure_ascii=False, indent=2)
    print(rendered)
    if not args.dry_run:
        (data_root / "install_manifest.json").write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
