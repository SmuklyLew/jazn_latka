from __future__ import annotations

"""Disk-backed, path-independent planning of a closed L0 source union."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import json
import sqlite3

from .intermediate import IntermediateRecord, PreparedSource, canonical_json

BATCH_POLICY = "closed-union/chronology-content-source-v1"


def source_key(source: PreparedSource) -> tuple[str, str, str]:
    return source.adapter_id, source.source_sha256, source.source_member or ""


def chronology(record: IntermediateRecord) -> str:
    # Missing, structural and ambiguous local times do not establish chronology.
    if record.timestamp_status not in {"exact", "source_recorded"}:
        return ""
    try:
        value = datetime.fromisoformat(record.event_time_start or "")
    except ValueError:
        return ""
    if value.tzinfo is None:
        return ""
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


class BatchPlan:
    """Consume each adapter iterator once before the destination is written.

    Revisions group equal content hashes, then sort by trusted UTC time and
    content hash. Sources and occurrences have their own stable tie-breakers.
    Original local locators remain in the caller's import report; source names
    stored in the reconstructed semantic database are content addresses.
    """

    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(path)
        self.sources: dict[tuple[str, str, str], PreparedSource] = {}
        self.connection.execute("""CREATE TABLE entries(
            logical_key TEXT, content_hash TEXT, chronology TEXT,
            adapter TEXT, sha TEXT, member TEXT, record_key TEXT, payload TEXT
        )""")
        self._sealed = False

    def close(self) -> None:
        self.connection.close()

    def add(self, source: PreparedSource) -> None:
        if self._sealed:
            raise ValueError("Batch plan is already sealed")
        key = source_key(source)
        canonical = replace(source, source_name=f"sha256:{source.source_sha256}")
        previous = self.sources.get(key)
        if previous is not None:
            if (previous.source_kind, previous.native_projection, canonical_json(previous.metadata)) != (
                canonical.source_kind, canonical.native_projection, canonical_json(canonical.metadata)
            ):
                raise ValueError("Conflicting metadata for the same source identity")
            return
        self.sources[key] = canonical
        for record in source.iter_records():
            self.connection.execute(
                "INSERT INTO entries VALUES(?,?,?,?,?,?,?,?)",
                (record.logical_key, record.content_sha256, chronology(record), *key,
                 record.source_record_id, canonical_json(asdict(record))),
            )
        self.connection.commit()

    def seal(self) -> None:
        self.connection.execute("""CREATE INDEX entries_variant ON entries(
            logical_key,content_hash,adapter,sha,member,record_key
        )""")
        self.connection.execute("""CREATE TABLE variants AS
            SELECT logical_key,content_hash,MAX(chronology) AS chronology
            FROM entries GROUP BY logical_key,content_hash""")
        self.connection.commit()
        self._sealed = True

    def iter_entries(self) -> Iterator[tuple[PreparedSource, IntermediateRecord]]:
        if not self._sealed:
            raise ValueError("Batch plan must be sealed before execution")
        rows = self.connection.execute("""SELECT e.adapter,e.sha,e.member,e.payload,v.chronology
            FROM variants v JOIN entries e
              ON e.logical_key=v.logical_key AND e.content_hash=v.content_hash
            ORDER BY v.logical_key,v.chronology,v.content_hash,
                     e.adapter,e.sha,e.member,e.record_key,e.payload""")
        for adapter, sha, member, payload, timestamp in rows:
            record = IntermediateRecord(**json.loads(payload))
            yield self.sources[(adapter, sha, member)], replace(
                record, provenance={
                    **record.provenance,
                    "batch_reconstruction": {
                        "policy": BATCH_POLICY,
                        "trusted_utc": timestamp or None,
                        "variant_tie_breaker": "content_sha256",
                        "representative_tie_breaker": "adapter_id,source_sha256,source_member,source_record_id,payload",
                        "unresolved_chronology": not bool(timestamp),
                    },
                },
            )
