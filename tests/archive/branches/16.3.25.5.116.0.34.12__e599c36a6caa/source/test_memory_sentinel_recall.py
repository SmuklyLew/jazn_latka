from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.memory import sentinel_recall


class _Plan:
    pass


class _Planner:
    def __init__(self, root: Path) -> None:
        self.root = root

    def plan(self, query: str) -> _Plan:
        return _Plan()


class _NativeGateway:
    def __init__(self, root: Path) -> None:
        self.root = root

    def readiness(self) -> dict[str, object]:
        return {"full_autobiographical_recall_ready": True}

    def search(self, plan: object, *, limit: int) -> dict[str, object]:
        return {
            "full_autobiographical_recall_ready": True,
            "hits": [
                {
                    "content_excerpt": "private synthetic excerpt that must not escape",
                    "metadata": {
                        "gateway_source_kind": "native_unified",
                        "autobiographical_source_ready": True,
                        "selected_canonical": True,
                    },
                }
            ],
            "sources": [
                {
                    "selected_canonical": True,
                    "source_kind": "native_unified",
                    "canonical_database": "/private/memory/sqlite/memory_jazn.sqlite3",
                }
            ],
        }


class _TierOnlyGateway(_NativeGateway):
    def readiness(self) -> dict[str, object]:
        return {"full_autobiographical_recall_ready": False}

    def search(self, plan: object, *, limit: int) -> dict[str, object]:
        return {
            "full_autobiographical_recall_ready": False,
            "hits": [
                {
                    "content_excerpt": "tier content",
                    "metadata": {
                        "gateway_source_kind": "transactional_tier_memory",
                        "autobiographical_source_ready": False,
                        "selected_canonical": False,
                    },
                }
            ],
            "sources": [],
        }


def _manifest(tmp_path: Path, query: str = "private sentinel phrase") -> Path:
    path = tmp_path / "sentinel.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "jazn_memory_sentinel/v1",
                "queries": [
                    {
                        "query": query,
                        "minimum_native_hits": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_sentinel_accepts_only_native_unified_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(sentinel_recall, "MemorySearchPlanner", _Planner)
    monkeypatch.setattr(sentinel_recall, "LivingMemoryGateway", _NativeGateway)
    query = "private sentinel phrase"

    result = sentinel_recall.run_memory_sentinel(
        tmp_path,
        manifest=_manifest(tmp_path, query),
    )

    assert result["ok"] is True
    assert result["queries_passed"] == 1
    assert result["native_hits_total"] == 1
    assert result["all_hits_have_local_provenance"] is True
    assert result["private_queries_emitted"] is False
    assert result["private_excerpts_emitted"] is False
    serialized = json.dumps(result, ensure_ascii=False)
    assert query not in serialized
    assert "private synthetic excerpt" not in serialized


def test_sentinel_rejects_transactional_tier_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(sentinel_recall, "MemorySearchPlanner", _Planner)
    monkeypatch.setattr(sentinel_recall, "LivingMemoryGateway", _TierOnlyGateway)

    result = sentinel_recall.run_memory_sentinel(
        tmp_path,
        manifest=_manifest(tmp_path),
    )

    assert result["ok"] is False
    assert result["full_autobiographical_recall_ready"] is False
    assert result["queries_passed"] == 0
    assert result["native_hits_total"] == 0


def test_sentinel_manifest_must_be_external_valid_contract(tmp_path: Path) -> None:
    manifest = tmp_path / "invalid.json"
    manifest.write_text(json.dumps({"queries": []}), encoding="utf-8")

    try:
        sentinel_recall.run_memory_sentinel(tmp_path, manifest=manifest)
    except ValueError as exc:
        assert str(exc) == "memory_sentinel_manifest_queries_required"
    else:
        raise AssertionError("empty sentinel manifest must fail closed")
