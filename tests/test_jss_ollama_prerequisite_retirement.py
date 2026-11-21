"""Legacy JSS prerequisite commands may not install or spawn Ollama.

The Services controller owns deliberate local CLI lifecycle; first-run only
opens the official vendor URL and allows explicit model download.
"""
from __future__ import annotations

import pytest

from latka_jazn.tools import jss_prerequisite_setup as setup


def test_legacy_cli_ollama_install_never_invokes_winget_or_other_installer(monkeypatch) -> None:
    monkeypatch.setattr(setup.subprocess, "run",
                        lambda *_args, **_kw: pytest.fail("unexpected installer subprocess"))
    with pytest.raises(setup.ProvisioningError, match="ollama_use_official_installer"):
        setup.install_ollama_windows(approved=True)
    with pytest.raises(setup.ProvisioningError, match="explicit_operator_approval_required"):
        setup.install_ollama_windows(approved=False)


@pytest.mark.parametrize("launch", ["cli", "app"])
def test_legacy_cli_start_never_spawns_an_unowned_ollama_process(monkeypatch, launch: str) -> None:
    monkeypatch.setattr(setup.subprocess, "Popen",
                        lambda *_args, **_kw: pytest.fail("untracked process spawn"))
    with pytest.raises(setup.ProvisioningError, match="ollama_lifecycle_moved_to_jss_services"):
        setup.start_ollama(approved=True, launch=launch)
    with pytest.raises(setup.ProvisioningError, match="explicit_operator_approval_required"):
        setup.start_ollama(approved=False, launch=launch)
