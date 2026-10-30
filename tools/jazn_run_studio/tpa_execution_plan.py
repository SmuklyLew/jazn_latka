"""Durable dependency plan. Checkpoints contain references, never private runtime."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from .tpa_catalog import execution_map
from .tpa_reports import RunStore, STATES, TERMINAL, redact, safe_child, utc

LIVE_ORDER = ("gui-daemon", "ollama-two-turns", "chat-reconnect", "chat-resume", "daemon-restart")
PHASE_TIMEOUTS = {"preflight": 30, "source": 300, "regression": 180, "start": 60,
                  "heartbeat": 30, "readiness": 45, "generation": 120,
                  "finalization": 30, "restart": 60, "cleanup": 90,
                  "gui": 120, "operator": None}


def build_plan(case_ids: tuple[str, ...], source: dict, model: str = "", *, assisted: bool = False,
               include_live: bool = True) -> dict:
    known = {c["id"] for c in execution_map()}
    if not case_ids or len(set(case_ids)) != len(case_ids) or set(case_ids) - known:
        raise ValueError("Wybierz znane, niepowtarzające się scenariusze planu")
    # Live predecessors are included explicitly; selecting restart cannot bypass
    # the earlier turn/reconnect/resume acceptance gates.
    selected = set(case_ids)
    last_live = max((LIVE_ORDER.index(k) for k in selected if k in LIVE_ORDER), default=-1) if include_live else -1
    selected.update(LIVE_ORDER[:last_live + 1])
    ordered = [c["id"] for c in execution_map() if c["id"] in selected]
    tasks = [{"id": "regression:" + key, "case_id": key, "execution": "regression",
              "depends_on": [], "status": "QUEUED", "run_id": None} for key in ordered]
    for i, key in enumerate(LIVE_ORDER[:last_live + 1]):
        tasks.append({"id": "live:" + key, "case_id": key, "execution": "live", "status": "QUEUED", "run_id": None,
                      "depends_on": ["regression:" + key] + (["live:" + LIVE_ORDER[i - 1]] if i else [])})
    return {"schema": "jazn_tpa_execution_plan/v1", "plan_id": "plan-" + uuid4().hex,
            "system_root": "", "created_utc": utc(), "saved_utc": utc(), "finished_utc": None,
            "owner_pid": os.getpid(), "status": "QUEUED", "source_request": deepcopy(source),
            "source_copy": None, "source_identity": None, "model": model,
            "assisted": assisted, "regression_only": not include_live,
            "timeouts": dict(PHASE_TIMEOUTS), "tasks": tasks}


def blocked_dependencies(plan: dict) -> None:
    """Propagate only terminal non-PASS evidence; queued/running is not failure."""
    by_id = {n["id"]: n for n in plan["tasks"]}
    for node in plan["tasks"]:
        if node["status"] != "QUEUED":
            continue
        bad = [key for key in node["depends_on"] if by_id[key]["status"] in TERMINAL and by_id[key]["status"] != "PASS"]
        if bad:
            node.update(status="BLOCKED", reason="Nie przeszły wymagane kroki: " + ", ".join(bad))


class PhaseDeadline:
    def __init__(self, limits: dict | None = None):
        self.limits = dict(PHASE_TIMEOUTS if limits is None else limits)
        self.phase = "preflight"
        self.started = time.monotonic()

    def enter(self, phase: str) -> None:
        if phase not in self.limits:
            raise ValueError("Nieznana faza odbioru")
        self.phase, self.started = phase, time.monotonic()

    def check(self) -> None:
        limit = self.limits[self.phase]
        if limit is not None and time.monotonic() - self.started > limit:
            raise TimeoutError("Przekroczono limit fazy: " + self.phase)


class PlanStore:
    """Append-only complete checkpoints; no destructive cleanup or cached index."""
    def __init__(self, runs: RunStore):
        self.runs = runs

    def folder(self, plan_id: str) -> Path:
        if not re.fullmatch(r"plan-[0-9a-f]{32}", plan_id):
            raise ValueError("Nieprawidłowy identyfikator planu")
        return safe_child(self.runs.base, plan_id)

    def save(self, plan: dict) -> None:
        folder = self.folder(plan["plan_id"])
        folder.mkdir(parents=True, exist_ok=True)
        plan["saved_utc"] = utc()
        # Bind the checkpoint to the canonical system without storing its
        # potentially sensitive absolute path. This remains stable if a new
        # process has a different environment/redaction secret list.
        plan["system_root"] = self._root_binding()
        clean = deepcopy(plan)
        # Redact externally influenced content only. Redacting public schema
        # names, dependencies or status identifiers makes checkpoints
        # unreadable when an environment secret matches one of those strings.
        for key in ("model", "source_copy", "source_identity"):
            if key in clean:
                clean[key] = redact(clean[key], self.runs.redactor)
        if isinstance(clean.get("source_request"), dict):
            clean["source_request"] = {
                key: (value if key == "kind" else redact(value, self.runs.redactor))
                for key, value in clean["source_request"].items()
            }
        for task in clean.get("tasks", []):
            if isinstance(task, dict):
                for key in tuple(task):
                    if key not in {"id", "case_id", "execution", "depends_on",
                                   "status", "run_id", "started_utc", "finished_utc"}:
                        task[key] = redact(task[key], self.runs.redactor)
        for key in tuple(clean):
            if key not in {"schema", "plan_id", "system_root", "created_utc",
                           "saved_utc", "finished_utc", "owner_pid", "status",
                           "assisted", "regression_only", "timeouts", "tasks", "source_request",
                           "model", "source_copy", "source_identity"}:
                clean[key] = redact(clean[key], self.runs.redactor)
        path = safe_child(folder, "checkpoint-" + uuid4().hex + ".json")
        temporary = safe_child(folder, path.name + ".tmp")
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(clean, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(temporary, path)

    def _root_binding(self) -> str:
        return "sha256:" + sha256(str(self.runs.root).encode("utf-8")).hexdigest()

    def load(self, plan_id: str) -> dict:
        checkpoints = []
        for path in self.folder(plan_id).glob("checkpoint-*.json"):
            path = safe_child(path.parent, path.name)
            if path.stat().st_size > 1024 * 1024:
                raise ValueError("Checkpoint planu przekracza limit")
            value = json.loads(path.read_text(encoding="utf-8"))
            if (not isinstance(value, dict) or value.get("schema") != "jazn_tpa_execution_plan/v1"
                    or value.get("plan_id") != plan_id
                    or value.get("system_root") not in {self._root_binding(), str(self.runs.root)}
                    or not isinstance(value.get("saved_utc"), str) or not isinstance(value.get("tasks"), list)
                    or not isinstance(value.get("source_request"), dict)
                    or not isinstance(value["source_request"].get("kind"), str)
                    or value["source_request"]["kind"] not in {"master", "branch", "pr", "merge", "local", "zip"}
                    or not isinstance(value["source_request"].get("value", ""), str)
                    or not isinstance(value.get("model"), str)
                    or not isinstance(value.get("regression_only", False), bool)):
                raise ValueError("Uszkodzony checkpoint planu")
            known = {c["id"] for c in execution_map()}
            ids = {n.get("id") for n in value["tasks"] if isinstance(n, dict) and isinstance(n.get("id"), str)}
            if len(ids) != len(value["tasks"]) or any(
                    not isinstance(n, dict) or not isinstance(n.get("case_id"), str) or n["case_id"] not in known
                    or not isinstance(n.get("execution"), str) or n["execution"] not in {"regression", "live"}
                    or n.get("id") != n["execution"] + ":" + n["case_id"] or n.get("status") not in STATES
                    or not isinstance(n.get("depends_on"), list) or any(not isinstance(k, str) or k not in ids for k in n["depends_on"])
                    for n in value["tasks"]):
                raise ValueError("Nieprawidłowe kroki planu")
            expected = build_plan(tuple(n["case_id"] for n in value["tasks"] if n["execution"] == "regression"), {},
                                  include_live=not value.get("regression_only", False))
            if [(n["id"], n["depends_on"]) for n in value["tasks"]] != [(n["id"], n["depends_on"]) for n in expected["tasks"]]:
                raise ValueError("Zmieniono zależności kanonicznego planu")
            checkpoints.append(value)
        if not checkpoints:
            raise ValueError("Brak kompletnego checkpointu planu")
        return max(checkpoints, key=lambda p: p["saved_utc"])

    def history(self) -> list[dict]:
        if not self.runs.base.exists():
            return []
        return sorted((self.load(p.name) for p in self.runs.base.glob("plan-*") if p.is_dir()),
                      key=lambda p: p["saved_utc"], reverse=True)


def plan_counts(plan: dict) -> dict[str, int]:
    return dict(Counter(n["status"] for n in plan["tasks"]))
