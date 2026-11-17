#!/usr/bin/env python3
"""Jaźń — Serce Systemu. Thin GUI entry; main.py owns the runtime."""
from __future__ import annotations

from pathlib import Path
import os
import sys


def main() -> int:
    from latka_jazn.dependencies.private_python import private_python_status

    root = Path(__file__).resolve().parent
    from latka_jazn.dependencies.environment_manager import (
        EnvironmentPolicyError, inspect_external_environment, load_environment_policy,
    )
    try:
        policy = load_environment_policy(root)
        if policy is not None:
            external = inspect_external_environment(root, policy)
            if not external["ready"]:
                print("Jaźń: external_environment_not_ready: " +
                      ", ".join(external["errors"]), file=sys.stderr)
                return 78
            if not external["current"]:
                if os.environ.get("JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE") == "1":
                    print("Jaźń: external_environment_handoff_not_established", file=sys.stderr)
                    return 78
                from latka_jazn.dependencies.process_handoff import handoff_to_managed_python
                return handoff_to_managed_python(
                    external["python_executable"],
                    [str(Path(__file__).resolve()), *sys.argv[1:]],
                    replace_process=True,
                )
            from tools.jazn_run_studio.dependency_preflight import dispatch
            return dispatch()
    except EnvironmentPolicyError as exc:
        print("Jaźń: environment_policy_invalid: " + str(exc), file=sys.stderr)
        return 78
    private = private_python_status(root)
    if private["present"] and not private["ready"]:
        print("Jaźń: private_python_invalid: " + str(private["state"]), file=sys.stderr)
        return 78
    if private["ready"] and not private["current"]:
        if os.environ.get("JAZN_DEPENDENCY_BOOTSTRAP_ACTIVE") == "1":
            print("Jaźń: private_python_handoff_not_established", file=sys.stderr)
            return 78
        from latka_jazn.dependencies.process_handoff import handoff_to_managed_python

        return handoff_to_managed_python(
            str(private["python_executable"]),
            [str(Path(__file__).resolve()), *sys.argv[1:]],
            replace_process=True,
        )
    from tools.jazn_run_studio.dependency_preflight import dispatch

    return dispatch()


if __name__ == "__main__":
    raise SystemExit(main())
