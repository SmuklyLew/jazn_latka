from __future__ import annotations

from latka_jazn.dependencies.environment import _inspect_inventory


def test_pip_inspect_inventory_uses_canonical_distribution_names() -> None:
    payload = {
        "installed": [
            {
                "metadata": {
                    "name": "backports.zstd",
                    "version": "1.7.0",
                }
            }
        ]
    }

    assert _inspect_inventory(payload) == {"backports-zstd": "1.7.0"}
