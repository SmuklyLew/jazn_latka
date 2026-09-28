from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from latka_jazn.core.memory_search_planner import MemorySearchPlanner
from latka_jazn.memory.living_memory_gateway import LivingMemoryGateway
from latka_jazn.version import schema_version


SCHEMA_VERSION = schema_version("memory_sentinel_recall")
MANIFEST_SCHEMA = "jazn_memory_sentinel/v1"
MAX_SENTINEL_QUERIES = 64
MAX_QUERY_CHARS = 512


def _load_manifest(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path).expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("memory_sentinel_manifest_must_be_object")
    declared_schema = str(payload.get("schema_version") or MANIFEST_SCHEMA).strip()
    if declared_schema != MANIFEST_SCHEMA:
        raise ValueError("memory_sentinel_manifest_schema_unsupported")
    raw_queries = payload.get("queries")
    if not isinstance(raw_queries, list) or not raw_queries:
        raise ValueError("memory_sentinel_manifest_queries_required")
    if len(raw_queries) > MAX_SENTINEL_QUERIES:
        raise ValueError("memory_sentinel_manifest_too_many_queries")

    queries: list[dict[str, Any]] = []
    for index, item in enumerate(raw_queries):
        if not isinstance(item, Mapping):
            raise ValueError(f"memory_sentinel_query_must_be_object:{index}")
        query = str(item.get("query") or "").strip()
        if not query:
            raise ValueError(f"memory_sentinel_query_empty:{index}")
        if len(query) > MAX_QUERY_CHARS:
            raise ValueError(f"memory_sentinel_query_too_long:{index}")
        raw_minimum = item.get("minimum_native_hits", 1)
        if isinstance(raw_minimum, bool) or not isinstance(raw_minimum, int):
            raise ValueError(f"memory_sentinel_minimum_native_hits_must_be_integer:{index}")
        minimum = int(raw_minimum)
        if minimum < 1 or minimum > 100:
            raise ValueError(f"memory_sentinel_minimum_native_hits_out_of_range:{index}")
        queries.append({"query": query, "minimum_native_hits": minimum})
    return queries


def _query_fingerprint(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def _native_hits(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    hits = result.get("hits")
    if not isinstance(hits, list):
        return []
    accepted: list[Mapping[str, Any]] = []
    for raw in hits:
        if not isinstance(raw, Mapping):
            continue
        metadata = raw.get("metadata")
        if not isinstance(metadata, Mapping):
            continue
        if (
            str(metadata.get("gateway_source_kind") or "") == "native_unified"
            and metadata.get("autobiographical_source_ready") is True
            and metadata.get("selected_canonical") is True
        ):
            accepted.append(raw)
    return accepted


def _canonical_database(result: Mapping[str, Any]) -> str | None:
    sources = result.get("sources")
    if not isinstance(sources, list):
        return None
    for raw in sources:
        if not isinstance(raw, Mapping):
            continue
        if (
            raw.get("selected_canonical") is True
            and str(raw.get("source_kind") or "") == "native_unified"
        ):
            value = str(raw.get("canonical_database") or "").strip()
            if value:
                return value
    return None


def run_memory_sentinel(
    root: str | Path,
    *,
    manifest: str | Path,
    limit: int = 12,
) -> dict[str, Any]:
    """Verify private autobiographical recall without emitting private query text.

    The manifest remains external operator input. Results expose only query
    fingerprints, counts, readiness/provenance status, and the selected
    canonical database path. No excerpts or query strings are returned.
    """

    runtime_root = Path(root).expanduser().resolve()
    per_query_limit = max(1, min(100, int(limit)))
    queries = _load_manifest(manifest)
    planner = MemorySearchPlanner(runtime_root)
    gateway = LivingMemoryGateway(runtime_root)

    readiness = gateway.readiness()
    full_ready = readiness.get("full_autobiographical_recall_ready") is True

    rows: list[dict[str, Any]] = []
    native_hits_total = 0
    canonical_database: str | None = None

    for item in queries:
        query = str(item["query"])
        minimum = int(item["minimum_native_hits"])
        plan = planner.plan(query)
        result = gateway.search(plan, limit=max(per_query_limit, minimum))
        native_hits = _native_hits(result)
        native_count = len(native_hits)
        native_hits_total += native_count
        if canonical_database is None:
            canonical_database = _canonical_database(result)

        query_full_ready = result.get("full_autobiographical_recall_ready") is True
        rows.append(
            {
                "query_sha256": _query_fingerprint(query),
                "minimum_native_hits": minimum,
                "native_hit_count": native_count,
                "full_autobiographical_recall_ready": query_full_ready,
                "passed": bool(query_full_ready and native_count >= minimum),
            }
        )

    passed = sum(1 for row in rows if row["passed"] is True)
    ok = bool(full_ready and passed == len(rows))
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA,
        "ok": ok,
        "full_autobiographical_recall_ready": full_ready,
        "queries_total": len(rows),
        "queries_passed": passed,
        "native_hits_total": native_hits_total,
        "all_hits_have_local_provenance": bool(
            rows and all(row["passed"] is True for row in rows)
        ),
        "canonical_database": canonical_database,
        "results": rows,
        "private_queries_emitted": False,
        "private_excerpts_emitted": False,
        "truth_boundary": (
            "Sentinel success requires native unified autobiographical readiness "
            "and enough hits carrying selected canonical native provenance. "
            "Transactional-tier-only searchability never satisfies this gate."
        ),
    }
