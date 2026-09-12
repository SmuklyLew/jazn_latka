from __future__ import annotations

"""Conservative temporal evidence links. Never overwrite a source timestamp."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import hashlib
import re
import sqlite3


def parse_source_time(value: Any) -> tuple[float | None, str]:
    if value in (None, ""):
        return None, "missing"
    try:
        if isinstance(value, (int, float)) or re.fullmatch(r"\d{10}(?:\.\d+)?", str(value)):
            stamp = float(value)
            datetime.fromtimestamp(stamp, timezone.utc)
            return stamp, "epoch_utc"
        text = str(value).strip()
        if re.match(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}", text):
            return None, "ambiguous_date_order"
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None, "timezone_missing"
        return parsed.timestamp(), "explicit_timezone"
    except (ValueError, OverflowError, OSError):
        return None, "invalid"


def link_entry(con: sqlite3.Connection, entry: dict[str, Any], *, window_seconds: int = 300,
               limit: int = 20) -> dict[str, Any]:
    raw_time = next((entry[k] for k in ('timestamp', 'date', 'data', 'datetime') if entry.get(k)), None)
    stamp, time_status = parse_source_time(raw_time)
    mid = entry.get('message_id') or entry.get('source_message_id')
    cid = entry.get('conversation_id')
    text = str(entry.get('content') or entry.get('treść') or entry.get('tresc') or entry.get('tekst') or entry.get('analiza') or '')
    active = "m.sha IN (SELECT sha FROM files WHERE details NOT LIKE '%\"error\"%')"
    params: list[Any] = []
    where = [active, "m.role IN ('user','assistant')"]
    if mid:
        where.append('m.mid=?')
        params.append(str(mid))
    elif text.strip():
        words = re.findall(r'\w+', text, re.UNICODE)[:12]
        if not words:
            return {'status': 'unlinked', 'timestamp_status': time_status, 'candidates': []}
        where.append("m.rowid IN (SELECT rowid FROM audit_fts WHERE audit_fts MATCH ?)")
        params.append(' AND '.join('"' + word + '"' for word in words))
    else:
        return {'status': 'unlinked', 'timestamp_status': time_status, 'candidates': []}
    if cid:
        where.append('m.cid=?')
        params.append(str(cid))
    rows = con.execute('SELECT DISTINCT m.cid,m.nid,m.mid,m.role,m.time,m.text,m.payload_sha FROM messages m WHERE '
                       + ' AND '.join(where) + ' LIMIT ?', (*params, limit + 1)).fetchall()
    candidates = []
    for row in rows[:limit]:
        delta = abs(stamp - row['time']) if stamp is not None and row['time'] is not None else None
        exact = bool(text.strip()) and text.strip() in row['text']
        temporal = delta is not None and delta <= window_seconds
        candidates.append({'conversation_id': row['cid'], 'node_id': row['nid'], 'message_id': row['mid'],
                           'role': row['role'], 'message_time_utc': row['time'], 'source_payload_sha': row['payload_sha'],
                           'exact_text': exact, 'explicit_id': bool(mid), 'delta_seconds': delta,
                           'status': 'time_correlated' if temporal and (exact or mid) else 'candidate',
                           'excerpt': row['text'][:600]})
    unique = len(rows) == 1
    return {'status': 'time_correlated' if unique and candidates[0]['status'] == 'time_correlated' else 'review_required' if rows else 'unlinked',
            'timestamp_raw': raw_time, 'timestamp_status': time_status,
            'truncated': len(rows) > limit, 'candidates': candidates,
            'truth_boundary': 'Correlation confirms a source relation, not lived emotion or factuality.'}


def correlate_file(catalog: Path, source: Path, *, window_seconds: int = 300) -> dict[str, Any]:
    source_bytes = source.read_bytes()
    value = json.loads(source_bytes.decode('utf-8-sig'))
    if isinstance(value, dict):
        value = next((value[k] for k in ('entries', 'wpisy', 'dziennik', 'analizy')
                      if isinstance(value.get(k), list)), list(value.values()) if all(isinstance(v, dict) for v in value.values()) else [value])
    if not isinstance(value, list):
        raise ValueError('Expected journal/music JSON object or array')
    con = sqlite3.connect(catalog.resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        results = [{'source_index': i, 'source_id': row.get('id'),
                    **link_entry(con, row, window_seconds=window_seconds)}
                   for i, row in enumerate(value) if isinstance(row, dict)]
    finally:
        con.close()
    return {'source': str(source), 'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
            'source_size_bytes': len(source_bytes), 'entries': len(results), 'results': results,
            'time_correlated': sum(r['status'] == 'time_correlated' for r in results)}


def search_catalog(catalog: Path, query: str, *, year: int | None = None, limit: int = 20) -> dict[str, Any]:
    """Read source messages directly with temporal and source identity evidence."""
    words = re.findall(r'\w+', query, re.UNICODE)
    if not words or not 1 <= limit <= 500:
        raise ValueError('Podaj zapytanie i limit 1..500')
    con = sqlite3.connect(catalog.resolve().as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    try:
        sql = """SELECT DISTINCT m.cid,m.mid,m.nid,m.role,m.time,m.text,m.payload_sha
                 FROM messages m WHERE m.rowid IN (SELECT rowid FROM audit_fts WHERE audit_fts MATCH ?)
                 AND m.role IN ('user','assistant') AND m.sha IN (SELECT sha FROM files)"""
        params: list[Any] = [' AND '.join('"'+w+'"' for w in words)]
        if year is not None:
            sql += " AND strftime('%Y',m.time,'unixepoch')=?"
            params.append(str(year))
        sql += ' ORDER BY m.time LIMIT ?'
        results = [dict(r) for r in con.execute(sql, (*params, limit))]
        for row in results:
            row['sources'] = [r[0] for r in con.execute('SELECT DISTINCT f.path FROM files f JOIN messages m ON f.sha=m.sha WHERE m.cid=? AND m.nid=? AND m.payload_sha=?', (row['cid'], row['nid'], row['payload_sha']))]
        return {'ok': True, 'results': results, 'limit': limit, 'source_evidence_only': True}
    finally:
        con.close()
