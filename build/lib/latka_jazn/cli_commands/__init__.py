"""Command implementations used by the canonical v16 run.py parser."""

# Keep the large historical diagnostics implementation import-compatible while
# converging its readiness semantics onto the current optional-MEMORY contract.
# Package initialization runs before ``latka_jazn.cli_commands.diagnostics`` is
# returned to direct importers, so legacy call sites receive the same corrected
# status_payload without a second command surface.
from . import diagnostics as diagnostics
from .diagnostics_convergence import install as _install_diagnostics_convergence

_install_diagnostics_convergence(diagnostics)

del _install_diagnostics_convergence
