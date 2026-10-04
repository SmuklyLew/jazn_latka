from __future__ import annotations

from typing import Any, Mapping
import sqlite3
import uuid


def persist_record_metadata(
    con: sqlite3.Connection,
    *,
    record_id: str,
    source_id: str,
    raw: Mapping[str, Any],
    observed_at_utc: str,
) -> None:
    """Persist derived projection flags without deleting or rewriting RAW evidence."""

    visibility = str(raw.get("visibility") or "visible")
    memory_eligible = bool(raw.get("memory_eligible", True))
    con.execute(
        "UPDATE memory_l0_records SET visibility=?,memory_eligible=? WHERE record_id=?",
        (visibility, int(memory_eligible), record_id),
    )
    con.execute("DELETE FROM memory_l0_affect_claims WHERE record_id=?", (record_id,))
    claims = raw.get("__jazn_affect_claims__")
    for claim in claims if isinstance(claims, list) else ():
        if not isinstance(claim, Mapping):
            continue
        label = str(claim.get("label") or "").strip()
        if not label:
            continue
        source_field = str(claim.get("source_field") or "unknown").strip() or "unknown"
        claim_kind = str(claim.get("claim_kind") or "explicit_source_label").strip()
        subject = str(claim.get("subject") or "latka").strip() or "latka"
        boundary = str(
            claim.get("boundary") or "source_claimed_affect_not_biological_state"
        ).strip()
        normalized = " ".join(label.casefold().split())
        claim_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"jazn-affect-claim:{record_id}:{normalized}:{source_field}:{claim_kind}:{subject}",
        ))
        con.execute(
            """INSERT OR REPLACE INTO memory_l0_affect_claims(
               claim_id,record_id,source_id,label,normalized_label,source_field,
               claim_kind,subject,boundary,observed_at_utc
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                claim_id, record_id, source_id, label, normalized, source_field,
                claim_kind, subject, boundary, observed_at_utc,
            ),
        )

    assets = raw.get("assets")
    for asset in assets if isinstance(assets, list) else ():
        if not isinstance(asset, Mapping):
            continue
        pointer = str(asset.get("asset_pointer") or "").strip()
        if not pointer:
            continue
        con.execute(
            """INSERT INTO memory_l0_assets(
               asset_pointer,original_filename,content_type,mime_type,availability_status,
               file_sha256,first_seen_source_id,last_seen_source_id,first_seen_at_utc,last_seen_at_utc
               ) VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(asset_pointer) DO UPDATE SET
                 original_filename=COALESCE(excluded.original_filename,memory_l0_assets.original_filename),
                 content_type=COALESCE(excluded.content_type,memory_l0_assets.content_type),
                 mime_type=COALESCE(excluded.mime_type,memory_l0_assets.mime_type),
                 availability_status=excluded.availability_status,
                 file_sha256=COALESCE(excluded.file_sha256,memory_l0_assets.file_sha256),
                 last_seen_source_id=excluded.last_seen_source_id,
                 last_seen_at_utc=excluded.last_seen_at_utc""",
            (
                pointer,
                asset.get("original_filename"),
                asset.get("content_type"),
                asset.get("mime_type"),
                str(asset.get("availability_status") or "referenced_only"),
                asset.get("file_sha256"),
                source_id,
                source_id,
                observed_at_utc,
                observed_at_utc,
            ),
        )
        con.execute(
            "INSERT OR IGNORE INTO memory_l0_record_assets(record_id,asset_pointer) VALUES(?,?)",
            (record_id, pointer),
        )


__all__ = ["persist_record_metadata"]
