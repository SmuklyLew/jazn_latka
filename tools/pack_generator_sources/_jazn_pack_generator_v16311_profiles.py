from __future__ import annotations

"""v16.3.11 packaging-profile contract hardening.

Profiles are user-facing product contracts, not best-effort suggestions:

1. ``combined`` -> system and complete memory in one package,
2. ``system``   -> system only,
3. ``memory``   -> complete memory only,
4. ``dual``     -> exactly two packages: system and complete memory.

Any profile that promises memory fails closed when no eligible memory payload is
available. In particular, ``dual`` must never silently degrade to ``system``.
The stable generator identity remains v8.5. Historical public choice constants
are retained as compatibility aliases; ``USER_PROFILE_CHOICES`` is canonical.
"""

from pathlib import PurePosixPath
from typing import Any, Sequence

GENERATOR_VERSION = "8.5"
SETTINGS_SCHEMA = "jazn_pack_generator_settings/v8.5"
LEGACY_PROFILE_CHOICES = ("system", "dual", "memory")
LEGACY_PACK_PROFILE_CHOICES = ("system", "dual", "memory", "combined")
USER_PROFILE_CHOICES = ("combined", "system", "memory", "dual")
PROFILE_DISPLAY = {
    "combined": "SYSTEM + PAMIĘĆ (1 ZIP)",
    "system": "SYSTEM",
    "memory": "PAMIĘĆ",
    "dual": "SYSTEM + PAMIĘĆ (2 OSOBNE ZIP-y)",
}
PROFILE_DESCRIPTIONS = {
    "combined": "Tworzy jedną paczkę zawierającą system oraz pełną pamięć.",
    "system": "Tworzy paczkę samego systemu, bez pamięci i workspace_runtime.",
    "memory": "Tworzy paczkę samej pełnej pamięci, z bezpiecznymi snapshotami SQLite.",
    "dual": "Tworzy dwie oddzielne paczki: system oraz pełną pamięć.",
}


def expected_plan_profiles(profile: str) -> frozenset[str]:
    if profile == "dual":
        return frozenset({"system", "memory"})
    if profile in {"combined", "system", "memory"}:
        return frozenset({profile})
    raise ValueError(f"unknown_package_profile:{profile}")


def _actual_profiles(plans: Sequence[Any]) -> frozenset[str]:
    return frozenset(str(getattr(plan, "profile", "")) for plan in plans)


def _has_real_memory_payload(plan: Any, memory_manifest: str) -> bool:
    manifest = PurePosixPath(memory_manifest).as_posix().casefold()
    for raw in getattr(plan, "paths", ()):
        path = PurePosixPath(str(raw).replace("\\", "/")).as_posix()
        lowered = path.casefold()
        if lowered.startswith("memory/") and lowered != manifest:
            return True
    return False


def require_exact_profile_set(core: Any, requested_profile: str, plans: Sequence[Any]) -> None:
    expected = expected_plan_profiles(requested_profile)
    actual = _actual_profiles(plans)
    if not plans or actual != expected:
        raise core.PackError(
            "Profil pakowania nie został zrealizowany w całości: "
            f"requested={requested_profile!r}, expected={sorted(expected)}, actual={sorted(actual)}"
        )
    if requested_profile == "combined":
        plan = plans[0]
        if not _has_real_memory_payload(plan, core.MEMORY_PACKAGE_MANIFEST):
            raise core.PackError(
                "Profil 'System i Pamięć (jedna paczka)' wymaga rzeczywistych plików pamięci. "
                "Nie wolno publikować paczki combined jako samego systemu."
            )


def _set_profile_choices_on_parser(parsed: Any) -> Any:
    for action in getattr(parsed, "_actions", []):
        choices = getattr(action, "choices", None)
        if not isinstance(choices, dict):
            continue
        for command in ("pack", "plan"):
            command_parser = choices.get(command)
            if command_parser is None:
                continue
            for command_action in getattr(command_parser, "_actions", []):
                if getattr(command_action, "dest", None) == "profile":
                    command_action.choices = USER_PROFILE_CHOICES
    return parsed


