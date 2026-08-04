from __future__ import annotations

# One source of truth for clock acquisition and visible clock metadata.
# The wall clock supports continuity, but it is never an authorization gate for
# runtime startup, generation, finalization or display of a Jaźń reply.

TIMESTAMP_TIMEZONE = "Europe/Warsaw"
TIMESTAMP_ENVIRONMENT_FIRST_DEFAULT = True
TIMESTAMP_NETWORK_FIRST_DEFAULT = False  # compatibility field; normal turns are environment-first
TIMESTAMP_NETWORK_IN_NORMAL_TURN_DEFAULT = False
TIMESTAMP_NETWORK_FALLBACK_WHEN_CLOCK_UNAVAILABLE = True
TIMESTAMP_LOCAL_FALLBACK_ALLOWED_DEFAULT = True
TIMESTAMP_NETWORK_TIMEOUT_SECONDS = 1.5
TIMESTAMP_MAX_AGE_SECONDS = 120
TIMESTAMP_REQUIRE_TRUSTED_IN_FINAL_VISIBLE = False
TIMESTAMP_ALLOW_DEGRADED_LOCAL_VISIBLE = True
from latka_jazn.version import schema_version

TIMESTAMP_POLICY_SCHEMA = schema_version("timestamp_runtime_policy")


def timestamp_runtime_policy() -> dict:
    return {
        "schema_version": TIMESTAMP_POLICY_SCHEMA,
        "timezone": TIMESTAMP_TIMEZONE,
        "environment_first_default": TIMESTAMP_ENVIRONMENT_FIRST_DEFAULT,
        "network_first_default": TIMESTAMP_NETWORK_FIRST_DEFAULT,
        "network_time_in_normal_turn_default": TIMESTAMP_NETWORK_IN_NORMAL_TURN_DEFAULT,
        "network_fallback_when_clock_unavailable": TIMESTAMP_NETWORK_FALLBACK_WHEN_CLOCK_UNAVAILABLE,
        "local_fallback_allowed_default": TIMESTAMP_LOCAL_FALLBACK_ALLOWED_DEFAULT,
        "network_timeout_seconds": TIMESTAMP_NETWORK_TIMEOUT_SECONDS,
        "max_age_seconds": TIMESTAMP_MAX_AGE_SECONDS,
        "require_trusted_in_final_visible": TIMESTAMP_REQUIRE_TRUSTED_IN_FINAL_VISIBLE,
        "allow_degraded_local_visible": TIMESTAMP_ALLOW_DEGRADED_LOCAL_VISIBLE,
        "clock_unavailable_header": "🕒 [ZEGAR NIEDOSTĘPNY]",
        "truth_boundary": (
            "Runtime first reads an available clock from its execution environment and converts it to Europe/Warsaw. "
            "Network time is attempted only when the environment clock cannot be obtained. "
            "If neither source is available, the visible header is '🕒 [ZEGAR NIEDOSTĘPNY]'. "
            "Clock absence, age, source or trust never blocks startup or a reply."
        ),
    }
