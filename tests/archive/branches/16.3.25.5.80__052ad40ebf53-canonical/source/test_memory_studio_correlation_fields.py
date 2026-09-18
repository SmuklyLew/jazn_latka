import hashlib
import json
import sqlite3

from latka_jazn.tools.memory_rebuild_app.studio_links import correlate_file


def test_ascii_journal_content_and_source_bytes_are_traceable(tmp_path):
    catalog = tmp_path / "catalog.sqlite3"
    con = sqlite3.connect(catalog)
    con.executescript("""
        CREATE TABLE files(sha TEXT, details TEXT);
        INSERT INTO files VALUES('source','{}');
        CREATE TABLE messages(sha TEXT,cid TEXT,nid TEXT,mid TEXT,role TEXT,time REAL,text TEXT,payload_sha TEXT);
        INSERT INTO messages VALUES('source','chat','node','message','assistant',1754000000,'Zapisana refleksja','payload');
        CREATE VIRTUAL TABLE audit_fts USING fts5(text);
        INSERT INTO audit_fts(rowid,text) VALUES(1,'Zapisana refleksja');
    """)
    con.commit()
    con.close()
    source = tmp_path / "journal.json"
    data = json.dumps({"entries": [{"tresc": "Zapisana refleksja", "timestamp": 1754000000}]}).encode()
    source.write_bytes(data)
    result = correlate_file(catalog, source)
    assert result["time_correlated"] == 1
    assert result["results"][0]["candidates"][0]["exact_text"] is True
    assert result["source_sha256"] == hashlib.sha256(data).hexdigest()
    assert result["source_size_bytes"] == len(data)
