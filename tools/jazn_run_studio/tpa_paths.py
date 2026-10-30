"""Short-lived, run-scoped authority for isolated TPA staging directories."""
from __future__ import annotations

import hmac
import json
from pathlib import Path
import re
import time
from uuid import uuid4

from latka_jazn.tools.application_shell.operator_paths import validate_operator_path
from .tpa_catalog import scenario
from .tpa_reports import safe_child

TOKEN_ENV = "JAZN_TPA_RUN_TOKEN"
MAX_START_AGE = 900
MAX_CLEANUP_AGE = 86400


def issue_staging(root: Path, run_folder: Path, case_id: str) -> tuple[Path, str]:
    """Create a fresh destination and exclusive claim; never reuse a staging."""
    scenario(case_id)
    if not re.fullmatch(r"run-[0-9a-f]{32}", run_folder.name):
        raise ValueError("Nieprawidłowy przebieg TPA")
    folder = safe_child(run_folder, "live-" + case_id)
    validate_operator_path(folder, root, directory=True, allow_acceptance_operator=True)
    folder.mkdir(exist_ok=False)
    token = uuid4().hex + uuid4().hex
    claim = safe_child(run_folder, folder.name + ".claim.json")
    with claim.open("x", encoding="utf-8") as stream:
        json.dump({"schema": "tpa_staging/v1", "root": str(root.resolve()),
                   "folder": str(folder.resolve()), "run_id": run_folder.name,
                   "case_id": case_id, "created": time.time(), "token": token}, stream)
    return folder, token


def validate_staging(root: Path, raw: Path, run_id: str, case_id: str,
                     token: str, *, cleaning: bool = False) -> Path:
    """Reject aliases before resolving, then require the exact run capability."""
    scenario(case_id)
    if (not raw.is_absolute() or ".." in raw.parts
            or re.fullmatch(r"run-[0-9a-f]{32}", run_id) is None
            or raw.parent.name != run_id or raw.name != "live-" + case_id):
        raise ValueError("Katalog nie należy do bieżącego scenariusza i przebiegu TPA")
    folder = safe_child(raw.parent, raw.name)
    validate_operator_path(folder, root, directory=True, allow_acceptance_operator=True)
    if not folder.is_dir():
        raise ValueError("Brak katalogu odbioru TPA")
    claim = safe_child(folder.parent, folder.name + ".claim.json")
    if not claim.is_file() or claim.stat().st_size > 4096:
        raise ValueError("Brak poprawnego uprawnienia przebiegu TPA")
    saved = json.loads(claim.read_text(encoding="utf-8"))
    if (not isinstance(saved, dict) or saved.get("schema") != "tpa_staging/v1"
            or saved.get("root") != str(root.resolve())
            or saved.get("folder") != str(folder.resolve())
            or saved.get("run_id") != run_id or saved.get("case_id") != case_id
            or not isinstance(saved.get("token"), str) or not token
            or not hmac.compare_digest(saved["token"], token)):
        raise ValueError("Niezgodne uprawnienie przebiegu TPA")
    created = saved.get("created")
    if (not isinstance(created, (int, float)) or isinstance(created, bool)
            or not 0 <= time.time() - created <= (MAX_CLEANUP_AGE if cleaning else MAX_START_AGE)):
        raise ValueError("Nieaktualne uprawnienie przebiegu TPA")
    # Validate known mutable descendants even on recovery. Never follow a
    # redirected owner, staging root, runtime, MEMORY or operator directory.
    for name in ("SYSTEM", "runtime", "memory", "operator", "owner.json", "cancel.flag"):
        safe_child(folder, name)
    if not cleaning:
        if any(folder.iterdir()):
            raise ValueError("Odbiór wymaga świeżego pustego katalogu TPA")
        started = safe_child(folder.parent, folder.name + ".started")
        with started.open("x", encoding="utf-8") as stream:
            stream.write(run_id)
    return folder
