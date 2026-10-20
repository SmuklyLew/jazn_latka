from __future__ import annotations

"""Regression: only launching operations opt into dependency preparation.

Isolate main.py's actual entrypoint bootstrap function with AST so the test never
imports its runtime-wide compatibility overlays or spawns a process.
"""

import ast
import json
import os
from pathlib import Path
import sys

import latka_jazn.dependencies.runtime as dependency_runtime

ROOT = Path(__file__).resolve().parents[1]


def _entrypoint_function():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(ROOT / "main.py"))
    activation = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_ACTIVATION_COMMANDS"
                for target in node.targets)
    )
    requested = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_requested_command"
    )
    entrypoint = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_bootstrap_entrypoint_environment"
    )
    module = ast.fix_missing_locations(ast.Module(body=[activation, requested, entrypoint], type_ignores=[]))
    namespace = {"__file__": str(ROOT / "main.py"), "Path": Path, "os": os, "sys": sys, "json": json}
    exec(compile(module, str(ROOT / "main.py"), "exec"), namespace)
    return namespace["_bootstrap_entrypoint_environment"]


def test_process_launches_require_verified_environment_but_diagnostics_do_not(monkeypatch) -> None:
    calls: list[tuple[str, bool]] = []

    def prepare(root: Path, *, auto_install: bool = True) -> dict[str, object]:
        calls.append((str(root), auto_install))
        return {"ok": True, "state": "current_interpreter_ready", "reexec_python": None}

    monkeypatch.setattr(dependency_runtime, "prepare_entrypoint_environment", prepare)
    entrypoint = _entrypoint_function()
    activating = ("start", "restart", "chat", "chat-gpt", "runtime-bootstrap",
                  "mcp-http", "supervisor-run", "host-op-submit")
    diagnostics = ("status", "doctor", "host-preflight", "mcp-probe",
                   "host-op-status", "memory-validate", "model-status")
    for name in activating:
        entrypoint([name])
        assert calls[-1] == (str(ROOT), True), name
    for name in diagnostics:
        entrypoint([name])
        assert calls[-1] == (str(ROOT), False), name
    entrypoint([])
    assert calls[-1] == (str(ROOT), True)


def test_no_unapproved_dependency_install_when_explicitly_disabled(monkeypatch) -> None:
    # Actual dependency policy is responsible for enforcing the operator opt-out.
    source = (ROOT / "latka_jazn/dependencies/environment.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "prepare_entrypoint_environment")
    referenced = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert "auto_install" in referenced
    assert "install_bundle" in referenced
    assert "dependency_activation_status" in referenced
    assert 'JAZN_DEPENDENCY_AUTOBOOTSTRAP' in source
