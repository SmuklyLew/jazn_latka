from __future__ import annotations

"""v16.3.12 compatibility fixes for the v16.3.11 Memory Rebuild hardening.

This layer intentionally keeps the v16.3.11 schema/feature contract intact while
repairing two regressions found by the full deterministic suite:

* non-chat L0 evidence (journal/legacy/etc.) must not be disabled merely because
  it has no user/assistant role;
* archived conversation-variant identifiers must be reproducible for the same
  source graph across fresh rebuild targets.
"""

import sqlite3
import uuid
from typing import Any

from latka_jazn.tools.chat_export_models import ConversationGraph
from latka_jazn.tools.chat_export_store import ChatExportArchiveStore

from . import v16311_hardening as previous

HOTFIX_VERSION = "memory-rebuild-ci-hotfix/v16.3.12"

_ORIGINAL_ENSURE_EXTENDED_L0_SCHEMA = previous._ensure_extended_l0_schema


def _ensure_extended_l0_schema_v16312(con: sqlite3.Connection) -> None:
    _ORIGINAL_ENSURE_EXTENDED_L0_SCHEMA(con)
    # v16.3.11 visibility gating is a chat-message policy. Journal entries and
    # other source-evidence kinds can legitimately have no dialogue role and
    # must remain recall-eligible. Re-applying this correction is idempotent and
    # also repairs databases touched by the earlier regression.
    con.execute(
        """UPDATE memory_l0_records
           SET visibility='visible', memory_eligible=1
           WHERE record_kind<>'conversation_message'"""
    )


def _archive_variant_v16312(
    self: ChatExportArchiveStore,
    import_id: str,
    graph: ConversationGraph,
    relation: str,
) -> None:
    compressed, raw_size = previous._compressed_payload(graph)
    # Do not bind the primary key to import_id: import IDs are intentionally
    # operational/volatile and differ between otherwise identical fresh
    # rebuilds. Raw+semantic graph fingerprints preserve genuinely different
    # source variants while deduplicating the same variant deterministically.
    variant_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            "jazn-chat-archive-variant:"
            f"{graph.conversation_id}:{graph.raw_tree_sha256}:{graph.semantic_tree_sha256}",
        )
    )
    self.con.execute(
        """INSERT OR IGNORE INTO conversation_variant_payloads(
           variant_id,conversation_id,import_id,relation_to_active,raw_tree_sha256,
           semantic_tree_sha256,payload_codec,payload_blob,payload_size_uncompressed,created_at_utc
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            variant_id,
            graph.conversation_id,
            import_id,
            relation,
            graph.raw_tree_sha256,
            graph.semantic_tree_sha256,
            previous.PAYLOAD_CODEC,
            sqlite3.Binary(compressed),
            raw_size,
            previous._utc_now(),
        ),
    )


def apply() -> None:
    if getattr(previous, "_JAZN_V16312_CI_HOTFIX_APPLIED", False):
        return

    # v16.3.11 installed closures call these names through their module globals,
    # so replacing only the two defective policies preserves the rest of the
    # already-tested hardening and avoids a second rebuild engine.
    previous._ensure_extended_l0_schema = _ensure_extended_l0_schema_v16312
    previous._archive_variant = _archive_variant_v16312
    setattr(previous, "_JAZN_V16312_CI_HOTFIX_APPLIED", True)


__all__ = ["HOTFIX_VERSION", "apply"]
