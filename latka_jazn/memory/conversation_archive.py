from __future__ import annotations

from dataclasses import asdict, dataclass
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, cast
import math
import re
import sqlite3

from latka_jazn.core.memory_intent_contract import TemporalPrecision, TemporalScope
from latka_jazn.memory.memory_root import resolve_memory_root
from latka_jazn.memory.storage_limits import DEFAULT_MAX_SQLITE_FILE_BYTES


SCHEMA_VERSION = "conversation_archive_runtime/v1"
DEFAULT_HARD_LIMIT_BYTES = DEFAULT_MAX_SQLITE_FILE_BYTES
TRUTH_BOUNDARY = (
    "conversation_archive is source-backed local storage built from raw HTML; "
    "conversation_fts is a rebuildable search index; staging is not canonical memory "
    "and must not be treated as wake_state or identity proof by itself."
)
MOJIBAKE_MARKERS = frozenset("\u0081\u00c2\u00c3\u00c4\u0139\u015f\u017a\u201a\u201e\u2020\u2021\u2122")


def _mib(value: int) -> float:
    return round(value / 1024 / 1024, 2)


def _connect_ro(path: Path, *, immutable: bool = False) -> sqlite3.Connection:
    options = "mode=ro&immutable=1" if immutable else "mode=ro"
    uri = f"file:{path.resolve().as_posix()}?{options}"
    con = sqlite3.connect(uri, uri=True, timeout=10.0)
    con.row_factory = sqlite3.Row
    return con


def _tables(con: sqlite3.Connection) -> set[str]:
    return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}


def _count(con: sqlite3.Connection, table: str) -> int:
    if table not in _tables(con):
        return 0
    return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _mojibake_score(text: str) -> int:
    return sum(1 for char in text if char in MOJIBAKE_MARKERS)


def _repair_common_cp1250_mojibake(text: str) -> str:
    if not text or _mojibake_score(text) == 0:
        return text

    raw = bytearray()
    for char in text:
        codepoint = ord(char)
        if codepoint < 256:
            raw.append(codepoint)
            continue
        try:
            raw.extend(char.encode("cp1250"))
        except UnicodeEncodeError:
            return text

    try:
        candidate = raw.decode("utf-8")
    except UnicodeDecodeError:
        return text

    if _mojibake_score(candidate) < _mojibake_score(text):
        return candidate
    return text


