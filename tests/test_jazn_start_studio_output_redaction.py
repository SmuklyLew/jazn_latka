"""Studio Startu must not persist even short operator credentials."""
from __future__ import annotations

import pytest

from tools.jazn_start_studio import safe_line


@pytest.mark.parametrize("text, exposed", [
    ("password=abc", "abc"),
    ('{"api_key": "small value"}', "small value"),
    ("JAZN_DAEMON_TOKEN=short", "short"),
    ("session_credential='x'", "='x'"),
    ("Authorization: Bearer abc", "Bearer abc"),
    ("http://alice:pw@localhost:8080/mcp", "alice:pw"),
])
def test_operator_output_masks_credential_text(text: str, exposed: str) -> None:
    masked = safe_line(text)
    assert exposed not in masked
    assert "[UKRYTO]" in masked


def test_studio_output_keeps_nonsecret_boolean_and_plain_diagnostics() -> None:
    assert safe_line('requires_api_key=false') == 'requires_api_key=false'
    assert safe_line('model ready; version=1.2.3') == 'model ready; version=1.2.3'


def test_studio_output_keeps_token_counters_and_nonsecret_metrics() -> None:
    assert safe_line('token_count=125') == 'token_count=125'
    assert safe_line('token_limit=300') == 'token_limit=300'
    assert safe_line('password_policy=enabled') == 'password_policy=enabled'
