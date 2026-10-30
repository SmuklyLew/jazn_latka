"""Local operator-owned pseudo-terminal, independent of the Jaźń daemon."""
from __future__ import annotations
import importlib
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
from typing import Any
from .core import SECRET_NAME, StudioError

def safe_env(root: Path, values: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ if values is None else values
    result = {k: v for k, v in env.items() if not SECRET_NAME.search(k)}
    result["JAZN_ROOT"] = str(root)
    return result

def shell_command() -> list[str]:
    if sys.platform == "win32":
        p = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if not p.is_file():
            raise StudioError("Brak systemowego PowerShell")
        return [str(p), "-NoLogo", "-NoProfile"]
    command = shutil.which("bash") or shutil.which("sh")
    if not command:
        raise StudioError("Brak lokalnej powłoki")
    return [command, "-i"]

class PtySession:
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        self.process: Any = None
        self.master: int | None = None
        self.queue: queue.Queue[str] = queue.Queue(maxsize=1000)
        self.done = False
        self.error = ""

    def start(self, rows: int = 30, cols: int = 100) -> None:
        if self.process is not None:
            raise StudioError("Sesja PTY już uruchomiona")
        if not (10 <= rows <= 200 and 20 <= cols <= 400):
            raise ValueError("Niepoprawne wymiary PTY")
        cmd = shell_command()
        if sys.platform == "win32":
            try:
                factory = getattr(importlib.import_module("winpty"), "PtyProcess")
            except (ImportError, AttributeError) as exc:
                raise StudioError("Opcjonalne pywinpty nie jest dostępne — bez automatycznej instalacji") from exc
            self.process = factory.spawn(cmd, cwd=str(self.root), env=safe_env(self.root), dimensions=(rows, cols))
        else:
            import pty
            self.master, slave = pty.openpty()
            try:
                self.process = subprocess.Popen(cmd, stdin=slave, stdout=slave, stderr=slave,
                                                cwd=self.root, env=safe_env(self.root), shell=False,
                                                close_fds=True, start_new_session=True)
            except BaseException:
                os.close(self.master)
                self.master = None
                raise
            finally:
                os.close(slave)
        threading.Thread(target=self._reader, name="jss-owned-pty", daemon=True).start()

    def _reader(self) -> None:
        try:
            while not self.done:
                if sys.platform == "win32":
                    value = self.process.read(4096)
                else:
                    assert self.master is not None
                    try:
                        value = os.read(self.master, 4096).decode("utf-8", "replace")
                    except OSError:
                        break
                if not value:
                    break
                try:
                    self.queue.put_nowait(str(value))
                except queue.Full:
                    self.error = "Przekroczono bufor wyjścia PTY"
                    break
        except (OSError, EOFError) as exc:
            self.error = type(exc).__name__
        finally:
            self.done = True

    def read_available(self) -> list[str]:
        chunks = []
        for _ in range(60):
            try:
                chunks.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return chunks

    def write(self, data: str) -> None:
        if self.process is None or self.done:
            raise StudioError("Brak aktywnej sesji PTY")
        if len(data) > 8192:
            raise ValueError("Za duże wejście")
        if sys.platform == "win32":
            self.process.write(data)
        else:
            assert self.master is not None
            os.write(self.master, data.encode("utf-8"))

    def close(self) -> None:
        self.done = True
        if self.process is None:
            return
        if sys.platform == "win32":
            self.process.close(force=False)
        elif self.process.poll() is None:
            self.process.terminate()
        if self.master is not None:
            os.close(self.master)
            self.master = None