@dataclass(slots=True)
class SQLiteFileHealth:
    path: str
    family: str
    shard_id: str
    exists: bool
    size_bytes: int
    size_mib: float
    integrity_check: str | None
    foreign_key_error_count: int | None
    hard_limit_bytes: int
    over_limit: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ConversationArchiveStatus:
    schema_version: str
    status: str
    root: str
    archive_dir: str
    fts_dir: str
    staging_dir: str
    manifest_path: str
    manifest_present: bool
    counts: dict[str, int]
    files: list[dict[str, Any]]
    hard_limit_bytes: int
    ready_for_search: bool
    issues: list[str]
    truth_boundary: str = TRUTH_BOUNDARY

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ConversationArchiveHit:
    fts_doc_uid: str
    rank: float
    message_uid: str
    occurrence_uid: str
    staging_uid: str
    conversation_uid: str
    source_uid: str
    source_name: str | None
    source_locator: str | None
    role: str
    title: str | None
    create_time: str | None
    content_hash: str
    memory_namespace: str | None
    privacy_scope: str | None
    identity_confidence: float | None
    review_status: str | None
    excerpt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ConversationArchiveSearchResult:
    schema_version: str
    status: str
    query: str
    fts_query: str | None
    hits: list[dict[str, Any]]
    searched_shards: int
    issues: list[str]
    truth_boundary: str = TRUTH_BOUNDARY
    input_query: str | None = None
    temporal_scope: dict[str, Any] | None = None
    sampling_strategy: str = "fts_rank"
    candidate_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConversationArchiveStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.memory_root = resolve_memory_root(self.root)
        base = self.memory_root / "sqlite"
        self.archive_dir = base / "conversation_archive_v1"
        self.fts_dir = base / "conversation_fts_v1"
        self.staging_dir = base / "staging_v1"
        self.manifest_path = self.archive_dir / "conversation_archive_manifest.sqlite3"

    def status(self, *, check_integrity: bool | None = None, health_mode: str | None = None) -> ConversationArchiveStatus:
        if health_mode is None:
            health_mode = "deep" if check_integrity is True else "metadata"
        health_mode = (health_mode or "metadata").strip().lower()
        if health_mode not in {"metadata", "quick", "deep"}:
            raise ValueError(f"Unsupported conversation archive health_mode: {health_mode}")
        issues: list[str] = []
        files: list[dict[str, Any]] = []
        counts = {
            "sources": 0,
            "conversation_locations": 0,
            "conversation_occurrences": 0,
            "message_locations": 0,
            "message_occurrences": 0,
            "content_locations": 0,
            "staging_locations": 0,
            "fts_locations": 0,
        }
        hard_limit_bytes = DEFAULT_HARD_LIMIT_BYTES

        if not self.manifest_path.exists():
            issues.append("conversation_archive_manifest_missing")
            return ConversationArchiveStatus(
                schema_version=SCHEMA_VERSION,
                status="missing",
                root=str(self.root),
                archive_dir=str(self.archive_dir),
                fts_dir=str(self.fts_dir),
                staging_dir=str(self.staging_dir),
                manifest_path=str(self.manifest_path),
                manifest_present=False,
                counts=counts,
                files=[],
                hard_limit_bytes=hard_limit_bytes,
                ready_for_search=False,
                issues=issues,
            )

        manifest_health = self._health(
            self.manifest_path,
            family="manifest",
            shard_id="manifest",
            hard_limit_bytes=hard_limit_bytes,
            health_mode=health_mode,
        )
        files.append(manifest_health.to_dict())
        if manifest_health.integrity_check not in (None, "ok"):
            issues.append("manifest_integrity_not_ok")
        if manifest_health.foreign_key_error_count:
            issues.append("manifest_foreign_key_errors")

        try:
            with closing(_connect_ro(self.manifest_path, immutable=True)) as con:
                meta = {row["key"]: row["value"] for row in con.execute("SELECT key,value FROM manifest_meta")}
                hard_limit_bytes = int(meta.get("hard_limit_bytes") or hard_limit_bytes)
                counts = {
                    "sources": _count(con, "archive_sources"),
                    "conversation_locations": _count(con, "conversation_locations"),
                    "conversation_occurrences": _count(con, "conversation_occurrence_locations"),
                    "message_locations": _count(con, "message_locations"),
                    "message_occurrences": _count(con, "occurrence_locations"),
                    "content_locations": _count(con, "content_locations"),
                    "staging_locations": _count(con, "staging_locations"),
                    "fts_locations": _count(con, "fts_locations"),
                }
                for row in con.execute("SELECT * FROM shard_files ORDER BY family, ordinal"):
                    path = self._shard_path(row["family"], row["relative_path"])
                    health = self._health(
                        path,
                        family=row["family"],
                        shard_id=row["shard_id"],
                        hard_limit_bytes=int(row["hard_limit_bytes"] or hard_limit_bytes),
                        health_mode=health_mode,
                    )
                    files.append(health.to_dict())
                    if not health.exists:
                        issues.append(f"missing_shard:{row['shard_id']}")
                    if health.integrity_check not in (None, "ok"):
                        issues.append(f"integrity_not_ok:{row['shard_id']}")
                    if health.foreign_key_error_count:
                        issues.append(f"foreign_key_errors:{row['shard_id']}")
                    if health.over_limit:
                        issues.append(f"over_limit:{row['shard_id']}")
        except Exception as exc:
            issues.append(f"manifest_read_error:{type(exc).__name__}:{exc}")

        if counts["message_occurrences"] <= 0:
            issues.append("no_message_occurrences")
        if counts["fts_locations"] <= 0:
            issues.append("no_fts_locations")
        if counts["staging_locations"] <= 0:
            issues.append("no_staging_locations")

        ready = not issues and counts["fts_locations"] > 0 and counts["message_occurrences"] > 0
        if ready:
            status = "ready"
        elif self.manifest_path.exists():
            status = "partial_or_invalid"
        else:
            status = "missing"
        return ConversationArchiveStatus(
            schema_version=SCHEMA_VERSION,
            status=status,
            root=str(self.root),
            archive_dir=str(self.archive_dir),
            fts_dir=str(self.fts_dir),
            staging_dir=str(self.staging_dir),
            manifest_path=str(self.manifest_path),
            manifest_present=True,
            counts=counts,
            files=files,
            hard_limit_bytes=hard_limit_bytes,
            ready_for_search=ready,
            issues=issues,
        )

    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        include_snippets: bool = False,
        should_continue: Callable[[], bool] | None = None,
        temporal_scope: TemporalScope | dict[str, Any] | None = None,
    ) -> ConversationArchiveSearchResult:
        def can_continue() -> bool:
            if should_continue is None:
                return True
            try:
                return bool(should_continue())
            except Exception:
                return False

        input_query = (query or "").strip()
        query = _repair_common_cp1250_mojibake(input_query)
        terms = self._query_terms(query)
        fts_query = self._fts_query(terms)
        issues: list[str] = []
        scope, scope_issue = self._validated_temporal_scope(temporal_scope)
        if temporal_scope is not None and scope is None:
            return ConversationArchiveSearchResult(
                SCHEMA_VERSION,
                "invalid_temporal_scope",
                query,
                fts_query,
                [],
                0,
                [scope_issue or "invalid_temporal_scope"],
            )
        if not query and scope is None:
            return ConversationArchiveSearchResult(SCHEMA_VERSION, "empty_query", query, None, [], 0, ["empty_query"])
        if not fts_query and scope is None:
            return ConversationArchiveSearchResult(SCHEMA_VERSION, "no_search_terms", query, None, [], 0, ["no_search_terms"])
        if not can_continue():
            return ConversationArchiveSearchResult(
                schema_version=SCHEMA_VERSION,
                status="cancelled",
                query=query,
                fts_query=fts_query,
                hits=[],
                searched_shards=0,
                issues=["search_cancelled:turn_deadline_or_cancellation"],
                temporal_scope=scope.to_dict() if scope is not None else None,
                sampling_strategy="temporal_buckets_even_spread" if scope is not None and not fts_query else "fts_rank",
            )

        status = self.status(health_mode="metadata")
        if not status.ready_for_search:
            return ConversationArchiveSearchResult(
                schema_version=SCHEMA_VERSION,
                status="archive_not_ready",
                query=query,
                fts_query=fts_query,
                hits=[],
                searched_shards=0,
                issues=status.issues,
                temporal_scope=scope.to_dict() if scope is not None else None,
                sampling_strategy="temporal_buckets_even_spread" if scope is not None and not fts_query else "fts_rank",
            )

        shard_rows = self._manifest_rows("SELECT * FROM shard_files WHERE family='fts' ORDER BY ordinal")
        raw_hits: list[tuple[float, dict[str, Any]]] = []
        candidate_count = 0
        searched = 0
        cancelled = False
        for shard in shard_rows:
            if not can_continue():
                cancelled = True
                break
            path = self._shard_path(shard["family"], shard["relative_path"])
            if not path.exists():
                issues.append(f"missing_fts_shard:{shard['shard_id']}")
                continue
            try:
                with closing(_connect_ro(path)) as con:
                    if should_continue is not None:
                        def _progress() -> int:
                            return 0 if can_continue() else 1
                        con.set_progress_handler(_progress, 2_000)
                    searched += 1
                    if fts_query:
                        where_time = ""
                        params: list[Any] = [fts_query]
                        if scope is not None:
                            where_time = f" AND {self._timestamp_epoch_sql('d.create_time')} >= ? AND {self._timestamp_epoch_sql('d.create_time')} < ?"
                            params.extend((scope.start_epoch, scope.end_epoch_exclusive))
                        params.append(max(1, min(128, limit * 3)))
                        sql = f"""
                            SELECT d.*, bm25(message_fts) AS rank
                              FROM message_fts
                              JOIN fts_docs d ON d.rowid = message_fts.rowid
                             WHERE message_fts MATCH ?{where_time}
                             ORDER BY rank
                             LIMIT ?
                        """
                        for row in con.execute(sql, tuple(params)):
                            rank = float(row["rank"] if row["rank"] is not None else 0.0)
                            raw_hits.append((rank, dict(row)))
                            candidate_count += 1
                    elif scope is not None:
                        epoch_sql = self._timestamp_epoch_sql("d.create_time")
                        count_row = con.execute(
                            f"SELECT COUNT(*) FROM fts_docs d WHERE {epoch_sql} >= ? AND {epoch_sql} < ?",
                            (scope.start_epoch, scope.end_epoch_exclusive),
                        ).fetchone()
                        shard_count = int(count_row[0] if count_row is not None else 0)
                        candidate_count += shard_count
                        bucket_count = min(max(1, limit * 2), 24)
                        width = (scope.end_epoch_exclusive - scope.start_epoch) / bucket_count
                        for bucket in range(bucket_count):
                            bucket_start = scope.start_epoch + (bucket * width)
                            bucket_end = scope.end_epoch_exclusive if bucket == bucket_count - 1 else bucket_start + width
                            row = con.execute(
                                f"""
                                SELECT d.*, {epoch_sql} AS temporal_epoch, 0.0 AS rank
                                  FROM fts_docs d
                                 WHERE {epoch_sql} >= ? AND {epoch_sql} < ?
                                 ORDER BY {epoch_sql}, d.conversation_uid, d.fts_doc_uid
                                 LIMIT 1
                                """,
                                (bucket_start, bucket_end),
                            ).fetchone()
                            if row is not None:
                                raw_hits.append((float(bucket), dict(row)))
            except sqlite3.OperationalError as exc:
                if not can_continue() or "interrupt" in str(exc).casefold():
                    cancelled = True
                    break
                issues.append(f"fts_query_error:{shard['shard_id']}:{exc}")
            except sqlite3.DatabaseError as exc:
                issues.append(f"fts_database_error:{shard['shard_id']}:{exc}")

        if cancelled:
            issues.append("search_cancelled:turn_deadline_or_cancellation")

        deduplicated: list[tuple[float, dict[str, Any]]] = []
        seen_docs: set[str] = set()
        for ranked in raw_hits:
            uid = str(ranked[1].get("fts_doc_uid") or "")
            if uid and uid in seen_docs:
                continue
            if uid:
                seen_docs.add(uid)
            deduplicated.append(ranked)
        if fts_query:
            deduplicated.sort(key=lambda item: item[0])
            selected = deduplicated[: max(1, limit)]
        else:
            deduplicated.sort(
                key=lambda item: (
                    float(item[1].get("temporal_epoch") or 0.0),
                    str(item[1].get("conversation_uid") or ""),
                    str(item[1].get("fts_doc_uid") or ""),
                )
            )
            selected = self._evenly_spaced(deduplicated, max(1, limit))
        hits: list[dict[str, Any]] = []
        for rank, row in selected:
            hit = self._hydrate_hit(row, rank=rank, terms=terms, include_snippets=include_snippets)
            if hit is not None:
                hits.append(hit.to_dict())

        return ConversationArchiveSearchResult(
            schema_version=SCHEMA_VERSION,
            status="cancelled" if cancelled else ("ok" if hits else "no_hits"),
            query=query,
            fts_query=fts_query,
            hits=hits,
            searched_shards=searched,
            issues=issues,
            input_query=input_query if input_query != query else None,
            temporal_scope=scope.to_dict() if scope is not None else None,
            sampling_strategy="fts_rank_with_temporal_filter" if fts_query and scope is not None else (
                "temporal_buckets_even_spread" if scope is not None else "fts_rank"
            ),
            candidate_count=candidate_count,
        )

    @staticmethod
    def _timestamp_epoch_sql(column: str) -> str:
        text = f"trim(CAST({column} AS TEXT))"
        return (
            f"(CASE WHEN typeof({column}) IN ('integer','real') THEN CAST({column} AS REAL) "
            f"WHEN {text} GLOB '[0-9]*' AND {text} NOT GLOB '*[^0-9.]*' "
            f"THEN CAST({column} AS REAL) ELSE CAST(strftime('%s', {column}) AS REAL) END)"
        )

    @staticmethod
    def _validated_temporal_scope(
        value: TemporalScope | dict[str, Any] | None,
    ) -> tuple[TemporalScope | None, str | None]:
        if value is None:
            return None, None
        try:
            if isinstance(value, TemporalScope):
                scope = value
            elif isinstance(value, dict):
                precision_value = str(value.get("precision") or "year")
                if precision_value not in {"year", "month", "month_range"}:
                    return None, "invalid_temporal_scope_precision"
                raw_start_epoch = value.get("start_epoch")
                raw_end_epoch = value.get("end_epoch_exclusive", value.get("end_epoch"))
                if (
                    isinstance(raw_start_epoch, bool)
                    or not isinstance(raw_start_epoch, (str, int, float))
                    or isinstance(raw_end_epoch, bool)
                    or not isinstance(raw_end_epoch, (str, int, float))
                ):
                    return None, "invalid_temporal_scope_shape"
                scope = TemporalScope(
                    start_utc=str(value.get("start_utc") or ""),
                    end_utc_exclusive=str(value.get("end_utc_exclusive") or value.get("end_utc") or ""),
                    start_epoch=float(raw_start_epoch),
                    end_epoch_exclusive=float(raw_end_epoch),
                    precision=cast(TemporalPrecision, precision_value),
                    source_expression=str(value.get("source_expression") or value.get("source") or ""),
                    timezone_name=str(value.get("timezone_name") or value.get("timezone") or "Europe/Warsaw"),
                )
            else:
                return None, "invalid_temporal_scope_type"
        except (KeyError, TypeError, ValueError):
            return None, "invalid_temporal_scope_shape"
        if not math.isfinite(scope.start_epoch) or not math.isfinite(scope.end_epoch_exclusive):
            return None, "invalid_temporal_scope_non_finite"
        if scope.start_epoch >= scope.end_epoch_exclusive:
            return None, "invalid_temporal_scope_bounds"
        return scope, None

    @staticmethod
    def _evenly_spaced(
        values: list[tuple[float, dict[str, Any]]],
        limit: int,
    ) -> list[tuple[float, dict[str, Any]]]:
        if len(values) <= limit:
            return values
        if limit <= 1:
            return [values[len(values) // 2]]
        indexes = {
            round(index * (len(values) - 1) / (limit - 1))
            for index in range(limit)
        }
        return [values[index] for index in sorted(indexes)]

    def _health(
        self,
        path: Path,
        *,
        family: str,
        shard_id: str,
        hard_limit_bytes: int,
        health_mode: str = "metadata",
    ) -> SQLiteFileHealth:
        if not path.exists():
            return SQLiteFileHealth(str(path), family, shard_id, False, 0, 0.0, None, None, hard_limit_bytes, False)
        size = path.stat().st_size
        integrity: str | None = None
        fk_count: int | None = None
        error: str | None = None
        if health_mode in {"quick", "deep"}:
            try:
                with closing(_connect_ro(path, immutable=True)) as con:
                    con.execute("PRAGMA busy_timeout=1000")
                    if health_mode == "quick":
                        integrity = str(con.execute("PRAGMA quick_check").fetchone()[0])
                    else:
                        integrity = str(con.execute("PRAGMA integrity_check").fetchone()[0])
                        fk_count = len(con.execute("PRAGMA foreign_key_check").fetchall())
            except Exception as exc:
                error = f"{type(exc).__name__}:{exc}"
        return SQLiteFileHealth(
            path=str(path),
            family=family,
            shard_id=shard_id,
            exists=True,
            size_bytes=size,
            size_mib=_mib(size),
            integrity_check=integrity,
            foreign_key_error_count=fk_count,
            hard_limit_bytes=hard_limit_bytes,
            over_limit=size > hard_limit_bytes,
            error=error,
        )

    def _shard_path(self, family: str, relative_path: str) -> Path:
        if family == "fts":
            return self.fts_dir / relative_path
        if family == "staging":
            return self.staging_dir / relative_path
        return self.archive_dir / relative_path

    def _manifest_rows(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with closing(_connect_ro(self.manifest_path)) as con:
            return list(con.execute(sql, params))

    def _manifest_row(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        rows = self._manifest_rows(sql, params)
        return rows[0] if rows else None

    def _row_from_shard(self, family: str, shard_id: str, table: str, key_col: str, key_value: str) -> dict[str, Any] | None:
        shard = self._manifest_row("SELECT * FROM shard_files WHERE shard_id=?", (shard_id,))
        if shard is None:
            return None
        path = self._shard_path(family, shard["relative_path"])
        if not path.exists():
            return None
        with closing(_connect_ro(path)) as con:
            row = con.execute(f"SELECT * FROM {table} WHERE {key_col}=?", (key_value,)).fetchone()
            return _row_dict(row)

    def _hydrate_hit(
        self,
        fts_row: dict[str, Any],
        *,
        rank: float,
        terms: list[str],
        include_snippets: bool,
    ) -> ConversationArchiveHit | None:
        message_uid = str(fts_row["archive_message_uid"])
        occurrence_uid = str(fts_row["archive_occurrence_uid"])
        staging_uid = str(fts_row["staging_uid"])
        content_hash = str(fts_row["content_hash"])

        content_loc = self._manifest_row("SELECT * FROM content_locations WHERE content_hash=?", (content_hash,))
        message_loc = self._manifest_row("SELECT * FROM message_locations WHERE message_uid=?", (message_uid,))
        occurrence_loc = self._manifest_row("SELECT * FROM occurrence_locations WHERE occurrence_uid=?", (occurrence_uid,))
        staging_loc = self._manifest_row("SELECT * FROM staging_locations WHERE staging_uid=?", (staging_uid,))
        if content_loc is None or message_loc is None or occurrence_loc is None or staging_loc is None:
            return None

        content = self._row_from_shard("archive", content_loc["shard_id"], "content_blobs", "content_hash", content_hash)
        message = self._row_from_shard("archive", message_loc["shard_id"], "archive_messages", "message_uid", message_uid)
        occurrence = self._row_from_shard(
            "archive",
            occurrence_loc["shard_id"],
            "archive_message_occurrences",
            "occurrence_uid",
            occurrence_uid,
        )
        staging = self._row_from_shard("staging", staging_loc["shard_id"], "staging_memory_entries", "staging_uid", staging_uid)
        source = self._manifest_row("SELECT * FROM archive_sources WHERE source_uid=?", (str(fts_row["source_uid"]),))

        text = str((content or {}).get("text") or "")
        excerpt = self._excerpt(text, terms) if include_snippets else None
        return ConversationArchiveHit(
            fts_doc_uid=str(fts_row["fts_doc_uid"]),
            rank=rank,
            message_uid=message_uid,
            occurrence_uid=occurrence_uid,
            staging_uid=staging_uid,
            conversation_uid=str(fts_row["conversation_uid"]),
            source_uid=str(fts_row["source_uid"]),
            source_name=str(source["source_name"]) if source is not None else None,
            source_locator=(occurrence or {}).get("source_locator"),
            role=str((message or fts_row).get("role") or ""),
            title=(fts_row.get("title") or (occurrence or {}).get("title")),
            create_time=(message or fts_row).get("create_time"),
            content_hash=content_hash,
            memory_namespace=(staging or {}).get("memory_namespace"),
            privacy_scope=(staging or {}).get("privacy_scope"),
            identity_confidence=(staging or {}).get("identity_confidence"),
            review_status=(staging or {}).get("review_status"),
            excerpt=excerpt,
        )

    def _query_terms(self, query: str) -> list[str]:
        raw = re.findall(r"[\wąćęłńóśźżĄĆĘŁŃÓŚŹŻ-]+", query, flags=re.UNICODE)
        terms: list[str] = []
        seen: set[str] = set()
        for item in raw:
            term = item.strip("-_").lower()
            if len(term) < 2 or term in {"czy", "jak", "jest", "oraz", "the", "and"}:
                continue
            if term not in seen:
                seen.add(term)
                terms.append(term)
        return terms[:12]

    def _fts_query(self, terms: list[str]) -> str | None:
        if not terms:
            return None
        quoted = []
        for term in terms:
            safe = term.replace('"', '""')
            quoted.append(f'"{safe}"')
        return " OR ".join(quoted)

    def _excerpt(self, text: str, terms: list[str], *, window: int = 160) -> str:
        if not text:
            return ""
        low = text.lower()
        positions = [low.find(term.lower()) for term in terms if term]
        positions = [pos for pos in positions if pos >= 0]
        pos = min(positions) if positions else 0
        start = max(0, pos - window)
        end = min(len(text), pos + window)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return (prefix + text[start:end].replace("\r", " ").replace("\n", " ") + suffix).strip()


def build_conversation_archive_status(root: Path | str, *, health_mode: str = "metadata") -> ConversationArchiveStatus:
    return ConversationArchiveStore(root).status(health_mode=health_mode)


def search_conversation_archive(
    root: Path | str,
    query: str,
    *,
    limit: int = 8,
    include_snippets: bool = False,
    temporal_scope: TemporalScope | dict[str, Any] | None = None,
) -> ConversationArchiveSearchResult:
    return ConversationArchiveStore(root).search(
        query,
        limit=limit,
        include_snippets=include_snippets,
        temporal_scope=temporal_scope,
    )
