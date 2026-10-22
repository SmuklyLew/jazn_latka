"""Launch external programs without inheriting frozen Qt library paths."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, cast

_SPAWN_LOCK = threading.RLock()


def environment() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    bundle = getattr(sys, "_MEIPASS", None)
    if not getattr(sys, "frozen", False) or not bundle:
        return env
    root = Path(bundle).resolve()
    for name in ("PATH", "DYLD_LIBRARY_PATH"):
        parts = env.get(name, "").split(os.pathsep)
        env[name] = os.pathsep.join(p for p in parts if p and not Path(p).resolve().is_relative_to(root))
    for name in ("LD_LIBRARY_PATH", "LIBPATH"):
        original = env.get(name + "_ORIG")
        if original is None:
            env.pop(name, None)
        else:
            env[name] = original
    for name in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(name, None)
    return env


def spawn(argv: list[str], *, cwd: Path, **kwargs: Any) -> subprocess.Popen[bytes]:
    env = kwargs.pop("env", None)
    env = environment() if env is None else env
    with _SPAWN_LOCK:
        bundle = getattr(sys, "_MEIPASS", None)
        reset = os.name == "nt" and getattr(sys, "frozen", False) and bundle
        api = None
        if reset and sys.platform == "win32":
            import ctypes
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
            api.SetDllDirectoryW.restype = ctypes.c_int
            if not api.SetDllDirectoryW(None):
                raise OSError("Cannot reset frozen DLL directory")
        try:
            return cast(subprocess.Popen[bytes], subprocess.Popen(argv, cwd=cwd, env=env, shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, **kwargs))
        finally:
            if api is not None:
                api.SetDllDirectoryW(str(bundle))


def run(argv: list[str], *, cwd: Path, timeout: float = 30, data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    proc = spawn(argv, cwd=cwd, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(data, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise
    return subprocess.CompletedProcess(argv, proc.returncode, out, err)
