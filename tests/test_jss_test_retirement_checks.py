"""GitHub checks for destructive test retirement require fresh complete proof."""
from __future__ import annotations

import json

import pytest

from tools.jazn_tests_studio import retirement


REQUIRED = [
    "manifest_sync", "test (ubuntu-latest, 3.12)", "test (windows-latest, 3.12)",
]


class Response:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *_args):
        return False
    def read(self, _limit):
        return self.body


def _row(name: str, check_id: int, *, conclusion: str = "success", status: str = "completed"):
    return {"id": check_id, "name": name, "conclusion": conclusion, "status": status}


def test_green_checks_verify_required_matrix_and_exact_sha(monkeypatch):
    rows = [_row(name, index + 1) for index, name in enumerate(REQUIRED)]
    urls = []
    def fake_urlopen(request, *, timeout):
        urls.append(request.full_url)
        return Response({"total_count": len(rows), "check_runs": rows})
    monkeypatch.setattr(retirement, "urlopen", fake_urlopen)
    result = retirement._green_checks("a" * 40)
    assert result == sorted(REQUIRED)
    assert "/commits/" + "a" * 40 + "/check-runs?" in urls[0]
    with pytest.raises(ValueError, match="Invalid commit SHA"):
        retirement._green_checks("a" * 8)


def test_pending_required_check_cannot_authorize_retirement(monkeypatch):
    rows = [_row(name, index + 1) for index, name in enumerate(REQUIRED)]
    rows[2]["status"] = "in_progress"
    rows[2]["conclusion"] = None
    monkeypatch.setattr(retirement, "urlopen", lambda *_a, **_kw:
                        Response({"total_count": len(rows), "check_runs": rows}))
    with pytest.raises(ValueError, match="not all successful"):
        retirement._green_checks("a" * 40)


def test_latest_successful_rerun_supersedes_prior_failed_check(monkeypatch):
    rows = [_row(name, index + 1) for index, name in enumerate(REQUIRED)]
    rows += [_row(REQUIRED[1], 100, conclusion="failure"),
             _row(REQUIRED[1], 200, conclusion="success")]
    monkeypatch.setattr(retirement, "urlopen", lambda *_a, **_kw:
                        Response({"total_count": len(rows), "check_runs": rows}))
    assert retirement._green_checks("a" * 40) == sorted(REQUIRED)


def test_checks_are_paginated_and_incomplete_evidence_is_rejected(monkeypatch):
    rows = [_row(name, index + 1) for index, name in enumerate(REQUIRED)]
    rows += [_row("nonrequired-" + str(i), 10 + i) for i in range(98)]
    assert len(rows) == 101
    pages = []
    def fake_urlopen(request, *, timeout):
        page = 1 if request.full_url.endswith("&page=1") else 2
        pages.append(page)
        return Response({"total_count": 101, "check_runs": rows[(page-1)*100:page*100]})
    monkeypatch.setattr(retirement, "urlopen", fake_urlopen)
    assert len(retirement._green_checks("a" * 40)) == 101
    assert pages == [1, 2]

    def truncated(request, *, timeout):
        return Response({"total_count": 101, "check_runs": rows[:100] if request.full_url.endswith("&page=1") else []})
    monkeypatch.setattr(retirement, "urlopen", truncated)
    with pytest.raises(ValueError, match="Unable to verify"):
        retirement._green_checks("a" * 40)
