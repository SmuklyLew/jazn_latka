from __future__ import annotations

from pathlib import Path

from latka_jazn.dependencies.runtime import (
    activation_profile_names,
    expand_profile_names,
    release_profile_names,
    resolve_profile_requirements,
)


ROOT = Path(__file__).parents[1]


def test_mcp_http_profile_maps_public_ingress_dependencies_without_promoting_core() -> None:
    requirements = resolve_profile_requirements(ROOT, ["mcp-http"])

    assert requirements == [
        "mcp==2.2.0",
        "pydantic>=2.7",
        "starlette>=0.48.0",
        "uvicorn>=0.31.1,<1",
    ]
    assert "mcp-http" not in activation_profile_names(ROOT)
    assert "mcp-http" not in release_profile_names(ROOT)
    assert "mcp-http" in expand_profile_names(ROOT, ["all"])
