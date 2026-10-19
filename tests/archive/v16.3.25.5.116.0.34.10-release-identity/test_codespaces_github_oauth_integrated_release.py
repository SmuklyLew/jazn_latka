"""Combined release regression: private Codespaces + fail-closed GitHub MCP OAuth staging."""

from __future__ import annotations

import json
from pathlib import Path

from latka_jazn.version import PACKAGE_VERSION, PACKAGE_VERSION_FULL

ROOT = Path(__file__).resolve().parents[1]
OAUTH = ROOT / "deploy" / "chatgpt_mcp" / "workers_github_oauth"


def test_converged_release_metadata_and_startup_contract() -> None:
    startup = json.loads((ROOT / "latka_jazn" / "resources" / "startup_contract.json").read_text(encoding="utf-8"))
    deployment = json.loads((ROOT / "deploy" / "chatgpt_mcp" / "deployment.contract.json").read_text(encoding="utf-8"))
    assert PACKAGE_VERSION == "16.3.25.5.116.0.34.10"
    assert startup["version"] == PACKAGE_VERSION
    assert deployment["runtime_version"] == PACKAGE_VERSION_FULL
    assert "startup-index-ollama-visible" in PACKAGE_VERSION_FULL


def test_codespaces_does_not_publish_anonymous_mcp() -> None:
    config = json.loads((ROOT / ".devcontainer" / "devcontainer.json").read_text(encoding="utf-8"))
    assert config["forwardPorts"] == []
    assert config["portsAttributes"]["8080"]["onAutoForward"] == "ignore"
    assert "postStartCommand" not in config
    assert "run.py start" not in config["postCreateCommand"]
    assert "OPENAI_API_KEY" not in json.dumps(config)


def test_oauth_worker_staging_has_no_credentials_or_production_deploy() -> None:
    config_text = (OAUTH / "wrangler.jsonc").read_text(encoding="utf-8")
    source = (OAUTH / "src" / "index.mjs").read_text(encoding="utf-8")
    security = (OAUTH / "src" / "security.mjs").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "jazn-github-oauth-staging.yml").read_text(encoding="utf-8")
    assert '"workers_dev": true' in config_text
    assert '"OAUTH_KV"' in config_text
    assert '"GITHUB_CLIENT_SECRET"' not in config_text
    assert '"JAZN_INTROSPECTION_CLIENT_SECRET"' not in config_text
    assert "JAZN_INGRESS_MODE" not in config_text
    assert "requiresSafeAuthSettings" in source
    assert "githubIdentityAllowed" in source
    assert "tokenRecordToIntrospection" in source
    assert "RESOURCE" in security and "ISSUER" in security
    assert "npm ci" in workflow
    assert "wrangler deploy --dry-run" in workflow
    assert "wrangler deploy\n" not in workflow


def test_oauth_uses_dependency_lock_and_local_regression_tests() -> None:
    package = json.loads((OAUTH / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((OAUTH / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["lockfileVersion"] == 3
    assert package["name"] == lock["name"]
    assert lock["packages"]["node_modules/@cloudflare/workers-oauth-provider"]["version"].startswith("1.")
    assert (OAUTH / "test" / "security.test.mjs").is_file()
