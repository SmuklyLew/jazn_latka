from __future__ import annotations
import argparse, json, subprocess, sys, urllib.request, urllib.error
from pathlib import Path
from typing import Any

MIN_PYTHON = (3, 12)

def _run(cmd: list[str], root: Path, timeout: float = 20.0) -> dict[str, Any]:
    try:
        cp = subprocess.run(cmd, cwd=str(root), text=True, encoding="utf-8",
                            errors="replace", capture_output=True, timeout=timeout)
        return {"started": True, "ok": cp.returncode == 0, "returncode": cp.returncode,
                "stdout": cp.stdout[-20000:], "stderr": cp.stderr[-20000:]}
    except FileNotFoundError as e:
        return {"started": False, "ok": False, "error": f"not_found: {e}"}
    except subprocess.TimeoutExpired:
        return {"started": True, "ok": False, "timeout": True}
    except Exception as e:
        return {"started": False, "ok": False, "error": f"{type(e).__name__}: {e}"}

def _ollama(base: str) -> dict[str, Any]:
    url = base.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2.5) as r:
            payload = json.loads(r.read(1024 * 1024).decode("utf-8"))
        models = []
        if isinstance(payload, dict):
            for item in payload.get("models", []):
                if isinstance(item, dict) and (item.get("name") or item.get("model")):
                    models.append(str(item.get("name") or item.get("model")))
        return {"ok": True, "url": url, "models": models}
    except Exception as e:
        return {"ok": False, "url": url, "error": f"{type(e).__name__}: {e}"}

def build_report(root: Path, *, ollama_base_url="http://127.0.0.1:11434",
                 run_diagnostics=True) -> dict[str, Any]:
    root = root.resolve()
    files = {
        "run_py": (root / "run.py").is_file(),
        "main_py": (root / "main.py").is_file(),
        "agents_md": (root / "AGENTS.md").is_file(),
        "version_py": (root / "latka_jazn/version.py").is_file(),
    }
    report: dict[str, Any] = {
        "schema_version": "jazn_local_runtime_preflight/v1",
        "root": str(root),
        "python": {"version": ".".join(map(str, sys.version_info[:3])),
                   "minimum": "3.12",
                   "ok": sys.version_info[:2] >= MIN_PYTHON},
        "files": files,
    }
    if (root / ".git").exists():
        head = _run(["git", "rev-parse", "HEAD"], root, 10)
        branch = _run(["git", "branch", "--show-current"], root, 10)
        dirty = _run(["git", "status", "--porcelain"], root, 10)
        report["git"] = {
            "is_repository": True,
            "head": head.get("stdout", "").strip() if head.get("ok") else None,
            "branch": branch.get("stdout", "").strip() if branch.get("ok") else None,
            "dirty": bool(dirty.get("stdout", "").strip()) if dirty.get("started") else None,
        }
    else:
        report["git"] = {"is_repository": False}

    if run_diagnostics and files["run_py"]:
        report["run_py"] = {
            "status": _run([sys.executable, "-X", "utf8", "run.py",
                            "status", "--snapshot", "--json"], root, 30),
            "doctor": _run([sys.executable, "-X", "utf8", "run.py",
                            "doctor", "--json"], root, 90),
        }
    else:
        report["run_py"] = {"skipped": True}

    report["ollama"] = _ollama(ollama_base_url)
    report["ok"] = bool(report["python"]["ok"] and all(files.values()))
    report["truth_boundary"] = (
        "preflight ok certifies only Python/canonical-file baseline. "
        "It does not certify a live daemon, writable memory, live Ollama, "
        "or a verified ChatGPT-host turn."
    )
    return report

def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=".")
    p.add_argument("--json", action="store_true")
    p.add_argument("--ollama-base-url", default="http://127.0.0.1:11434")
    p.add_argument("--skip-run-diagnostics", action="store_true")
    ns = p.parse_args(argv)
    r = build_report(Path(ns.root), ollama_base_url=ns.ollama_base_url,
                     run_diagnostics=not ns.skip_run_diagnostics)
    print(json.dumps(r, ensure_ascii=False, indent=2, sort_keys=True) if ns.json else
          f"preflight_ok={r['ok']} ollama_ok={r['ollama'].get('ok')}")
    return 0 if r["ok"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
