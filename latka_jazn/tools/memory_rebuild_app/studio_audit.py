from __future__ import annotations

"""Content-addressed, read-only source discovery for Jaźń - Studio Pamięci.

The SQLite catalog is an inspection artifact, never runtime memory. Original
files remain authoritative. Titles are labels, not conversation identities.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TextIO, cast
import hashlib
import json
import re
import sqlite3
import zipfile

from latka_jazn.tools.chat_export_reader import (
    ChatExportReader, build_conversation_graph, iter_json_array_objects, sha256_file,
)
from .html_semantics import HtmlSemanticNormalizer
from .source_inventory import inspect_zip

AUDIT_VERSION = "studio-source-audit/1"
CHAT_NAME = re.compile(r"conversations(?:[-_]\d+)?\.json$", re.I)
HTML_MARKER = re.compile(r"(?:var|let|const)\s+jsonData\s*=\s*", re.I)


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def classify(path: Path) -> str:
    name = path.name.casefold()
    if name.endswith(("message_feedback.json", "shared_conversations.json")):
        return "relational_metadata"
    if CHAT_NAME.search(name):
        return "conversation_json"
    if path.suffix.casefold() in {".html", ".htm"}:
        return "html_control"
    if "dziennik" in name or "journal" in name:
        return "journal"
    if "analiz" in name and ("utwor" in name or "utwór" in name):
        return "music_analysis"
    if name.endswith(("message_feedback.json", "shared_conversations.json")):
        return "relational_metadata"
    if name.endswith(("user.json", "user_settings.json")):
        return "account_metadata"
    if name.endswith("manifest.json"):
        return "export_manifest"
    if path.suffix.casefold() == ".zip":
        return "attachment_archive"
    return "attachment"


class _PrefixStream:
    def __init__(self, prefix: str, stream: Any):
        self.prefix, self.stream = prefix, stream

    def read(self, size: int) -> str:
        prefix, self.prefix = self.prefix[:size], self.prefix[size:]
        return prefix + self.stream.read(size - len(prefix))


def html_records(path: Path, *, normalize: bool = True) -> Iterator[dict[str, Any]]:
    """Stream the embedded array; never materialize a gigabyte HTML document."""
    with path.open(encoding="utf-8-sig") as stream:
        tail = ""
        while chunk := stream.read(65536):
            text = tail + chunk
            match = HTML_MARKER.search(text)
            if match:
                normalizer = HtmlSemanticNormalizer()
                for raw in iter_json_array_objects(cast(TextIO, _PrefixStream(text[match.end():], stream))):
                    yield normalizer.normalize(raw) if normalize else raw
                return
            tail = text[-256:]
    raise ValueError("HTML has no lossless jsonData array; manual review required")


@contextmanager
def open_catalog(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript("""
    CREATE TABLE IF NOT EXISTS audit_meta(version TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, sha TEXT NOT NULL,
      size INTEGER NOT NULL, role TEXT NOT NULL, details TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS parsed(sha TEXT PRIMARY KEY, version TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS chats(sha TEXT, cid TEXT, title TEXT, tree_sha TEXT,
      PRIMARY KEY(sha,cid,tree_sha));
    CREATE TABLE IF NOT EXISTS messages(sha TEXT, cid TEXT, nid TEXT, mid TEXT,
      role TEXT, time REAL, parent TEXT, visible INTEGER, text TEXT, payload_sha TEXT,
      PRIMARY KEY(sha,cid,nid,payload_sha));
    CREATE INDEX IF NOT EXISTS message_id ON messages(mid);
    CREATE INDEX IF NOT EXISTS message_time ON messages(time);
    CREATE TABLE IF NOT EXISTS assets(sha TEXT,cid TEXT,nid TEXT,pointer TEXT,filename TEXT,
      PRIMARY KEY(sha,cid,nid,pointer));
    CREATE VIRTUAL TABLE IF NOT EXISTS audit_fts USING fts5(text, content='messages', content_rowid='rowid');
    """)
    versions = [r[0] for r in con.execute("SELECT version FROM audit_meta")]
    if versions and versions != [AUDIT_VERSION]:
        con.close()
        raise ValueError("Catalog schema changed; select a new catalog path")
    con.execute("INSERT OR IGNORE INTO audit_meta VALUES(?)", (AUDIT_VERSION,))
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _parse(con: sqlite3.Connection, path: Path, sha: str, role: str) -> dict[str, Any]:
    canonical = {r[0] for r in con.execute("SELECT tree_sha FROM chats WHERE sha IN (SELECT sha FROM files WHERE role='conversation_json')")} if role == 'html_control' else set()
    parser_version = AUDIT_VERSION + ('/assets-html-evidence/' + canonical_hash(sorted(canonical)) if role == 'html_control' else '/assets')
    if con.execute("SELECT 1 FROM parsed WHERE sha=? AND version=?", (sha, parser_version)).fetchone():
        return {"cached": True}
    for table in ('chats', 'messages', 'assets'):
        con.execute(f'DELETE FROM {table} WHERE sha=?', (sha,))
    con.execute('DELETE FROM parsed WHERE sha=?', (sha,))
    count = 0
    if role == "html_control":
        # Decode entities only when raw HTML payload has no exact canonical graph.
        # Authors may have written literal HTML entities in code or quoted text.
        def html_graphs():
            for raw in html_records(path, normalize=False):
                graph = build_conversation_graph(raw)
                if graph.semantic_tree_sha256 in canonical:
                    yield graph
                else:
                    yield build_conversation_graph(HtmlSemanticNormalizer().normalize(raw))
        graphs = html_graphs()
        reader = None
    else:
        reader = ChatExportReader(path, verify_crc=False)
        graphs = reader.iter_graphs()
    try:
        for graph in graphs:
            con.execute("INSERT OR IGNORE INTO chats VALUES(?,?,?,?)",
                        (sha, graph.conversation_id, graph.title, graph.semantic_tree_sha256))
            for node in graph.nodes:
                if not node.message_id:
                    continue
                con.execute("INSERT OR IGNORE INTO messages VALUES(?,?,?,?,?,?,?,?,?,?)", (
                    sha, graph.conversation_id, node.node_id, node.message_id,
                    node.role, node.create_time, node.parent_node_id,
                    int(node.on_current_path), node.text, node.semantic_payload_sha256 or ""))
                from .adapters.common import _assets, _raw_message
                for asset in _assets(node, _raw_message(graph, node.node_id)):
                    con.execute('INSERT OR IGNORE INTO assets VALUES(?,?,?,?,?)',
                                (sha, graph.conversation_id, node.node_id, asset['asset_pointer'], asset['original_filename']))
            count += 1
    finally:
        if reader:
            reader.close()
    con.execute("INSERT OR REPLACE INTO parsed VALUES(?,?)", (sha, parser_version))
    return {"cached": False, "conversation_occurrences": count}


def scan_sources(root: Path, catalog: Path, *, progress=None, repair_missing_commas: bool = False) -> dict[str, Any]:
    root, catalog = root.resolve(), catalog.resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)
    if catalog.is_relative_to(root):
        raise ValueError("Catalog must be outside source tree")
    paths = sorted(root.rglob("*"), key=lambda p: (0 if classify(p) == 'conversation_json' else 1, str(p)))
    errors: list[dict[str, str]] = []
    with open_catalog(catalog) as con:
        con.execute("DELETE FROM files")
        con.commit()
        for path in paths:
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                errors.append({"path": str(path), "error": "symlink_not_followed"})
                continue
            if not path.is_file():
                continue
            if progress:
                progress(str(path.relative_to(root)))
            before = path.stat()
            sha, role = sha256_file(path), classify(path)
            details: dict[str, Any] = {}
            try:
                if role in {"conversation_json", "html_control"}:
                    with con:
                        details = _parse(con, path, sha, role)
                elif role == "attachment_archive":
                    details = inspect_zip(path, verify_crc=True)
                    embedded = []
                    with zipfile.ZipFile(path) as archive:
                        for member in archive.infolist():
                            kind = classify(Path(member.filename))
                            if Path(member.filename).name.casefold() in {'dziennik.json', 'analizy_utworow.json'}:
                                if member.file_size > 32 * 1024 * 1024:
                                    raise ValueError('Embedded memory JSON exceeds 32 MiB limit')
                                data = archive.read(member)
                                item: dict[str, Any] = {'member': member.filename, 'role': kind,
                                        'sha256': hashlib.sha256(data).hexdigest()}
                                try:
                                    value = json.loads(data.decode('utf-8-sig'))
                                    item['items'] = len(value) if isinstance(value, (dict, list)) else 1
                                    item['valid_json'] = True
                                except (ValueError, UnicodeError) as exc:
                                    item['valid_json'] = False
                                    item['error'] = str(exc)
                                    if repair_missing_commas:
                                        from .studio_repair import repair_missing_object_comma
                                        try:
                                            repaired, recipe = repair_missing_object_comma(data)
                                            item['repair'] = recipe
                                            item['valid_json'] = True
                                            item['items'] = len(json.loads(repaired))
                                        except ValueError:
                                            pass
                                    if not item['valid_json']:
                                        errors.append({'path': str(path) + '::' + member.filename, 'error': str(exc)})
                                embedded.append(item)
                    details['embedded_memory_sources'] = embedded
                elif path.suffix.lower() == ".json":
                    with path.open(encoding="utf-8-sig") as stream:
                        value = json.load(stream)
                    details = {"json_type": type(value).__name__,
                               "items": len(value) if isinstance(value, (dict, list)) else 1}
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("source_changed_during_scan")
            except (ValueError, OSError, zipfile.BadZipFile) as exc:
                details = {"error": str(exc)}
                errors.append({"path": str(path), "error": str(exc)})
            con.execute("INSERT INTO files VALUES(?,?,?,?,?)",
                        (str(path), sha, before.st_size, role, json.dumps(details)))
            con.commit()
        con.execute("INSERT INTO audit_fts(audit_fts) VALUES('rebuild')")
        # Only files in this scan participate, even when old parsed content is cached.
        active = "sha IN (SELECT sha FROM files WHERE role IN ('conversation_json','html_control') AND details NOT LIKE '%\"error\"%')"
        roles = dict(con.execute(f"SELECT role,count(*) FROM (SELECT DISTINCT cid,nid,payload_sha,role FROM messages WHERE {active}) GROUP BY role"))
        titles = [dict(r) for r in con.execute(f"SELECT title,count(DISTINCT cid) chats FROM chats WHERE {active} GROUP BY title HAVING count(DISTINCT cid)>1 ORDER BY chats DESC")]
        duplicates = [dict(r) for r in con.execute("SELECT sha,count(*) copies FROM files GROUP BY sha HAVING count(*)>1")]
        conflicts = con.execute(f"SELECT count(*) FROM (SELECT cid,nid FROM messages WHERE {active} GROUP BY cid,nid HAVING count(DISTINCT payload_sha)>1)").fetchone()[0]
        selected, covered = [], set()
        rows = con.execute("SELECT * FROM files WHERE role IN ('conversation_json','html_control','journal','music_analysis') ORDER BY CASE role WHEN 'conversation_json' THEN 0 WHEN 'html_control' THEN 1 ELSE 2 END,path").fetchall()
        seen = set()
        for row in rows:
            if row['sha'] in seen or 'error' in json.loads(row['details']):
                continue
            seen.add(row['sha'])
            keys = {(r[0], r[1]) for r in con.execute("SELECT cid,tree_sha FROM chats WHERE sha=?", (row['sha'],))}
            if keys - covered or row['role'] in {'journal', 'music_analysis'}:
                selected.append(row['path'])
                covered.update(keys)
        all_files = con.execute('SELECT path,role FROM files').fetchall()
        assets = []
        for pointer, filename in con.execute('SELECT DISTINCT pointer,filename FROM assets WHERE sha IN (SELECT sha FROM files)'):
            token = pointer.rsplit('/', 1)[-1]
            candidates = [r['path'] for r in all_files
                          if (filename and Path(r['path']).name == Path(filename).name)
                          or (len(token) >= 12 and token in Path(r['path']).name)]
            assets.append({'pointer': pointer, 'filename': filename, 'paths': candidates,
                           'status': 'resolved' if len(candidates) == 1 else 'ambiguous' if candidates else 'missing'})
        report = {"ok": not errors, "schema": AUDIT_VERSION, "root": str(root),
                  "catalog": str(catalog), "file_count": con.execute('SELECT count(*) FROM files').fetchone()[0],
                  "files_by_role": dict(con.execute('SELECT role,count(*) FROM files GROUP BY role')),
                  "conversation_count": con.execute(f'SELECT count(DISTINCT cid) FROM chats WHERE {active}').fetchone()[0],
                  "message_versions_by_role": roles, "same_title_distinct_chats": titles,
                  "unique_message_ids_by_role": dict(con.execute(f"SELECT role,count(*) FROM (SELECT DISTINCT cid,nid,role FROM messages WHERE {active}) GROUP BY role")),
                  "visible_path_message_ids_by_role": dict(con.execute(f"SELECT role,count(*) FROM (SELECT DISTINCT cid,nid,role FROM messages WHERE {active} AND visible=1) GROUP BY role")),
                  "chats": [dict(r) for r in con.execute(f"SELECT cid,title,count(DISTINCT sha) source_count FROM chats WHERE {active} GROUP BY cid,title ORDER BY title,cid")],
                  "duplicate_files": duplicates, "conflicting_message_ids": conflicts,
                  "selected_sources": selected, "errors": errors,
                  "assets": assets,
                  "copy_plan": [{'path': r['path'], 'role': r['role'],
                                 'reason': 'conversation_or_journal' if r['path'] in selected else
                                 'referenced_asset' if any(r['path'] in a['paths'] for a in assets) else
                                 'metadata_control' if r['role'] in {'relational_metadata','export_manifest','html_control'} else
                                 'account_optional' if r['role'] == 'account_metadata' else 'archive_or_unreferenced_review'} for r in all_files],
                  "embedded_sources": [{'archive': r['path'], 'archive_sha256': r['sha'], **m}
                                       for r in con.execute("SELECT * FROM files WHERE role='attachment_archive'")
                                       for m in json.loads(r['details']).get('embedded_memory_sources', [])],
                  "truth_boundary": "Source declarations and literary scenes are not verified lived events."}
        report['fingerprint'] = canonical_hash([tuple(r) for r in con.execute('SELECT path,sha,role FROM files ORDER BY path')])
        return report
