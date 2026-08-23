from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
import json
import os
import re
import sqlite3

from latka_jazn.memory.source_archive_gateway import SourceArchiveGateway
from latka_jazn.db.runtime_sqlite import connect_runtime_readonly
from latka_jazn.tools.memory_rebuild_common import DATABASE_FILENAMES, fts_queries
from latka_jazn.version import schema_version

SCHEMA_VERSION = schema_version("living_memory_gateway")
REGISTRY_FILENAME = "memory_source_registry.json"


@dataclass(slots=True, frozen=True)
class LivingMemoryHit:
    source_layer: str
    source_database: str
    source_locator: str
    record_id: str
    content_excerpt: str
    timestamp: str | None
    truth_status: str
    confidence: float | None
    importance: float | None
    relevance: float
    title: str | None = None
    grounding: str = "read_only_living_memory_gateway"
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LivingMemoryGateway:
    """Read-only recall from one native unified database or legacy compatibility.

    The gateway deliberately exposes no write, promotion or migration methods.  It
    reads only explicitly discoverable roots: the active runtime root, roots listed
    in ``JAZN_MEMORY_SOURCE_ROOTS`` and enabled read-only entries from
    ``workspace_runtime/memory_source_registry.json``.
    """

    SEARCH_ORDER = ("memory_jazn", "experience", "journal", "archive_chats")

    def __init__(self, root: str | Path, *, busy_timeout_ms: int = 10_000) -> None:
        self.root = Path(root).expanduser().resolve()
        self.busy_timeout_ms = max(1_000, int(busy_timeout_ms))

    def discover(self) -> list[dict[str, Any]]:
        candidates: list[tuple[Path, str]] = [(self.root, "active_runtime_root")]
        env_value = os.environ.get("JAZN_MEMORY_SOURCE_ROOTS", "")
        for raw in env_value.split(os.pathsep):
            if raw.strip():
                candidates.append((Path(raw).expanduser(), "environment_registry"))

        registry = self.root / "workspace_runtime" / REGISTRY_FILENAME
        if registry.is_file():
            try:
                payload = json.loads(registry.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                payload = {}
            entries = payload.get("sources") if isinstance(payload, dict) else []
            if isinstance(entries, list):
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("enabled", True) is not True or entry.get("read_only", True) is not True:
                        continue
                    raw_path = str(entry.get("path") or "").strip()
                    if raw_path:
                        candidates.append((Path(raw_path).expanduser(), "workspace_registry"))

        discovered: list[dict[str, Any]] = []
        seen: set[Path] = set()
        for candidate, origin in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            sqlite_dir = self._as_sqlite_dir(resolved)
            if sqlite_dir in seen:
                continue
            seen.add(sqlite_dir)
            databases = {
                key: sqlite_dir / filename
                for key, filename in DATABASE_FILENAMES.items()
            }
            available = {key: path.is_file() for key, path in databases.items()}
            discovered.append({
                "root": str(resolved),
                "sqlite_dir": str(sqlite_dir),
                "origin": origin,
                "available": available,
                "database_paths": {key: str(path) for key, path in databases.items()},
                "recall_ready": any(available.get(key, False) for key in self.SEARCH_ORDER),
                "import_catalog_used_for_recall": False,
                "read_only": True,
            })
        return discovered

    def search(
        self,
        plan: Any,
        *,
        limit: int = 6,
        should_continue: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        mode = str(getattr(plan, "search_mode", None) or "semantic_query")
        terms = [str(value).strip() for value in (getattr(plan, "search_terms", None) or []) if str(value).strip()]
        query = " ".join(terms).strip()
        source_reports = self.discover()
        hits: list[LivingMemoryHit] = []
        issues: list[str] = []
        per_layer = max(1, min(4, int(limit)))

        def can_continue() -> bool:
            if should_continue is None:
                return True
            try:
                return bool(should_continue())
            except Exception:
                return False

        cancelled = False
        for source in source_reports:
            if not can_continue():
                cancelled = True
                break
            if not source.get("recall_ready"):
                continue
            paths = {key: Path(value) for key, value in (source.get("database_paths") or {}).items()}
            for layer in self.SEARCH_ORDER:
                if not can_continue():
                    cancelled = True
                    break
                path = paths.get(layer)
                if path is None or not path.is_file():
                    continue
                try:
                    if layer == "memory_jazn":
                        layer_hits = self._search_memory(path, query, mode=mode, limit=per_layer, should_continue=can_continue)
                    elif layer == "experience":
                        layer_hits = self._search_experience(path, query, mode=mode, limit=per_layer, should_continue=can_continue)
                    elif layer == "journal":
                        layer_hits = self._search_journal(path, query, mode=mode, limit=per_layer, should_continue=can_continue)
                    else:
                        layer_hits = self._search_archive(path, query, mode=mode, limit=per_layer, should_continue=can_continue)
                except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
                    issues.append(f"{layer}:{path}:{type(exc).__name__}:{exc}")
                    continue
                hits.extend(layer_hits)
            if cancelled:
                break

        if cancelled:
            issues.append("search_cancelled:turn_deadline_or_cancellation")

        hits = self._dedupe(hits)
        if mode == "chronological_earliest":
            hits.sort(key=lambda hit: (self._timestamp_key(hit.timestamp, latest=False), -hit.relevance))
        elif mode == "chronological_latest":
            hits.sort(key=lambda hit: (self._timestamp_key(hit.timestamp, latest=True), hit.relevance), reverse=True)
        else:
            layer_priority = {name: index for index, name in enumerate(self.SEARCH_ORDER)}
            hits.sort(key=lambda hit: (layer_priority.get(hit.source_layer, 99), -hit.relevance, -(hit.importance or 0.0)))

        layer_hit_counts: dict[str, int] = {}
        for hit in hits:
            layer_hit_counts[hit.source_layer] = layer_hit_counts.get(hit.source_layer, 0) + 1
        selected = hits[: max(1, int(limit))]
        native_ready = any(bool(report.get("memory_search_ready")) for report in source_reports)
        legacy_ready = any(bool(report.get("legacy_search_ready")) for report in source_reports)
        if native_ready:
            status = "ready_native_unified"
        elif legacy_ready:
            status = "ready_legacy_compatibility_only"
        else:
            status = "no_registered_living_memory"
        return {
            "schema_version": SCHEMA_VERSION,
            "status": status,
            "memory_search_ready": native_ready,
            "legacy_search_ready": legacy_ready,
            "search_mode": mode,
            "query": query,
            "cancelled": cancelled,
            "hits": [hit.to_dict() for hit in selected],
            "counts": {
                "hits": len(selected),
                "candidate_hits": len(hits),
                "hits_by_layer": layer_hit_counts,
                "sources_discovered": len(source_reports),
                "sources_recall_ready": sum(1 for report in source_reports if report.get("recall_ready")),
            },
            "sources": source_reports,
            "issues": issues,
            "search_order": (
                ["memory_jazn.sqlite3:" + key for key in self.SEARCH_ORDER]
                if native_ready
                else [DATABASE_FILENAMES[key] for key in self.SEARCH_ORDER]
            ),
            "import_catalog_used_for_recall": False,
            "truth_boundary": (
                "Źródła L0/L1/L2/L3 są czytane tylko do odczytu. Trafienie z archiwum, dziennika lub doświadczeń "
                "jest dowodem albo zapisem, a nie automatycznie zatwierdzonym wspomnieniem L3 ani biologicznym przeżyciem."
            ),
        }

    @staticmethod
    def _as_sqlite_dir(path: Path) -> Path:
        if path.name == "sqlite" or any((path / filename).is_file() for filename in DATABASE_FILENAMES.values()):
            return path
        return path / "memory" / "sqlite"

    def _connect(
        self,
        path: Path,
        *,
        should_continue: Callable[[], bool] | None = None,
    ) -> sqlite3.Connection:
        con = connect_runtime_readonly(path, timeout_ms=self.busy_timeout_ms)
        if should_continue is not None:
            def _progress() -> int:
                try:
                    return 0 if should_continue() else 1
                except Exception:
                    return 1
            con.set_progress_handler(_progress, 2_000)
        return con

    @staticmethod
    def _table_names(con: sqlite3.Connection) -> set[str]:
        return {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}

    def _search_memory(
        self, path: Path, query: str, *, mode: str, limit: int,
        should_continue: Callable[[], bool] | None = None,
    ) -> list[LivingMemoryHit]:
        with closing(self._connect(path, should_continue=should_continue)) as con:
            tables = self._table_names(con)
            if "memory_records" not in tables:
                return []
            params: list[Any] = []
            where = "active=1"
            fts_query = ""
            if mode not in {"chronological_earliest", "chronological_latest"}:
                tokens = self._tokens(query)
                if not tokens:
                    return []
                if "memory_records_fts" in tables:
                    fts_query = " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"*' for token in tokens)
                    where += " AND memory_records.rowid IN (SELECT rowid FROM memory_records_fts WHERE memory_records_fts MATCH ?)"
                    params.append(fts_query)
                else:
                    where += " AND (" + " OR ".join("content LIKE ?" for _ in tokens) + ")"
                    params.extend(f"%{token}%" for token in tokens)
            direction = "ASC" if mode == "chronological_earliest" else "DESC"
            order = f"created_at_utc {direction}, importance DESC" if mode.startswith("chronological_") else "importance DESC, confidence DESC, updated_at_utc DESC"
            params.append(limit)
            rows = con.execute(
                f"SELECT memory_id,tier,kind,content,domain,truth_status,confidence,importance,created_at_utc,updated_at_utc "
                f"FROM memory_records WHERE {where} ORDER BY {order} LIMIT ?",
                params,
            ).fetchall()
            evidence_by_memory: dict[str, list[dict[str, str]]] = {}
            if rows and "memory_evidence" in tables:
                placeholders = ",".join("?" for _ in rows)
                evidence_rows = con.execute(
                    "SELECT memory_id,evidence_key,source_type,source_id FROM memory_evidence "
                    f"WHERE memory_id IN ({placeholders}) ORDER BY memory_id,evidence_key",
                    [str(row["memory_id"]) for row in rows],
                ).fetchall()
                for evidence in evidence_rows:
                    evidence_by_memory.setdefault(str(evidence["memory_id"]), []).append({
                        "evidence_id": str(evidence["evidence_key"]),
                        "source_type": str(evidence["source_type"]),
                        "source_id": str(evidence["source_id"]),
                    })
        return [LivingMemoryHit(
            source_layer="memory_jazn",
            source_database=str(path),
            source_locator=f"memory_records:{row['memory_id']}",
            record_id=str(row["memory_id"]),
            content_excerpt=self._excerpt(row["content"]),
            timestamp=str(row["created_at_utc"] or row["updated_at_utc"] or "") or None,
            truth_status=str(row["truth_status"] or "source_recorded"),
            confidence=self._float(row["confidence"]),
            importance=self._float(row["importance"]),
            relevance=self._relevance(query, str(row["content"] or ""), base=0.86),
            title=str(row["kind"] or row["domain"] or "pamięć aktywna"),
            metadata={
                "tier": row["tier"],
                "kind": row["kind"],
                "domain": row["domain"],
                "evidence": evidence_by_memory.get(str(row["memory_id"]), []),
                "search_index": "memory_records_fts" if fts_query else "bounded_table_scan",
            },
        ) for row in rows if str(row["content"] or "").strip()]

    def _search_experience(
        self, path: Path, query: str, *, mode: str, limit: int,
        should_continue: Callable[[], bool] | None = None,
    ) -> list[LivingMemoryHit]:
        with closing(self._connect(path, should_continue=should_continue)) as con:
            if "experiences" not in self._table_names(con):
                return []
            params: list[Any] = []
            where = "status NOT IN ('rejected','superseded')"
            if mode not in {"chronological_earliest", "chronological_latest"}:
                tokens = self._tokens(query)
                if not tokens:
                    return []
                where += " AND (" + " OR ".join("(title LIKE ? OR summary LIKE ?)" for _ in tokens) + ")"
                for token in tokens:
                    params.extend((f"%{token}%", f"%{token}%"))
            direction = "ASC" if mode == "chronological_earliest" else "DESC"
            order = f"created_at_utc {direction}, importance DESC" if mode.startswith("chronological_") else "importance DESC, confidence DESC, updated_at_utc DESC"
            params.append(limit)
            rows = con.execute(
                f"SELECT experience_id,title,summary,truth_status,confidence,importance,status,created_at_utc,updated_at_utc "
                f"FROM experiences WHERE {where} ORDER BY {order} LIMIT ?",
                params,
            ).fetchall()
            sources_by_experience: dict[str, list[dict[str, str | None]]] = {}
            if rows and "experience_sources" in self._table_names(con):
                placeholders = ",".join("?" for _ in rows)
                source_rows = con.execute(
                    "SELECT experience_id,source_database,source_type,source_record_id,source_sha256 "
                    f"FROM experience_sources WHERE experience_id IN ({placeholders}) "
                    "ORDER BY experience_id,source_database,source_type,source_record_id",
                    [str(row["experience_id"]) for row in rows],
                ).fetchall()
                for source in source_rows:
                    sources_by_experience.setdefault(str(source["experience_id"]), []).append({
                        "source_database": str(source["source_database"]),
                        "source_type": str(source["source_type"]),
                        "source_record_id": str(source["source_record_id"]),
                        "source_sha256": str(source["source_sha256"]) if source["source_sha256"] else None,
                    })
        return [LivingMemoryHit(
            source_layer="experience",
            source_database=str(path),
            source_locator=f"experiences:{row['experience_id']}",
            record_id=str(row["experience_id"]),
            content_excerpt=self._excerpt(row["summary"] or row["title"]),
            timestamp=str(row["created_at_utc"] or row["updated_at_utc"] or "") or None,
            truth_status=str(row["truth_status"] or "source_recorded"),
            confidence=self._float(row["confidence"]),
            importance=self._float(row["importance"]),
            relevance=self._relevance(query, f"{row['title'] or ''} {row['summary'] or ''}", base=0.78),
            title=str(row["title"] or "doświadczenie"),
            metadata={
                "status": row["status"],
                "evidence_sources": sources_by_experience.get(str(row["experience_id"]), []),
            },
        ) for row in rows if str(row["summary"] or row["title"] or "").strip()]

    def _search_journal(
        self, path: Path, query: str, *, mode: str, limit: int,
        should_continue: Callable[[], bool] | None = None,
    ) -> list[LivingMemoryHit]:
        with closing(self._connect(path, should_continue=should_continue)) as con:
            tables = self._table_names(con)
            if "journal_entries" not in tables:
                return []
            rows: Iterable[sqlite3.Row]
            if mode in {"chronological_earliest", "chronological_latest"}:
                direction = "ASC" if mode == "chronological_earliest" else "DESC"
                rows = con.execute(
                    f"SELECT entry_id,title,summary,content,truth_status,importance,event_time_start,created_at_utc,status "
                    f"FROM journal_entries WHERE status NOT IN ('rejected','superseded') "
                    f"ORDER BY COALESCE(event_time_start,created_at_utc) {direction}, importance DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            elif {"journal_fts", "journal_fts_docs"}.issubset(tables) and query.strip():
                rows = []
                for fts_query in self._fts_candidates(query):
                    try:
                        rows = con.execute(
                            """SELECT e.entry_id,e.title,e.summary,e.content,e.truth_status,e.importance,
                                      e.event_time_start,e.created_at_utc,e.status,bm25(journal_fts) AS rank
                                 FROM journal_fts JOIN journal_fts_docs d ON d.rowid=journal_fts.rowid
                                 JOIN journal_entries e ON e.entry_id=d.entry_id
                                WHERE journal_fts MATCH ? AND e.status NOT IN ('rejected','superseded')
                                ORDER BY rank,e.importance DESC LIMIT ?""",
                            (fts_query, limit),
                        ).fetchall()
                    except sqlite3.OperationalError:
                        rows = []
                    if rows:
                        break
            else:
                tokens = self._tokens(query)
                if not tokens:
                    return []
                clauses = " OR ".join("(title LIKE ? OR summary LIKE ? OR content LIKE ?)" for _ in tokens)
                params: list[Any] = []
                for token in tokens:
                    params.extend((f"%{token}%", f"%{token}%", f"%{token}%"))
                params.append(limit)
                rows = con.execute(
                    f"SELECT entry_id,title,summary,content,truth_status,importance,event_time_start,created_at_utc,status "
                    f"FROM journal_entries WHERE status NOT IN ('rejected','superseded') AND ({clauses}) "
                    "ORDER BY importance DESC,COALESCE(event_time_start,created_at_utc) DESC LIMIT ?",
                    params,
                ).fetchall()
            sources_by_entry: dict[str, list[dict[str, str]]] = {}
            if rows and "journal_entry_sources" in tables:
                materialized_rows = list(rows)
                rows = materialized_rows
                placeholders = ",".join("?" for _ in materialized_rows)
                source_rows = con.execute(
                    "SELECT entry_id,source_id,source_record_id,content_sha256 "
                    f"FROM journal_entry_sources WHERE entry_id IN ({placeholders}) "
                    "ORDER BY entry_id,source_id,source_record_id",
                    [str(row["entry_id"]) for row in materialized_rows],
                ).fetchall()
                for source in source_rows:
                    sources_by_entry.setdefault(str(source["entry_id"]), []).append({
                        "source_id": str(source["source_id"]),
                        "source_record_id": str(source["source_record_id"]),
                        "content_sha256": str(source["content_sha256"]),
                    })
        return [LivingMemoryHit(
            source_layer="journal",
            source_database=str(path),
            source_locator=f"journal_entries:{row['entry_id']}",
            record_id=str(row["entry_id"]),
            content_excerpt=self._excerpt(row["summary"] or row["content"] or row["title"]),
            timestamp=str(row["event_time_start"] or row["created_at_utc"] or "") or None,
            truth_status=str(row["truth_status"] or "source_recorded"),
            confidence=None,
            importance=self._float(row["importance"]),
            relevance=self._relevance(query, f"{row['title'] or ''} {row['summary'] or ''} {row['content'] or ''}", base=0.72),
            title=str(row["title"] or "wpis dziennika"),
            metadata={
                "status": row["status"],
                "evidence_sources": sources_by_entry.get(str(row["entry_id"]), []),
            },
        ) for row in rows if str(row["summary"] or row["content"] or row["title"] or "").strip()]

    def _search_archive(
        self, path: Path, query: str, *, mode: str, limit: int,
        should_continue: Callable[[], bool] | None = None,
    ) -> list[LivingMemoryHit]:
        hits: list[LivingMemoryHit] = []
        with SourceArchiveGateway(path, busy_timeout_ms=self.busy_timeout_ms, should_continue=should_continue) as gateway:
            if mode in {"chronological_earliest", "chronological_latest"}:
                direction = "ASC" if mode == "chronological_earliest" else "DESC"
                candidates = gateway.con.execute(
                    f"""SELECT n.conversation_id,n.node_id,n.role,n.create_time,c.title
                           FROM nodes n JOIN conversations c ON c.conversation_id=n.conversation_id
                          WHERE n.create_time IS NOT NULL AND n.role IN ('user','assistant')
                          ORDER BY n.create_time {direction},n.structural_ordinal {direction} LIMIT ?""",
                    (max(limit * 4, 12),),
                ).fetchall()
                search_rows = [(row, None) for row in candidates]
            else:
                search_rows = []
                for fts_query in self._fts_candidates(query):
                    try:
                        archive_hits = gateway.search(fts_query, limit=max(limit * 2, 8))
                    except sqlite3.OperationalError:
                        archive_hits = []
                    if archive_hits:
                        search_rows = [(hit, hit.rank) for hit in archive_hits]
                        break
            for candidate, rank in search_rows:
                if should_continue is not None and not should_continue():
                    break
                conversation_id = str(candidate["conversation_id"] if isinstance(candidate, sqlite3.Row) else candidate.conversation_id)
                node_id = str(candidate["node_id"] if isinstance(candidate, sqlite3.Row) else candidate.node_id)
                try:
                    context = gateway.context_for_node(conversation_id, node_id, ancestor_limit=6)
                except (KeyError, ValueError, sqlite3.Error):
                    continue
                target = next((node for node in reversed(context.nodes) if node.node_id == node_id and node.text.strip()), None)
                if target is None:
                    continue
                relevance = self._relevance(query, target.text, base=0.62)
                if isinstance(rank, (int, float)):
                    relevance = min(0.94, relevance + max(0.0, 0.18 / (1.0 + abs(float(rank)))))
                hits.append(LivingMemoryHit(
                    source_layer="archive_chats",
                    source_database=str(path),
                    source_locator=f"conversations:{conversation_id}/nodes:{node_id}",
                    record_id=node_id,
                    content_excerpt=self._excerpt(target.text),
                    timestamp=(datetime.fromtimestamp(float(target.create_time), tz=timezone.utc).isoformat() if target.create_time is not None else None),
                    truth_status="source_recorded",
                    confidence=0.82,
                    importance=None,
                    relevance=relevance,
                    title=context.title or "rozmowa bez tytułu",
                    metadata={
                        "conversation_id": conversation_id,
                        "role": target.role,
                        "timestamp_status": target.timestamp_status,
                        "source_import_id": context.source_import_id,
                        "source_sha256": context.source_sha256,
                        "source_name": context.source_name,
                        "semantic_tree_sha256": context.semantic_tree_sha256,
                        "rank": rank,
                    },
                ))
                if len(hits) >= limit:
                    break
        return hits

    @classmethod
    def _fts_candidates(cls, query: str) -> tuple[str, ...]:
        tokens = cls._tokens(query)
        candidates: list[str] = []
        if tokens:
            escaped = [token.replace('"', '""') for token in tokens]
            candidates.append(" OR ".join(f'"{token}"' for token in escaped))
            candidates.append(" OR ".join(f'"{token}"*' for token in escaped))
        for value in fts_queries(query):
            if value and value not in candidates:
                candidates.append(value)
        return tuple(candidates)

    @staticmethod
    def _tokens(query: str) -> list[str]:
        tokens = re.findall(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ-]{3,}", query or "", flags=re.UNICODE)
        out: list[str] = []
        for token in tokens:
            if token.casefold() not in {value.casefold() for value in out}:
                out.append(token)
        return out[:12]

    @classmethod
    def _relevance(cls, query: str, content: str, *, base: float) -> float:
        tokens = cls._tokens(query)
        if not tokens:
            return min(0.98, base + 0.12)
        folded = (content or "").casefold()
        matched = sum(1 for token in tokens if token.casefold() in folded)
        return max(0.0, min(0.98, base + min(0.28, matched * 0.07)))

    @staticmethod
    def _float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _excerpt(value: Any, *, limit: int = 900) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text[:limit]

    @staticmethod
    def _timestamp_key(value: str | None, *, latest: bool) -> tuple[int, str]:
        text = str(value or "").strip()
        if not text:
            return (1 if not latest else -1, "")
        return (0, text)

    @staticmethod
    def _dedupe(hits: list[LivingMemoryHit]) -> list[LivingMemoryHit]:
        out: list[LivingMemoryHit] = []
        seen: set[tuple[str, str]] = set()
        for hit in hits:
            key = (hit.source_database, f"{hit.source_layer}:{hit.record_id}")
            if key in seen:
                continue
            seen.add(key)
            out.append(hit)
        return out
