from __future__ import annotations

"""v16.3.25 integration layer for source-union Memory Rebuild hardening."""

from pathlib import Path
from typing import Any, Iterable
import sqlite3

from latka_jazn.tools.chat_export_models import ConversationGraph
from latka_jazn.tools.chat_export_store import ChatExportArchiveStore

from .source_union import TOOL_RELEASE_LABEL, TOOL_REVISION, run_source_union_analysis


HARDENING_VERSION = "memory-rebuild-source-union-hardening/v16.3.25"


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_resolution_columns(con: sqlite3.Connection) -> None:
    columns = _columns(con, "import_conflicts")
    if not columns:
        return
    if "resolution_status" not in columns:
        con.execute(
            "ALTER TABLE import_conflicts ADD COLUMN resolution_status TEXT NOT NULL DEFAULT 'unresolved'"
        )
    if "resolution_reason" not in columns:
        con.execute("ALTER TABLE import_conflicts ADD COLUMN resolution_reason TEXT")


def _parent_conflicts(store: ChatExportArchiveStore, graph: ConversationGraph) -> tuple[str, ...]:
    existing = {
        str(row["node_id"]): (
            str(row["parent_node_id"]) if row["parent_node_id"] is not None else None
        )
        for row in store.con.execute(
            "SELECT node_id,parent_node_id FROM nodes WHERE conversation_id=?",
            (graph.conversation_id,),
        ).fetchall()
    }
    return tuple(
        sorted(
            node.node_id
            for node in graph.nodes
            if node.node_id in existing and existing[node.node_id] != node.parent_node_id
        )
    )


def _unresolved_with_resolution(original: Any, database: Path) -> dict[str, Any]:
    result = dict(original(database))
    if not database.is_file():
        return result
    try:
        with sqlite3.connect(
            f"file:{database.as_posix()}?mode=ro", uri=True, timeout=10
        ) as con:
            if "resolution_status" not in _columns(con, "import_conflicts"):
                return result
            unresolved = int(
                con.execute(
                    "SELECT COUNT(*) FROM import_conflicts "
                    "WHERE COALESCE(resolution_status,'unresolved')='unresolved'"
                ).fetchone()[0]
            )
            preserved = int(
                con.execute(
                    "SELECT COUNT(*) FROM import_conflicts WHERE resolution_status='preserved_union'"
                ).fetchone()[0]
            )
    except sqlite3.DatabaseError:
        return result
    old_chat = int(result.get("chat_import_conflicts", 0))
    result["chat_import_conflicts"] = unresolved
    result["preserved_chat_divergences"] = preserved
    result["total"] = max(0, int(result.get("total", 0)) - old_chat + unresolved)
    return result


def apply() -> None:
    import latka_jazn.tools.memory_rebuild_app.source_fidelity as source_fidelity
    import latka_jazn.tools.memory_rebuild_app.test_profiles as test_profiles

    if getattr(source_fidelity, "_JAZN_V16325_HARDENING_APPLIED", False):
        return

    original_test00 = source_fidelity.run_test00_source_fidelity
    original_archive_init = ChatExportArchiveStore.__init__
    original_store_graph = ChatExportArchiveStore.store_graph
    original_unresolved = test_profiles._unresolved_conflicts  # noqa: SLF001

    def test00_with_union(
        sources: Iterable[str | Path],
        *,
        output_root: str | Path,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        materialized = tuple(sources)
        report = original_test00(materialized, output_root=output_root, run_id=run_id)
        union = run_source_union_analysis(materialized, output_root=report["run_root"])
        report["source_union"] = union
        report["tool_revision"] = TOOL_REVISION
        report["tool_release_label"] = TOOL_RELEASE_LABEL
        if report.get("outcome") == "PASSED" and union.get("status") == "source_error":
            report["ok"] = False
            report["outcome"] = "FAILED"
        return report

    def archive_init(self: ChatExportArchiveStore, *args: Any, **kwargs: Any) -> None:
        original_archive_init(self, *args, **kwargs)
        _ensure_resolution_columns(self.con)

    def store_graph(
        self: ChatExportArchiveStore,
        import_id: str,
        graph: ConversationGraph,
        plan: Any,
    ) -> dict[str, int]:
        parent_conflicts = _parent_conflicts(self, graph)
        counters = original_store_graph(self, import_id, graph, plan)
        _ensure_resolution_columns(self.con)
        if str(getattr(plan, "relation", "")) == "divergent":
            changed = tuple(str(item) for item in getattr(plan, "changed_node_ids", ()) or ())
            safe = not changed and not parent_conflicts
            status = "preserved_union" if safe else "unresolved"
            reason = (
                "shared node payloads and parents agree; unique branches are preserved"
                if safe
                else "same node identity changed payload or parent; projection decision required"
            )
            self.con.execute(
                "UPDATE import_conflicts SET resolution_status=?,resolution_reason=? "
                "WHERE import_id=? AND conversation_id=?",
                (status, reason, import_id, graph.conversation_id),
            )
            counters["preserved_divergences"] = int(safe)
            counters["unresolved_divergences"] = int(not safe)
        return counters

    def unresolved_conflicts(database: Path) -> dict[str, Any]:
        return _unresolved_with_resolution(original_unresolved, database)

    source_fidelity.run_test00_source_fidelity = test00_with_union
    ChatExportArchiveStore.__init__ = archive_init
    ChatExportArchiveStore.store_graph = store_graph
    test_profiles._unresolved_conflicts = unresolved_conflicts  # noqa: SLF001
    setattr(source_fidelity, "_JAZN_V16325_HARDENING_APPLIED", True)


__all__ = ["HARDENING_VERSION", "apply"]
