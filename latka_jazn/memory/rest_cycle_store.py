from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
import json
import sqlite3

from latka_jazn.db.runtime_sqlite import connect_runtime_writable, runtime_sqlite_write_guard
import threading
import uuid

from latka_jazn.memory.rest_contracts import canonical_json, sha256_text
from latka_jazn.version import PACKAGE_VERSION_FULL, schema_version

SCHEMA_VERSION = schema_version("rest_cycle_store")

SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS rest_meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rest_episodes(
  episode_id TEXT PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('active','completed','interrupted','failed')),
  trigger TEXT NOT NULL,
  runtime_version TEXT NOT NULL,
  continuity_mode TEXT NOT NULL,
  continuity_claim_allowed INTEGER NOT NULL,
  shadow_mode INTEGER NOT NULL,
  started_at_utc TEXT NOT NULL,
  ended_at_utc TEXT,
  started_monotonic_ns INTEGER NOT NULL,
  ended_monotonic_ns INTEGER,
  cycle_count INTEGER NOT NULL DEFAULT 0,
  last_error TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rest_single_active_episode
  ON rest_episodes(status) WHERE status='active';
CREATE TABLE IF NOT EXISTS rest_cycles(
  cycle_id TEXT PRIMARY KEY,
  episode_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('running','completed','skipped','failed')),
  idle_seconds REAL NOT NULL,
  started_at_utc TEXT NOT NULL,
  ended_at_utc TEXT,
  started_monotonic_ns INTEGER NOT NULL,
  ended_monotonic_ns INTEGER,
  phase_reached INTEGER NOT NULL DEFAULT 0,
  model_status TEXT,
  error TEXT,
  payload_sha256 TEXT,
  UNIQUE(episode_id,ordinal),
  FOREIGN KEY(episode_id) REFERENCES rest_episodes(episode_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rest_cycles_episode ON rest_cycles(episode_id,ordinal);
CREATE TABLE IF NOT EXISTS rest_replay_items(
  cycle_id TEXT NOT NULL,
  source_memory_id TEXT NOT NULL,
  source_tier TEXT NOT NULL,
  kind TEXT NOT NULL,
  truth_status TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  domain TEXT NOT NULL,
  score REAL NOT NULL CHECK(score BETWEEN 0.0 AND 1.0),
  provenance_json TEXT NOT NULL,
  selected_at_utc TEXT NOT NULL,
  PRIMARY KEY(cycle_id,source_memory_id),
  FOREIGN KEY(cycle_id) REFERENCES rest_cycles(cycle_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rest_replay_memory ON rest_replay_items(source_memory_id,selected_at_utc DESC);
CREATE TABLE IF NOT EXISTS dream_scenes(
  scene_id TEXT PRIMARY KEY,
  cycle_id TEXT NOT NULL UNIQUE,
  simulation_kind TEXT NOT NULL CHECK(simulation_kind IN ('simulated_internal','counterfactual','rehearsal','associative')),
  content TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  generator_provider TEXT NOT NULL,
  generator_model TEXT NOT NULL,
  generator_status TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  factual_claim_allowed INTEGER NOT NULL DEFAULT 0 CHECK(factual_claim_allowed=0),
  FOREIGN KEY(cycle_id) REFERENCES rest_cycles(cycle_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS dream_source_links(
  scene_id TEXT NOT NULL,
  source_memory_id TEXT NOT NULL,
  source_content_sha256 TEXT NOT NULL,
  relation TEXT NOT NULL,
  PRIMARY KEY(scene_id,source_memory_id),
  FOREIGN KEY(scene_id) REFERENCES dream_scenes(scene_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS dream_evaluations(
  evaluation_id TEXT PRIMARY KEY,
  scene_id TEXT NOT NULL UNIQUE,
  groundedness REAL NOT NULL,
  source_consistency REAL NOT NULL,
  novelty REAL NOT NULL,
  utility REAL NOT NULL,
  uncertainty REAL NOT NULL,
  self_reference_risk REAL NOT NULL,
  real_source_anchor_count INTEGER NOT NULL,
  recommended_disposition TEXT NOT NULL,
  reasons_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  FOREIGN KEY(scene_id) REFERENCES dream_scenes(scene_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS rest_consolidation_decisions(
  decision_id TEXT PRIMARY KEY,
  scene_id TEXT NOT NULL UNIQUE,
  disposition TEXT NOT NULL,
  target_tier TEXT,
  automatic_l3_allowed INTEGER NOT NULL DEFAULT 0 CHECK(automatic_l3_allowed=0),
  real_source_anchor_count INTEGER NOT NULL,
  materialized_memory_id TEXT,
  reasons_json TEXT NOT NULL,
  decided_at_utc TEXT NOT NULL,
  FOREIGN KEY(scene_id) REFERENCES dream_scenes(scene_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS rest_wake_reports(
  report_id TEXT PRIMARY KEY,
  episode_id TEXT NOT NULL UNIQUE,
  generated_at_utc TEXT NOT NULL,
  report_json TEXT NOT NULL,
  report_sha256 TEXT NOT NULL,
  validation_status TEXT NOT NULL CHECK(validation_status IN ('valid','invalid')),
  FOREIGN KEY(episode_id) REFERENCES rest_episodes(episode_id) ON DELETE CASCADE
);
"""


class RestCycleStore:
    def __init__(self, path: str | Path, *, busy_timeout_ms: int = 30_000, synchronous: str = "FULL") -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.busy_timeout_ms = max(1000, int(busy_timeout_ms))
        self.con = connect_runtime_writable(
            self.path,
            timeout_ms=self.busy_timeout_ms,
            synchronous=synchronous,
            isolation_level=None,
            check_same_thread=False,
        )
        with runtime_sqlite_write_guard(self.path, timeout_ms=self.busy_timeout_ms):
            self.con.executescript(SCHEMA_SQL)
            self.con.execute("INSERT OR REPLACE INTO rest_meta(key,value) VALUES('schema_version',?)", (SCHEMA_VERSION,))
            self.con.execute("INSERT OR REPLACE INTO rest_meta(key,value) VALUES('runtime_version',?)", (PACKAGE_VERSION_FULL,))
            self.con.execute(
                "INSERT OR REPLACE INTO rest_meta(key,value) VALUES('truth_boundary',?)",
                ("Synthetic rest content is isolated from factual memory and cannot auto-promote to L3.",),
            )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock, runtime_sqlite_write_guard(self.path, timeout_ms=self.busy_timeout_ms):
            if self.con.in_transaction:
                raise RuntimeError("nested rest-cycle transactions are forbidden")
            self.con.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self.con.rollback()
                raise
            else:
                self.con.commit()

    def close(self) -> None:
        with runtime_sqlite_write_guard(self.path, timeout_ms=self.busy_timeout_ms):
            self.con.close()

    def __enter__(self) -> "RestCycleStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def active_episode(self) -> dict[str, Any] | None:
        row = self.con.execute("SELECT * FROM rest_episodes WHERE status='active' ORDER BY started_at_utc DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def start_episode(
        self,
        *,
        trigger: str,
        continuity_mode: str,
        continuity_claim_allowed: bool,
        shadow_mode: bool,
        started_at_utc: str,
        started_monotonic_ns: int,
    ) -> str:
        existing = self.active_episode()
        if existing:
            return str(existing["episode_id"])
        episode_id = uuid.uuid4().hex
        with self.transaction():
            self.con.execute(
                """INSERT INTO rest_episodes(
                   episode_id,status,trigger,runtime_version,continuity_mode,continuity_claim_allowed,shadow_mode,
                   started_at_utc,started_monotonic_ns) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    episode_id,
                    "active",
                    trigger,
                    PACKAGE_VERSION_FULL,
                    continuity_mode,
                    int(bool(continuity_claim_allowed)),
                    int(bool(shadow_mode)),
                    started_at_utc,
                    int(started_monotonic_ns),
                ),
            )
        return episode_id

    def finish_episode(
        self,
        episode_id: str,
        *,
        status: str,
        ended_at_utc: str,
        ended_monotonic_ns: int,
        error: str | None = None,
    ) -> None:
        if status not in {"completed", "interrupted", "failed"}:
            raise ValueError("invalid terminal rest episode status")
        with self.transaction():
            self.con.execute(
                """UPDATE rest_episodes SET status=?,ended_at_utc=?,ended_monotonic_ns=?,last_error=?
                   WHERE episode_id=? AND status='active'""",
                (status, ended_at_utc, int(ended_monotonic_ns), error, episode_id),
            )

    def recover_open_episode(self, *, ended_at_utc: str, ended_monotonic_ns: int) -> str | None:
        active = self.active_episode()
        if not active:
            return None
        episode_id = str(active["episode_id"])
        self.finish_episode(
            episode_id,
            status="interrupted",
            ended_at_utc=ended_at_utc,
            ended_monotonic_ns=ended_monotonic_ns,
            error="daemon_restart_or_unclean_rest_shutdown",
        )
        return episode_id

    def next_cycle_ordinal(self, episode_id: str) -> int:
        row = self.con.execute("SELECT COALESCE(MAX(ordinal),0)+1 FROM rest_cycles WHERE episode_id=?", (episode_id,)).fetchone()
        return int(row[0])

    def begin_cycle(
        self,
        *,
        episode_id: str,
        ordinal: int,
        idle_seconds: float,
        started_at_utc: str,
        started_monotonic_ns: int,
    ) -> str:
        cycle_id = sha256_text(f"{episode_id}|{ordinal}")
        with self.transaction():
            self.con.execute(
                """INSERT INTO rest_cycles(
                   cycle_id,episode_id,ordinal,status,idle_seconds,started_at_utc,started_monotonic_ns)
                   VALUES(?,?,?,?,?,?,?)""",
                (cycle_id, episode_id, int(ordinal), "running", float(idle_seconds), started_at_utc, int(started_monotonic_ns)),
            )
        return cycle_id

    def update_cycle_phase(self, cycle_id: str, phase_reached: int, *, model_status: str | None = None) -> None:
        with self.transaction():
            self.con.execute(
                "UPDATE rest_cycles SET phase_reached=MAX(phase_reached,?),model_status=COALESCE(?,model_status) WHERE cycle_id=?",
                (int(phase_reached), model_status, cycle_id),
            )

    def finish_cycle(
        self,
        cycle_id: str,
        *,
        status: str,
        ended_at_utc: str,
        ended_monotonic_ns: int,
        phase_reached: int,
        model_status: str | None,
        error: str | None,
        payload: dict[str, Any],
    ) -> None:
        if status not in {"completed", "skipped", "failed"}:
            raise ValueError("invalid terminal rest cycle status")
        digest = sha256_text(canonical_json(payload))
        with self.transaction():
            self.con.execute(
                """UPDATE rest_cycles SET status=?,ended_at_utc=?,ended_monotonic_ns=?,phase_reached=?,
                   model_status=?,error=?,payload_sha256=? WHERE cycle_id=?""",
                (status, ended_at_utc, int(ended_monotonic_ns), int(phase_reached), model_status, error, digest, cycle_id),
            )
            self.con.execute(
                "UPDATE rest_episodes SET cycle_count=(SELECT COUNT(*) FROM rest_cycles WHERE episode_id=rest_episodes.episode_id) "
                "WHERE episode_id=(SELECT episode_id FROM rest_cycles WHERE cycle_id=?)",
                (cycle_id,),
            )

    def add_replay_item(self, cycle_id: str, item: Any, *, selected_at_utc: str) -> None:
        with self.transaction():
            self.con.execute(
                """INSERT OR REPLACE INTO rest_replay_items(
                   cycle_id,source_memory_id,source_tier,kind,truth_status,content_sha256,domain,score,provenance_json,selected_at_utc)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    cycle_id,
                    item.source_memory_id,
                    item.source_tier,
                    item.kind,
                    item.truth_status,
                    item.content_sha256,
                    item.domain,
                    float(item.score),
                    canonical_json(item.provenance),
                    selected_at_utc,
                ),
            )

    def recent_replay_memory_ids(self, *, limit_cycles: int = 4) -> set[str]:
        rows = self.con.execute(
            """SELECT DISTINCT source_memory_id FROM rest_replay_items WHERE cycle_id IN (
               SELECT cycle_id FROM rest_cycles ORDER BY started_at_utc DESC LIMIT ?)
            """,
            (max(1, int(limit_cycles)),),
        ).fetchall()
        return {str(row[0]) for row in rows}

    def add_scene(self, scene: Any, replay_items: list[Any]) -> None:
        with self.transaction():
            self.con.execute(
                """INSERT INTO dream_scenes(
                   scene_id,cycle_id,simulation_kind,content,content_sha256,generator_provider,generator_model,
                   generator_status,created_at_utc,factual_claim_allowed) VALUES(?,?,?,?,?,?,?,?,?,0)""",
                (
                    scene.scene_id,
                    scene.cycle_id,
                    scene.simulation_kind.value,
                    scene.content,
                    scene.content_sha256,
                    scene.generator_provider,
                    scene.generator_model,
                    scene.generator_status,
                    scene.created_at_utc,
                ),
            )
            for item in replay_items:
                self.con.execute(
                    """INSERT INTO dream_source_links(scene_id,source_memory_id,source_content_sha256,relation)
                       VALUES(?,?,?,?)""",
                    (scene.scene_id, item.source_memory_id, item.content_sha256, "replay_source"),
                )

    def add_evaluation(self, evaluation: Any) -> None:
        with self.transaction():
            self.con.execute(
                """INSERT INTO dream_evaluations(
                   evaluation_id,scene_id,groundedness,source_consistency,novelty,utility,uncertainty,
                   self_reference_risk,real_source_anchor_count,recommended_disposition,reasons_json,created_at_utc)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    evaluation.evaluation_id,
                    evaluation.scene_id,
                    float(evaluation.groundedness),
                    float(evaluation.source_consistency),
                    float(evaluation.novelty),
                    float(evaluation.utility),
                    float(evaluation.uncertainty),
                    float(evaluation.self_reference_risk),
                    int(evaluation.real_source_anchor_count),
                    evaluation.recommended_disposition.value,
                    canonical_json(evaluation.reasons),
                    evaluation.created_at_utc,
                ),
            )

    def add_consolidation_decision(self, decision: Any) -> None:
        with self.transaction():
            self.con.execute(
                """INSERT INTO rest_consolidation_decisions(
                   decision_id,scene_id,disposition,target_tier,automatic_l3_allowed,real_source_anchor_count,
                   materialized_memory_id,reasons_json,decided_at_utc) VALUES(?,?,?,?,0,?,?,?,?)""",
                (
                    decision.decision_id,
                    decision.scene_id,
                    decision.disposition.value,
                    decision.target_tier,
                    int(decision.real_source_anchor_count),
                    decision.materialized_memory_id,
                    canonical_json(decision.reasons),
                    decision.decided_at_utc,
                ),
            )

    def episode_bundle(self, episode_id: str) -> dict[str, Any] | None:
        episode = self.con.execute("SELECT * FROM rest_episodes WHERE episode_id=?", (episode_id,)).fetchone()
        if episode is None:
            return None
        cycles = [dict(row) for row in self.con.execute("SELECT * FROM rest_cycles WHERE episode_id=? ORDER BY ordinal", (episode_id,))]
        cycle_ids = [str(row["cycle_id"]) for row in cycles]
        if not cycle_ids:
            replay: list[dict[str, Any]] = []
            scenes: list[dict[str, Any]] = []
            evaluations: list[dict[str, Any]] = []
            decisions: list[dict[str, Any]] = []
        else:
            placeholders = ",".join("?" for _ in cycle_ids)
            replay = [dict(row) for row in self.con.execute(
                f"SELECT * FROM rest_replay_items WHERE cycle_id IN ({placeholders}) ORDER BY selected_at_utc", cycle_ids
            )]
            scenes = [dict(row) for row in self.con.execute(
                f"SELECT * FROM dream_scenes WHERE cycle_id IN ({placeholders}) ORDER BY created_at_utc", cycle_ids
            )]
            scene_ids = [str(row["scene_id"]) for row in scenes]
            if scene_ids:
                s_ph = ",".join("?" for _ in scene_ids)
                evaluations = [dict(row) for row in self.con.execute(
                    f"SELECT * FROM dream_evaluations WHERE scene_id IN ({s_ph}) ORDER BY created_at_utc", scene_ids
                )]
                decisions = [dict(row) for row in self.con.execute(
                    f"SELECT * FROM rest_consolidation_decisions WHERE scene_id IN ({s_ph}) ORDER BY decided_at_utc", scene_ids
                )]
            else:
                evaluations, decisions = [], []
        return {
            "episode": dict(episode),
            "cycles": cycles,
            "replay_items": replay,
            "scenes": scenes,
            "evaluations": evaluations,
            "decisions": decisions,
        }

    def save_wake_report(
        self,
        *,
        report_id: str,
        episode_id: str,
        generated_at_utc: str,
        report: dict[str, Any],
        validation_status: str,
    ) -> str:
        raw = canonical_json(report)
        digest = sha256_text(raw)
        with self.transaction():
            self.con.execute(
                """INSERT OR REPLACE INTO rest_wake_reports(
                   report_id,episode_id,generated_at_utc,report_json,report_sha256,validation_status)
                   VALUES(?,?,?,?,?,?)""",
                (report_id, episode_id, generated_at_utc, raw, digest, validation_status),
            )
        return digest

    def latest_wake_report_row(self) -> dict[str, Any] | None:
        row = self.con.execute("SELECT * FROM rest_wake_reports ORDER BY generated_at_utc DESC,rowid DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    def validate(self) -> dict[str, Any]:
        integrity = str(self.con.execute("PRAGMA integrity_check").fetchone()[0])
        fk = self.con.execute("PRAGMA foreign_key_check").fetchall()
        factual_scenes = int(self.con.execute("SELECT COUNT(*) FROM dream_scenes WHERE factual_claim_allowed<>0").fetchone()[0])
        auto_l3 = int(self.con.execute("SELECT COUNT(*) FROM rest_consolidation_decisions WHERE automatic_l3_allowed<>0 OR target_tier='long_term'").fetchone()[0])
        return {
            "ok": integrity == "ok" and not fk and factual_scenes == 0 and auto_l3 == 0,
            "integrity_check": integrity,
            "foreign_key_error_count": len(fk),
            "factual_scene_violation_count": factual_scenes,
            "automatic_l3_violation_count": auto_l3,
            "path": str(self.path),
            "schema_version": SCHEMA_VERSION,
        }
