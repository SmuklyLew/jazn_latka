from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback

BASE_SHA = "6c6c3acc2485324e9a2e1b385811f17f5bebf7f7"
TARGET_BRANCH = "fix/release-safe-package-generator-v84"
ERROR_BRANCH = "diagnostic/release-safe-package-generator-v84"
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
        list(args), check=True, text=True, encoding="utf-8",
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def _git(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return _run("git", *args, capture=capture)


def _patch_bytes() -> bytes:
    expected = [CHUNK_ROOT / f"chunk-{index:03d}" for index in range(CHUNK_COUNT)]
    present = sorted(CHUNK_ROOT.glob("chunk-*"))
    if present != expected:
        raise RuntimeError(f"invalid chunk set: expected {CHUNK_COUNT}, found {len(present)}")
    encoded = "".join(path.read_text(encoding="utf-8").strip() for path in expected)
    raw = base64.b64decode(encoded.encode("ascii"), validate=True)
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != PATCH_SIZE or digest != PATCH_SHA256:
        raise RuntimeError(f"patch integrity mismatch: size={len(raw)} sha256={digest}")
    return raw


def _bootstrap() -> dict[str, object]:
    patch = _patch_bytes()
    _git("fetch", "origin", "master")
    remote_master = (_git("rev-parse", "origin/master", capture=True).stdout or "").strip()
    if remote_master != BASE_SHA:
        raise RuntimeError(f"master moved: expected {BASE_SHA}, got {remote_master}")
    with tempfile.TemporaryDirectory(prefix="jazn-generator-v84-") as temp_raw:
        patch_path = Path(temp_raw) / "generator-v84.patch"
        patch_path.write_bytes(patch)
        _git("switch", "--detach", BASE_SHA)
        _git("switch", "-C", TARGET_BRANCH)
        _git("apply", "--check", str(patch_path))
        _git("apply", str(patch_path))
        _git("diff", "--check")
        changed = {
            line.strip()
            for line in (_git("diff", "--name-only", capture=True).stdout or "").splitlines()
            if line.strip()
        }
        if changed != EXPECTED_PATHS:
            raise RuntimeError(
                f"unexpected patch paths: missing={sorted(EXPECTED_PATHS - changed)}, "
                f"extra={sorted(changed - EXPECTED_PATHS)}"
            )
        _git("config", "user.name", "github-actions[bot]")
        _git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        _git("add", "-A")
        _git("commit", "-m", "fix(generator): preserve release metadata consistency")
        commit_sha = (_git("rev-parse", "HEAD", capture=True).stdout or "").strip()
        _git("push", "origin", f"HEAD:refs/heads/{TARGET_BRANCH}")
    return {"ok": True, "bootstrap": True, "target_branch": TARGET_BRANCH, "commit_sha": commit_sha, "patch_sha256": PATCH_SHA256}


def _publish_error(text: str) -> None:
    try:
        subprocess.run(["git", "reset", "--hard"], check=False)
        subprocess.run(["git", "clean", "-fd"], check=False)
        _git("switch", "--detach", BASE_SHA)
        _git("switch", "-C", ERROR_BRANCH)
        Path("BOOTSTRAP_ERROR.txt").write_text(text, encoding="utf-8")
        _git("config", "user.name", "github-actions[bot]")
        _git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        _git("add", "BOOTSTRAP_ERROR.txt")
        _git("commit", "-m", "diagnostic: record generator bootstrap failure")
        _git("push", "--force", "origin", f"HEAD:refs/heads/{ERROR_BRANCH}")
    except Exception:
        pass


def main() -> int:
    if "--write" not in sys.argv or not CHUNK_ROOT.is_dir():
        print(json.dumps({"ok": True, "bootstrap": False}, ensure_ascii=False))
        return 0
    try:
        result = _bootstrap()
    except Exception:
        diagnostic = traceback.format_exc()
        print(diagnostic, file=sys.stderr)
        _publish_error(diagnostic)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
