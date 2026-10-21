from __future__ import annotations

"""Public, operator-facing rebuild steps.

The v4 protocol persists legacy test00..test04 keys in signed/hashed manifests.
Those keys are deliberately preserved for backwards compatibility. A STEP does
work; a TEST/validator only verifies data, formatting and postconditions.
No runner is duplicated here.
"""

from dataclasses import dataclass

from .test_spec import TEST_PROTOCOL_ORDER, TEST_SPEC_BY_PROFILE


@dataclass(frozen=True, slots=True)
class RebuildStep:
    step_id: str
    legacy_profile: str
    label: str
    goal: str
    required_predecessors: tuple[str, ...]
    checks: tuple[str, ...]
    phases: tuple[str, ...]


STEP_NAMES = (
    ("step00", "test00", "Krok 00 — Inwentaryzacja i wierność źródeł"),
    ("step01", "test01", "Krok 01 — Budowa kanonicznego L0"),
    ("step02", "test02", "Krok 02 — Normalizacja i indeksowanie"),
    ("step03", "test03", "Krok 03 — Odbudowa porównawcza"),
    ("step04", "test04", "Krok 04 — Ocena Recall i akceptacja"),
    ("final", "final", "Krok 05 — Finalizacja i bezpieczny eksport"),
)

STEP_SPECS: tuple[RebuildStep, ...] = tuple(
    RebuildStep(
        step_id=step_id,
        legacy_profile=profile,
        label=label,
        goal=TEST_SPEC_BY_PROFILE[profile].goal,
        required_predecessors=tuple(
            "step" + parent[-2:] if parent.startswith("test") else parent
            for parent in TEST_SPEC_BY_PROFILE[profile].required_predecessors
        ),
        checks=TEST_SPEC_BY_PROFILE[profile].checks,
        phases=TEST_SPEC_BY_PROFILE[profile].phases,
    )
    for step_id, profile, label in STEP_NAMES
)
STEP_ORDER = tuple(item.step_id for item in STEP_SPECS)
STEP_BY_ID = {item.step_id: item for item in STEP_SPECS}
STEP_BY_PROFILE = {item.legacy_profile: item for item in STEP_SPECS}


def legacy_profile_for_step(value: str) -> str:
    key = value.strip().lower()
    if key in STEP_BY_ID:
        return STEP_BY_ID[key].legacy_profile
    if key in TEST_PROTOCOL_ORDER:
        return key
    raise ValueError(f"Unknown Memory Rebuild step: {value}")


def step_for_legacy_profile(value: str) -> RebuildStep:
    profile = legacy_profile_for_step(value)
    return STEP_BY_PROFILE[profile]


__all__ = [
    "RebuildStep", "STEP_NAMES", "STEP_SPECS", "STEP_ORDER", "STEP_BY_ID",
    "legacy_profile_for_step", "step_for_legacy_profile",
]
