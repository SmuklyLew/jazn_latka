"""Operator-gated, whole-file retirement. Never remove tests merely for green pytest.

Only complete test modules can be retired. Every collected contract must be
explicitly reviewed as obsolete with a current replacement in another module.
An actual move additionally requires a clean non-master checkout, the exact
current HEAD, and fresh successful GitHub check-runs for that SHA.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .core import contracts, effective_contract, load_reviews
from latka_jazn.version import version_slug

GITHUB_REPOSITORY = "SmuklyLew/jazn_latka"


def _file(root: Path, relative: str) -> tuple[str, Path]:
    if not isinstance(relative, str) or len(relative) > 260 or "\x00" in relative:
        raise ValueError("Invalid test path")
    value = relative.replace("\\", "/")
    parts = PurePosixPath(value).parts
    if (len(parts) < 2 or parts[0] != "tests" or parts[1] == "archive"
            or any(p in {"", ".", ".."} for p in parts)
            or not parts[-1].startswith("test_") or not parts[-1].endswith(".py")
            or value.startswith("/") or ":" in value):
        raise ValueError("Only active tests/test_*.py modules may be archived")
    root = root.resolve()
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symlink in test source path")
    if not current.is_file() or not current.resolve().is_relative_to(root / "tests"):
        raise ValueError("Test source file is unavailable")
    return "/".join(parts), current


def preview(root: Path, relative: str) -> dict:
    """Read-only archival plan; no green test results are inferred."""
    root = Path(root).resolve()
    name, path = _file(root, relative)
    catalog = contracts(root)
    review_map = load_reviews(root).get("reviews", {})
    if not isinstance(review_map, dict):
        review_map = {}
    nodes = sorted(k for k in catalog if k.split("::", 1)[0].replace("\\", "/") == name)
    missing: list[str] = []
    replacements: dict[str, str] = {}
    if not nodes:
        missing.append("No active test contracts identify this module")
    for nodeid in nodes:
        review = review_map.get(nodeid)
        if not isinstance(review, dict) or review.get("status") != "obsolete":
            missing.append(nodeid + ": missing explicit obsolete review")
            continue
        replacement = review.get("replacement_nodeid", "")
        if not isinstance(replacement, str) or not replacement or replacement not in catalog:
            missing.append(nodeid + ": missing a known replacement")
            continue
        if replacement.split("::", 1)[0] == name:
            missing.append(nodeid + ": replacement must be in another file")
            continue
        if effective_contract(root, replacement).get("status") != "current":
            missing.append(nodeid + ": replacement is not current")
            continue
        replacements[nodeid] = replacement
    return {
        "schema": "jazn_test_retirement_preview/v1",
        "file": name,
        "source_sha256": sha256(path.read_bytes()).hexdigest(),
        "contracts_in_file": len(nodes),
        "reviewed_with_current_replacements": len(replacements),
        "replacements": replacements,
        "status": "REVIEW_READY" if not missing else "BLOCKED",
        "blockers": missing,
        "full_release_gate": "NOT_VERIFIED",
        "automatic_archival": False,
    }


def _git(root: Path, *args: str) -> str:
    outcome = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        timeout=15, check=False,
    )
    if outcome.returncode:
        raise ValueError("Cannot verify clean Git checkout")
    return outcome.stdout.strip()


def _green_checks(head: str) -> list[str]:
    """Verify the most recent result for every check on the exact GitHub SHA."""
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("Invalid commit SHA")
    runs: list[dict] = []
    total: int | None = None
    try:
        for page in range(1, 11):
            address = (
                "https://api.github.com/repos/" + GITHUB_REPOSITORY
                + "/commits/" + head + "/check-runs?per_page=100&page=" + str(page)
            )
            request = Request(
                address, headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "jazn-tests-studio",
                },
            )
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read(512_000))
            if not isinstance(payload, dict):
                raise ValueError("Invalid GitHub checks")
            observed = payload.get("total_count")
            rows = payload.get("check_runs")
            if (not isinstance(observed, int) or not 0 < observed <= 1000
                    or total is not None and total != observed
                    or not isinstance(rows, list)
                    or len(rows) > 100
                    or any(not isinstance(row, dict) for row in rows)):
                raise ValueError("Incomplete GitHub checks")
            total = observed
            runs.extend(rows)
            if len(runs) >= total:
                break
            if not rows:
                raise ValueError("Missing GitHub checks page")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise ValueError("Unable to verify GitHub checks on the exact HEAD") from exc
    if total is None or len(runs) != total:
        raise ValueError("Incomplete GitHub checks; refusing retirement")
    latest: dict[str, dict] = {}
    for run in runs:
        name = run.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Unnamed GitHub check")
        prior = latest.get(name)
        if prior is None or (run.get("id") or 0) > (prior.get("id") or 0):
            latest[name] = run
    # The catalog/definition gate is necessary: a stale catalog could hide
    # new test functions in a whole-file retirement candidate.
    required = (
        "manifest_sync",
        "Validate stable Test Studio contracts",
        "test (ubuntu-latest, 3.12)",
        "test (windows-latest, 3.12)",
    )
    if any(name not in latest for name in required):
        raise ValueError("Required release/Windows/Linux checks are missing")
    if any(run.get("status") != "completed" or run.get("conclusion") != "success"
           for run in latest.values()):
        raise ValueError("GitHub checks are not all successful")
    return sorted(latest)


def archive_file(root: Path, relative: str, *, expected_sha256: str,
                 expected_head: str, confirmation: str) -> dict:
    """Archive exact source bytes and remove original only after explicit proof.

    The resulting code change must receive fresh CI again before merge.
    The operator is still responsible for full TPA acceptance, as applicable.
    """
    if confirmation != "ARCHIWIZUJ":
        raise ValueError("Explicit ARCHIWIZUJ confirmation required")
    root = Path(root).resolve()
    report = preview(root, relative)
    if report["status"] != "REVIEW_READY":
        raise ValueError("Incomplete obsolete reviews or replacement contracts")
    if expected_sha256 != report["source_sha256"]:
        raise ValueError("Source file changed since preview")
    if _git(root, "status", "--porcelain"):
        raise ValueError("Retirement requires a clean working tree")
    branch = _git(root, "branch", "--show-current")
    if not branch or branch in {"master", "main"}:
        raise ValueError("Retirement is allowed only on a feature branch")
    head = _git(root, "rev-parse", "HEAD")
    if head != expected_head:
        raise ValueError("The reviewed HEAD differs from the active branch")
    checks = _green_checks(head)
    name, source = _file(root, relative)
    archive = root / "tests" / "archive" / (
        "retired-" + version_slug().replace("/", "_") + "-" + head[:12]
    ) / name
    if archive.exists() or archive.is_symlink():
        raise ValueError("Archive target already exists; append-only history")
    # Check all existing ancestors *before* creating anything in archive.
    for parent in [archive.parent, *archive.parent.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("Archive target includes a symlink")
    archive.parent.mkdir(parents=True, exist_ok=True)
    metadata = archive.with_suffix(".retirement.json")
    if metadata.exists() or metadata.is_symlink():
        raise ValueError("Retirement metadata already exists")
    blob = source.read_bytes()
    if sha256(blob).hexdigest() != expected_sha256:
        raise ValueError("Source bytes changed")
    with archive.open("xb") as stream:
        stream.write(blob)
        stream.flush()
        os.fsync(stream.fileno())
    if sha256(archive.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("Archive verification failed; source retained")
    payload = {
        "schema": "jazn_test_retirement/v1", "source": name,
        "source_sha256": expected_sha256, "source_head_sha": head,
        "source_branch": branch, "replacement_nodeids": report["replacements"],
        "verified_check_names": checks, "post_archival_ci": "PENDING",
        "full_tpa_acceptance": "NOT_IMPLIED",
    }
    with metadata.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    # No original test file is removed before durable, verified archive.
    source.unlink()
    return {**payload, "archived_path": str(archive.relative_to(root)),
            "next_action": "Sync Test Studio catalog and rerun required CI on the new commit"}
