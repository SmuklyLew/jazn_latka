from __future__ import annotations

from collections.abc import MutableMapping
import os

LOOPBACK_PROXY_BYPASS_HOSTS: tuple[str, ...] = (
    "localhost",
    "127.0.0.1",
    "::1",
)


def _merged_no_proxy_value(env: MutableMapping[str, str]) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for name in ("NO_PROXY", "no_proxy"):
        for raw_value in str(env.get(name, "") or "").split(","):
            value = raw_value.strip()
            if not value:
                continue
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            values.append(value)

    if "*" in seen:
        return "*"

    for host in LOOPBACK_PROXY_BYPASS_HOSTS:
        key = host.casefold()
        if key not in seen:
            seen.add(key)
            values.append(host)
    return ",".join(values)


def ensure_loopback_proxy_bypass(
    env: MutableMapping[str, str] | None = None,
) -> dict[str, str]:
    """Ensure local daemon traffic is never routed through an HTTP proxy.

    urllib imports proxy configuration from environment variables and, on
    Windows, from system proxy settings. Explicit NO_PROXY entries make local
    runtime probes deterministic while preserving every user-defined bypass.
    """
    target = os.environ if env is None else env
    merged = _merged_no_proxy_value(target)
    target["NO_PROXY"] = merged
    target["no_proxy"] = merged
    return {"NO_PROXY": merged, "no_proxy": merged}
