from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

BASE_SHA = "6c6c3acc2485324e9a2e1b385811f17f5bebf7f7"
TARGET_BRANCH = "fix/release-safe-package-generator-v84"
PATCH_SHA256 = "c7422ec11910d7edbf4261b5c0fc1685c59272e84105559612754bb661cbc5e5"
PATCH_SIZE = 75477
CHUNK_COUNT = 101
CHUNK_ROOT = Path(".automation/release-safe-generator-v84/chunks")
EXPECTED_PATHS = {
    "latka_jazn/tools/package_integrity.py",
    "latka_jazn/tools/release_metadata_sync.py",
    "tests/test_jazn_pack_generator_v82_contract.py",
    "tests/test_jazn_pack_generator_v83_contract.py",
    "tests/test_jazn_pack_generator_v84_contract.py",
    "tests/test_package_integrity_canonical_worktree.py",
    "tests/test_release_metadata_generator_dirty_policy.py",
    "tools/jazn_pack_generator.py",
}


def _run(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=True,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def _git(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return _run("git", *args, capture=capture)


def _reconstruct_patch() -> bytes:
    expected = [CHUNK_ROOT / f"chunk-{index:03d}" for index in range(CHUNK_COUNT)]
    present = sorted(CHUNK_ROOT.glob("chunk-*"))
    if present != expected:
        raise RuntimeError(f"invalid chunk set: expected {CHUNK_COUNT}, found {len(present)}")
    encoded = "".join(path.read_text(encoding="utf-8").strip() for path in expected)
    raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != PATCH_SIZE or digest != PATCH_SHA256:
        raise RuntimeError(
            f"patch integrity mismatch: size={len(raw)} sha256={digest}"
        )
    return raw


def _changed_paths() -> set[str]:
    result = _git("diff", "--name-only", capture=True)
    return {line.strip() for line in (result.stdout or "").splitlines() if line.strip()}


def _bootstrap() -> dict[str, object]:
    patch = _reconstruct_patch()
    _git("fetch", "origin", "master")
    current_master = (_git("rev-parse", "origin/master", capture=True).stdout or "").strip()
    if current_master != BASE_SHA:
        raise RuntimeError(f"master moved: expected {BASE_SHA}, got {current_master}")

    with tempfile.TemporaryDirectory(prefix="jazn-generator-v84-") as temp_raw:
        patch_path = Path(temp_raw) / "generator-v84.patch"
        patch_path.write_bytes(patch)

        _git("switch", "--detach", BASE_SHA)
        _git("switch", "-C", TARGET_BRANCH)
        _git("apply", "--check", str(patch_path))
        _git("apply", str(patch_path))
        _git("diff", "--check")

        changed = _changed_paths()
        if changed != EXPECTED_PATHS:
            raise RuntimeError(
                "unexpected patch paths: "
                f"missing={sorted(EXPECTED_PATHS - changed)}, "
                f"extra={sorted(changed - EXPECTED_PATHS)}"
            )

        _run(
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "compileall",
            "-q",
            "latka_jazn",
            "tests",
            "main.py",
            "run.py",
            "tools/jazn_pack_generator.py",
        )
        _run(
            sys.executable,
            "-X",
            "utf8",
            "tools/jazn_pack_generator.py",
            "self-test",
        )

        _git("config", "user.name", "github-actions[bot]")
        _git(
            "config",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        )
        _git("add", "-A")
        _git("commit", "-m", "fix(generator): preserve release metadata consistency")
        code_sha = (_git("rev-parse", "HEAD", capture=True).stdout or "").strip()

        _run(
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "latka_jazn.tools.release_metadata_sync",
            "--root",
            ".",
            "--base-branch",
            "master",
            "--write",
            "--json",
        )
        metadata_paths = _changed_paths()
        expected_metadata = {
            "PACKAGE_INTEGRITY_MANIFEST.json",
            "SOURCE_PROVENANCE.json",
        }
        if metadata_paths != expected_metadata:
            raise RuntimeError(
                "unexpected metadata paths: "
                f"missing={sorted(expected_metadata - metadata_paths)}, "
                f"extra={sorted(metadata_paths - expected_metadata)}"
            )
        _git("diff", "--check")
        _git("add", "SOURCE_PROVENANCE.json", "PACKAGE_INTEGRITY_MANIFEST.json")
        _git("commit", "-m", "release: synchronize metadata for generator v8.4")
        metadata_sha = (_git("rev-parse", "HEAD", capture=True).stdout or "").strip()

        _run(
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "latka_jazn.tools.release_metadata_sync",
            "--root",
            ".",
            "--base-branch",
            "master",
            "--check",
            "--json",
        )
        if (_git("status", "--porcelain", capture=True).stdout or "").strip():
            raise RuntimeError("target branch is dirty after metadata verification")
        _git("push", "origin", f"HEAD:refs/heads/{TARGET_BRANCH}")

    return {
        "ok": True,
        "bootstrap": True,
        "target_branch": TARGET_BRANCH,
        "code_sha": code_sha,
        "metadata_sha": metadata_sha,
        "patch_sha256": PATCH_SHA256,
    }


def main() -> int:
    if "--write" not in sys.argv or not CHUNK_ROOT.is_dir():
        print(json.dumps({"ok": True, "bootstrap": False}, ensure_ascii=False))
        return 0
    result = _bootstrap()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
