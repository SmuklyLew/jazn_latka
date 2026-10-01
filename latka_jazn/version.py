from __future__ import annotations

# v16.3.25.5.95 makes the ChatGPT -> Jaźń boundary an installable MCP/plugin
# ingress contract: canonical model-visible actions, persistent remote runtime
# evidence, and current Agent Plugins packaging without claiming host capability.
DISTRIBUTION_VERSION = "16.3.25.5.95"
PACKAGE_VERSION = "16.3.25.5.95"
PACKAGE_RELEASE_NAME = "chatgpt-real-mcp-ingress-convergence"
PACKAGE_VERSION_FULL = (
    f"{PACKAGE_VERSION}-{PACKAGE_RELEASE_NAME}"
    if PACKAGE_RELEASE_NAME
    else PACKAGE_VERSION
)


def schema_version(name: str) -> str:
    return f"{name}/v1"
