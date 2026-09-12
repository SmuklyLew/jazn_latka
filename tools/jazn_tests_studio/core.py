from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from latka_jazn.tools.application_shell import ShellSettings, load_shell_settings, save_shell_settings

APP_NAME = "Jaźń - Studio Testów"
APP_VERSION = "1.3.0"
VALID_REVIEW = {"current", "review_required", "obsolete", "incompatible"}
EVENT_MARKER = "JAZN_TEST_STUDIO_EVENT "
UI_STATUS = {
    "PASSED": "CORRECT",
    "FAILED": "FAIL",
    "ERROR": "ERROR",
    "SKIPPED": "SKIP",
    "XFAIL": "XFAIL",
    "XPASS": "XPASS",
}


def find_root(explicit: str | None = None) -> Path:
    starts: list[Path] = []
    if explicit:
        starts.append(Path(explicit).expanduser().resolve())
    starts.extend([Path.cwd().resolve(), Path(__file__).resolve().parents[1]])
    checked: list[str] = []
    for start in starts:
        for candidate in (start, *start.parents):
            checked.append(str(candidate))
            if (candidate / "tests").is_dir() and (candidate / "pyproject.toml").is_file():
                return candidate
    raise RuntimeError(
        "Nie znaleziono katalogu repozytorium z tests/ i pyproject.toml. Sprawdzono: "
        + ", ".join(dict.fromkeys(checked))
    )


def support_dir(root: Path) -> Path:
    return Path(root) / "tools" / "jazn_tests_studio"


def local_settings_path(root: Path) -> Path:
    return support_dir(root) / "local_settings.json"


def default_shell_settings() -> ShellSettings:
    return ShellSettings(ui_mode="window" if sys.platform.startswith("win") else "tui")


def load_ui_settings(root: Path) -> ShellSettings:
    return load_shell_settings(local_settings_path(root), defaults=default_shell_settings())


def save_ui_settings(root: Path, settings: ShellSettings) -> ShellSettings:
    return save_shell_settings(local_settings_path(root), settings)


def policy_settings(root: Path) -> dict[str, Any]:
    path = support_dir(root) / "settings.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


@lru_cache(maxsize=32)
def _read_json_cached(path_text: str, mtime_ns: int, size: int) -> dict[str, Any]:
    del mtime_ns, size
    path = Path(path_text)
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError(f"Oczekiwano obiektu JSON: {path}")
    return raw


def _read_json(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return _read_json_cached(str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))


def load_catalog(root: Path) -> dict[str, Any]:
    path = support_dir(root) / "test_contracts.json"
    if not path.is_file():
        raise RuntimeError(f"Brak katalogu kontraktów: {path}. Uruchom migrator/test governance.")
    return _read_json(path)


def load_reviews(root: Path) -> dict[str, Any]:
    path = support_dir(root) / "reviews.json"
    if not path.is_file():
        return {"schema": "jazn_tests_studio_reviews/v1", "reviews": {}}
    try:
        payload = _read_json(path)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {"schema": "jazn_tests_studio_reviews/v1", "reviews": {}}
    result = dict(payload)
    reviews = result.get("reviews")
    result["reviews"] = dict(reviews) if isinstance(reviews, dict) else {}
    return result


def save_reviews(root: Path, payload: dict[str, Any]) -> None:
    path = support_dir(root) / "reviews.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    _read_json_cached.cache_clear()


def contracts(root: Path) -> dict[str, dict[str, Any]]:
    raw = load_catalog(root).get("contracts", {})
    return dict(raw) if isinstance(raw, dict) else {}


def _effective(base: dict[str, Any], review: dict[str, Any] | None) -> dict[str, Any]:
    item = dict(base)
    if review:
        item["review"] = dict(review)
        item["status"] = review.get("status", item.get("status", "current"))
        for key in ("purpose", "expected", "notes"):
            if review.get(key):
                item[key] = review[key]
    return item


def effective_contract(root: Path, nodeid: str) -> dict[str, Any]:
    catalog = contracts(root)
    base = catalog.get(nodeid)
    if base is None:
        raise KeyError(nodeid)
    reviews = load_reviews(root).get("reviews", {})
    review = reviews.get(nodeid) if isinstance(reviews, dict) else None
    return _effective(base, review if isinstance(review, dict) else None)


def filtered(root: Path, query: str = "", status: str = "all") -> list[tuple[str, dict[str, Any]]]:
    q = query.lower().strip()
    catalog = contracts(root)
    review_map = load_reviews(root).get("reviews", {})
    if not isinstance(review_map, dict):
        review_map = {}
    result: list[tuple[str, dict[str, Any]]] = []
    for nodeid in sorted(catalog):
        review = review_map.get(nodeid)
        item = _effective(catalog[nodeid], review if isinstance(review, dict) else None)
        if status != "all" and item.get("status") != status:
            continue
        tags = item.get("tags", [])
        haystack = " ".join(
            [
                nodeid,
                str(item.get("purpose", "")),
                str(item.get("category", "")),
                " ".join(map(str, tags if isinstance(tags, list) else [])),
            ]
        ).lower()
        if q and q not in haystack:
            continue
        result.append((nodeid, item))
    return result


def audit(root: Path) -> dict[str, Any]:
    started = time.monotonic()
    payload = load_catalog(root)
    rows = filtered(root)
    reviews = load_reviews(root).get("reviews", {})
    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for _, item in rows:
        item_status = str(item.get("status", "current"))
        category = str(item.get("category", "unknown"))
        by_status[item_status] = by_status.get(item_status, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
    return {
        "app": f"{APP_NAME} {APP_VERSION}",
        "root": str(root),
        "definitions": payload.get("active_definition_count", len(rows)),
        "manual_reviews": len(reviews) if isinstance(reviews, dict) else 0,
        "by_status": by_status,
        "by_category": by_category,
        "catalog_load_seconds": round(time.monotonic() - started, 4),
    }


def set_review(
    root: Path,
    nodeid: str,
    status: str,
    purpose: str = "",
    expected: str = "",
    notes: str = "",
) -> None:
    if status not in VALID_REVIEW:
        raise ValueError(f"Niepoprawny status: {status}")
    if nodeid not in contracts(root):
        raise KeyError(f"Nieznany test: {nodeid}")
    payload = load_reviews(root)
    review_map = payload.setdefault("reviews", {})
    if not isinstance(review_map, dict):
        review_map = {}
        payload["reviews"] = review_map
    review_map[nodeid] = {
        "status": status,
        "purpose": purpose,
        "expected": expected,
        "notes": notes,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_reviews(root, payload)


def invalidate_caches() -> None:
    _read_json_cached.cache_clear()
