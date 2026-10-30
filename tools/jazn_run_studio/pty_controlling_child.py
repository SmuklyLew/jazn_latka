"""Tiny POSIX PTY child bootstrap executed after Popen(start_new_session=True).

Runs in a separate Python interpreter: no preexec_fn, fork from Qt threads or
duplicate runtime lifecycle. The PTY slave is already stdin/out/err.
"""
from __future__ import annotations

import os
import sys

if sys.platform != "win32":
    import fcntl
    import termios


def main() -> int:
    if sys.platform == "win32":
        raise RuntimeError("POSIX PTY bootstrap is unavailable on Windows")
    if len(sys.argv) < 2 or not os.isatty(0):
        raise RuntimeError("PTY slave and a shell are required")
    # Popen has already called setsid() in this fresh child process.
    # Acquire only the already attached slave as the controlling TTY.
    fcntl.ioctl(0, termios.TIOCSCTTY, 0)
    os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
