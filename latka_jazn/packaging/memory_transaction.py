from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import hashlib
import os
import shutil
import uuid


class MemoryTransactionError(RuntimeError):
    pass


def _nearest_existing(path: Path) -> Path:
    current = Path(path).resolve()
    while not current.exists() and current.parent != current:
        current = current.parent
    return current


def same_filesystem(left: Path, right: Path) -> bool:
    try:
        return os.stat(_nearest_existing(left)).st_dev == os.stat(_nearest_existing(right)).st_dev
    except OSError:
        return False


def tree_fingerprint(root: Path) -> str:
    base = Path(root).resolve()
    digest = hashlib.sha256()
    for path in sorted(p for p in base.rglob("*") if p.is_file() and not p.is_symlink()):
        rel = path.relative_to(base).as_posix()
        item = hashlib.sha256()
        size = 0
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                item.update(block); size += len(block)
        digest.update(f"{rel}\0{size}\0{item.hexdigest()}\n".encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class MemoryPromotionResult:
    target_memory: Path
    backup_memory: Path | None
    failed_memory: Path | None
    had_previous: bool
    backup_mode: str


def promote_memory_tree(
    *,
    source_memory: Path,
    target_memory: Path,
    workspace: Path,
    fault_injector: Callable[[str], None] | None = None,
    post_promote: Callable[[], None] | None = None,
) -> MemoryPromotionResult:
    source_memory = Path(source_memory).resolve()
    target_memory = Path(target_memory).resolve()
    workspace = Path(workspace).resolve()
    if not source_memory.is_dir():
        raise MemoryTransactionError(f"source memory tree missing: {source_memory}")
    target_parent = target_memory.parent
    target_parent.mkdir(parents=True, exist_ok=True)
    txid = uuid.uuid4().hex
    transaction = target_parent / f".jazn-memory-attach-{txid}"
    staged_memory = transaction / "memory"
    failed_memory = transaction / "failed-memory"
    transaction.mkdir(parents=False, exist_ok=False)
    source_fp = tree_fingerprint(source_memory)
    shutil.copytree(source_memory, staged_memory)
    if tree_fingerprint(staged_memory) != source_fp:
        shutil.rmtree(transaction, ignore_errors=True)
        raise MemoryTransactionError("staged memory copy fingerprint mismatch")

    previous = target_memory if target_memory.exists() else None
    had_previous = previous is not None
    backup_root = workspace / "memory_attach_backups" / txid
    backup_mode = "workspace_same_filesystem"
    if had_previous and not same_filesystem(previous.parent, backup_root.parent):
        backup_root = target_parent / ".jazn-memory-attach-backups" / txid
        backup_mode = "target_filesystem"
    backup_memory = backup_root / "memory" if had_previous else None
    old_moved = False
    new_promoted = False
    try:
        if had_previous and backup_memory is not None:
            backup_memory.parent.mkdir(parents=True, exist_ok=False)
            os.replace(previous, backup_memory)
            old_moved = True
            if fault_injector:
                fault_injector("after_old_renamed")
        os.replace(staged_memory, target_memory)
        new_promoted = True
        if fault_injector:
            fault_injector("after_new_promoted")
        if post_promote:
            post_promote()
        if fault_injector:
            fault_injector("before_commit_complete")
    except Exception:
        if new_promoted and target_memory.exists():
            failed_memory.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target_memory, failed_memory)
        if old_moved and backup_memory is not None and backup_memory.exists():
            target_memory.parent.mkdir(parents=True, exist_ok=True)
            os.replace(backup_memory, target_memory)
        raise
    finally:
        if staged_memory.exists():
            shutil.rmtree(staged_memory, ignore_errors=True)
    if transaction.exists() and not any(transaction.iterdir()):
        transaction.rmdir()
    return MemoryPromotionResult(
        target_memory=target_memory,
        backup_memory=backup_memory if backup_memory and backup_memory.exists() else None,
        failed_memory=failed_memory if failed_memory.exists() else None,
        had_previous=had_previous,
        backup_mode=backup_mode,
    )
