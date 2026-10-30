"""Only canonical contract fields may serialize release identity."""
import json

import pytest

from tests.test_version_consistency_audit import _write_version
from latka_jazn.tools.version_consistency_audit import (
    VERSION_BOUND_CONTRACTS, _generated_metadata_errors, scan_forbidden_current_literals,
)
from latka_jazn.version import PACKAGE_VERSION, PACKAGE_VERSION_FULL


@pytest.mark.parametrize("relative", VERSION_BOUND_CONTRACTS)
@pytest.mark.parametrize("mode", ["valid", "stale", "missing", "duplicate", "other_field", "broken"])
def test_version_contract_checks_exact_field_without_exempting_file(tmp_path, relative, mode):
    _write_version(tmp_path)
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    field, attribute = VERSION_BOUND_CONTRACTS[relative]
    expected = PACKAGE_VERSION if attribute == "package_version" else PACKAGE_VERSION_FULL
    payload = {field: expected}
    if mode == "stale":
        payload[field] = "0.0.0"
    elif mode == "missing":
        payload = {}
    elif mode == "other_field":
        payload["unauthorized"] = PACKAGE_VERSION_FULL
    text = json.dumps(payload)
    if mode == "duplicate":
        text = '{"%s": "%s", "%s": "%s"}' % (field, expected, field, expected)
    elif mode == "broken":
        text = "["
    path.write_text(text, encoding="utf-8")
    errors = [e for e in _generated_metadata_errors(tmp_path) if e["kind"].startswith("version_bound_contract")]
    assert bool(errors) is (mode in {"stale", "missing", "duplicate", "broken"})
    violations = scan_forbidden_current_literals(tmp_path)
    assert any(e["path"] == relative for e in violations) is (mode in {"duplicate", "other_field"})
