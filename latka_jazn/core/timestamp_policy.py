from __future__ import annotations

from latka_jazn.version import schema_version

# P0: jeden punkt prawdy dla widocznego czasu Jaźni.
# Timestamp jest częścią ciągłości i kontraktu prawdy, nie ozdobą UI.

TIMESTAMP_TIMEZONE = "Europe/Warsaw"
TIMESTAMP_NETWORK_FIRST_DEFAULT = False
TIMESTAMP_NETWORK_IN_NORMAL_TURN_DEFAULT = False
TIMESTAMP_LOCAL_FALLBACK_ALLOWED_DEFAULT = True
TIMESTAMP_NETWORK_TIMEOUT_SECONDS = 1.5
TIMESTAMP_MAX_AGE_SECONDS = 120
TIMESTAMP_REQUIRE_TRUSTED_IN_FINAL_VISIBLE = False
TIMESTAMP_ALLOW_DEGRADED_LOCAL_VISIBLE = True

LOCAL_OS_TIMESTAMP_SOURCE_PREFIXES = (
    "local_fallback",
    "system_local",
    "local_machine",
    "system_utc",
    "utc_system_clock",
)


def timestamp_source_is_local_os(source: object) -> bool:
    """Return true only for timestamp sources produced by the host OS clock."""
    value = str(source or "").strip().lower()
    return bool(value) and value.startswith(LOCAL_OS_TIMESTAMP_SOURCE_PREFIXES)

TIMESTAMP_POLICY_SCHEMA = schema_version("timestamp_runtime_policy")


def timestamp_runtime_policy() -> dict:
    return {
        "schema_version": TIMESTAMP_POLICY_SCHEMA,
        "timezone": TIMESTAMP_TIMEZONE,
        "network_first_default": TIMESTAMP_NETWORK_FIRST_DEFAULT,
        "network_time_in_normal_turn_default": TIMESTAMP_NETWORK_IN_NORMAL_TURN_DEFAULT,
        "local_fallback_allowed_default": TIMESTAMP_LOCAL_FALLBACK_ALLOWED_DEFAULT,
        "network_timeout_seconds": TIMESTAMP_NETWORK_TIMEOUT_SECONDS,
        "max_age_seconds": TIMESTAMP_MAX_AGE_SECONDS,
        "require_trusted_in_final_visible": TIMESTAMP_REQUIRE_TRUSTED_IN_FINAL_VISIBLE,
        "allow_degraded_local_visible": TIMESTAMP_ALLOW_DEGRADED_LOCAL_VISIBLE,
        "truth_boundary": (
            "Widoczny timestamp preferuje czas sieciowy albo zaufany czas wstrzyknięty przez loader, "
            "ale ich brak nie blokuje odpowiedzi. Świeży czas z zegara OS środowiska jest dozwolonym "
            "źródłem widocznego timestampu i ciągłości rozmowy. Pole trusted opisuje wyłącznie zewnętrzną "
            "weryfikację źródła, a nie pozwolenie na pokazanie odpowiedzi."
        ),
    }