def apply(impl: Any) -> None:
    if getattr(impl, "_JAZN_V16311_PROFILE_POLICY_APPLIED", False):
        return
    core = getattr(impl, "_core", None)
    if core is None:
        raise RuntimeError("jazn_pack_generator_core_missing")

    original_parser = impl.parser
    original_build_plan = impl.build_plan
    original_run_pack_with_plans = impl.run_pack_with_plans
    original_verify_plans_current = core.verify_plans_current

    def parser() -> Any:
        return _set_profile_choices_on_parser(original_parser())

    def build_plan(
        root: Any,
        profile: str,
        custom_excludes: Sequence[str],
        *,
        base_excludes: Sequence[str] | None = None,
        manual_excludes_enabled: bool = True,
        synchronize_release_metadata: bool = False,
    ) -> Any:
        plan = original_build_plan(
            root,
            profile,
            custom_excludes,
            base_excludes=base_excludes,
            manual_excludes_enabled=manual_excludes_enabled,
            synchronize_release_metadata=synchronize_release_metadata,
        )
        if profile == "combined" and not _has_real_memory_payload(
            plan, core.MEMORY_PACKAGE_MANIFEST
        ):
            raise core.PackError(
                "Profil 'System i Pamięć (jedna paczka)' wymaga pełnej pamięci; "
                "katalog memory/ jest pusty, nieobecny albo wszystkie jego pliki zostały odrzucone."
            )
        return plan

    def build_plans_for_options(options: Any) -> list[Any]:
        source = options.source.expanduser().resolve()
        out_dir = options.out_dir.expanduser().resolve()
        core.ensure_output_outside_source(source, out_dir)
        # Resolve through the public implementation module at call time. This
        # preserves the established monkeypatch/extension seam while still
        # defaulting to the hardened build_plan installed below.
        plan_builder = getattr(impl, "build_plan", build_plan)
        if options.profile == "dual":
            plans = [
                plan_builder(
                    source,
                    "system",
                    options.custom_excludes,
                    base_excludes=options.base_excludes,
                    manual_excludes_enabled=options.manual_excludes_enabled,
                    synchronize_release_metadata=True,
                ),
                plan_builder(
                    source,
                    "memory",
                    options.custom_excludes,
                    base_excludes=options.base_excludes,
                    manual_excludes_enabled=options.manual_excludes_enabled,
                    synchronize_release_metadata=False,
                ),
            ]
        else:
            plans = [
                plan_builder(
                    source,
                    options.profile,
                    options.custom_excludes,
                    base_excludes=options.base_excludes,
                    manual_excludes_enabled=options.manual_excludes_enabled,
                    synchronize_release_metadata=(options.profile in {"system", "combined"}),
                )
            ]
        require_exact_profile_set(core, options.profile, plans)
        return plans

    def verify_plans_current(plans: Sequence[Any], options: Any) -> tuple[bool, str]:
        try:
            require_exact_profile_set(core, options.profile, plans)
        except (core.PackError, ValueError) as exc:
            return False, str(exc)
        return original_verify_plans_current(plans, options)

    def run_pack_with_plans(options: Any, plans: Sequence[Any]) -> list[Any]:
        require_exact_profile_set(core, options.profile, plans)
        return original_run_pack_with_plans(options, plans)

    core.GENERATOR_VERSION = GENERATOR_VERSION
    core.SETTINGS_SCHEMA = SETTINGS_SCHEMA
    core.PROFILE_CHOICES = USER_PROFILE_CHOICES
    core.PACK_PROFILE_CHOICES = USER_PROFILE_CHOICES
    core.PROFILE_DISPLAY = dict(PROFILE_DISPLAY)
    core.PROFILE_DESCRIPTIONS = dict(PROFILE_DESCRIPTIONS)
    core.parser = parser
    core.build_plan = build_plan
    core.build_plans_for_options = build_plans_for_options
    core.verify_plans_current = verify_plans_current
    core.run_pack_with_plans = run_pack_with_plans
    core.USER_PROFILE_CHOICES = USER_PROFILE_CHOICES

    impl.GENERATOR_VERSION = GENERATOR_VERSION
    impl.SETTINGS_SCHEMA = SETTINGS_SCHEMA
    impl.PROFILE_CHOICES = LEGACY_PROFILE_CHOICES
    impl.PACK_PROFILE_CHOICES = LEGACY_PACK_PROFILE_CHOICES
    impl.USER_PROFILE_CHOICES = USER_PROFILE_CHOICES
    impl.PROFILE_DISPLAY = dict(PROFILE_DISPLAY)
    impl.PROFILE_DESCRIPTIONS = dict(PROFILE_DESCRIPTIONS)
    impl.parser = parser
    impl.build_plan = build_plan
    impl.build_plans_for_options = build_plans_for_options
    impl.verify_plans_current = verify_plans_current
    impl.run_pack_with_plans = run_pack_with_plans
    impl.expected_plan_profiles = expected_plan_profiles
    impl.require_exact_profile_set = lambda requested, plans, _core=core: require_exact_profile_set(
        _core, requested, plans
    )
    impl._JAZN_V16311_PROFILE_POLICY_APPLIED = True


__all__ = [
    "GENERATOR_VERSION",
    "LEGACY_PACK_PROFILE_CHOICES",
    "LEGACY_PROFILE_CHOICES",
    "PROFILE_DESCRIPTIONS",
    "PROFILE_DISPLAY",
    "SETTINGS_SCHEMA",
    "USER_PROFILE_CHOICES",
    "apply",
    "expected_plan_profiles",
    "require_exact_profile_set",
]
