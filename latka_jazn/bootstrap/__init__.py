"""Bootstrap contract loading and embedded source fallback."""

# ChatGPT recovery predates the host-level optional-MEMORY boundary. Converge
# its public entrypoint once at package import so existing callers keep one
# canonical command while SYSTEM-only activation no longer depends on MEMORY.
from . import chatgpt_recovery as chatgpt_recovery
from .recovery_convergence import install as _install_recovery_convergence

_install_recovery_convergence(chatgpt_recovery)

del _install_recovery_convergence
