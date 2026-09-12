#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable

APP_NAME = "Jaźń - Studio testów"
APP_VERSION = "1.2.0"
VALID_REVIEW = {"current", "review_required", "obsolete", "incompatible"}
EVENT_MARKER = "JAZN_TEST_STUDIO_EVENT "
UI_STATUS = {
    "PASSED": "CORRECT",
    "FAILED": "FAIL",
    "ERROR": "ERROR",
    "SKIPPED": "SKIP",
    "XFAIL": "XFAIL",
    "XPASS": "XPASS",
}


def find_root(explicit: str | None = None) -> Path:
    starts: list[Path] = []
    if explicit:
        starts.append(Path(explicit).expanduser().resolve())
    starts.extend([Path.cwd().resolve(), Path(__file__).resolve().parent])
    checked: list[str] = []
    for start in starts:
        for candidate in (start, *start.parents):
            checked.append(str(candidate))
            if (candidate / "tests").is_dir() and (candidate / "pyproject.toml").is_file():
                return candidate
    raise SystemExit(
        "Nie znaleziono katalogu repozytorium z tests/ i pyproject.toml. Sprawdzono: "
        + ", ".join(dict.fromkeys(checked))
    )


def support_dir(root: Path) -> Path:
    return root / "tools" / "jazn_tests_studio"


def load_catalog(root: Path) -> dict[str, Any]:
    path = support_dir(root) / "test_contracts.json"
    if not path.is_file():
        raise SystemExit(f"Brak katalogu kontraktów: {path}. Uruchom migrator/test governance.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_reviews(root: Path) -> dict[str, Any]:
    path = support_dir(root) / "reviews.json"
    if not path.is_file():
        return {"schema": "jazn_tests_studio_reviews/v1", "reviews": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": "jazn_tests_studio_reviews/v1", "reviews": {}}
    payload.setdefault("reviews", {})
    return payload


def save_reviews(root: Path, payload: dict[str, Any]) -> None:
    path = support_dir(root) / "reviews.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def contracts(root: Path) -> dict[str, dict[str, Any]]:
    return dict(load_catalog(root).get("contracts", {}))


def effective_contract(root: Path, nodeid: str) -> dict[str, Any]:
    base = contracts(root).get(nodeid)
    if base is None:
        raise KeyError(nodeid)
    item = dict(base)
    review = load_reviews(root).get("reviews", {}).get(nodeid, {})
    if review:
        item["review"] = review
        item["status"] = review.get("status", item.get("status", "current"))
        for key in ("purpose", "expected", "notes"):
            if review.get(key):
                item[key] = review[key]
    return item


def filtered(root: Path, query: str = "", status: str = "all") -> list[tuple[str, dict[str, Any]]]:
    q = query.lower().strip()
    result: list[tuple[str, dict[str, Any]]] = []
    for nodeid in sorted(contracts(root)):
        item = effective_contract(root, nodeid)
        if status != "all" and item.get("status") != status:
            continue
        haystack = " ".join(
            [nodeid, str(item.get("purpose", "")), str(item.get("category", "")), " ".join(item.get("tags", []))]
        ).lower()
        if q and q not in haystack:
            continue
        result.append((nodeid, item))
    return result


def audit(root: Path) -> dict[str, Any]:
    payload = load_catalog(root)
    rows = filtered(root)
    reviews = load_reviews(root).get("reviews", {})
    by_status: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for _, item in rows:
        item_status = str(item.get("status", "current"))
        category = str(item.get("category", "unknown"))
        by_status[item_status] = by_status.get(item_status, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
    return {
        "app": f"{APP_NAME} {APP_VERSION}",
        "root": str(root),
        "definitions": payload.get("active_definition_count", len(rows)),
        "manual_reviews": len(reviews),
        "by_status": by_status,
        "by_category": by_category,
    }


def set_review(
    root: Path,
    nodeid: str,
    status: str,
    purpose: str = "",
    expected: str = "",
    notes: str = "",
) -> None:
    if status not in VALID_REVIEW:
        raise SystemExit(f"Niepoprawny status: {status}")
    if nodeid not in contracts(root):
        raise SystemExit(f"Nieznany test: {nodeid}")
    payload = load_reviews(root)
    payload["reviews"][nodeid] = {
        "status": status,
        "purpose": purpose,
        "expected": expected,
        "notes": notes,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_reviews(root, payload)


class PytestRun:
    """Run pytest in a worker thread and emit structured progress events."""

    def __init__(
        self,
        root: Path,
        nodeids: list[str] | None = None,
        *,
        timeout: int = 1800,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.root = root
        self.nodeids = nodeids or []
        self.timeout = max(1, int(timeout))
        self.on_event = on_event or (lambda event: None)
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None
        self.started = 0.0
        self.cancelled = False
        self.timed_out = False
        self.done = threading.Event()
        self.result: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._output: list[str] = []
        self._total = 0
        self._completed = 0
        self._counts = {key: 0 for key in ("PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL", "XPASS")}

    def command(self) -> list[str]:
        cmd = [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "pytest",
            "-q",
            "-p",
            "jazn_tests_studio.progress_plugin",
            "--tb=short",
            "-ra",
            "--color=no",
        ]
        if self.nodeids:
            cmd.extend(self.nodeids)
        else:
            cmd.extend(["tests", "--ignore=tests/archive"])
        return cmd

    def start(self) -> "PytestRun":
        if self.thread is not None:
            raise RuntimeError("run already started")
        self.thread = threading.Thread(target=self._worker, name="jazn-tests-studio-pytest", daemon=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        self.cancelled = True
        with self._lock:
            proc = self.process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                return

    def wait(self, timeout: float | None = None) -> dict[str, Any]:
        if not self.done.wait(timeout):
            raise TimeoutError("pytest run did not finish")
        assert self.result is not None
        return self.result

    def _emit(self, event: dict[str, Any]) -> None:
        try:
            self.on_event(event)
        except Exception:
            # UI/reporting failures must never kill the test process reader.
            pass

    def _parse_line(self, line: str) -> bool:
        marker_at = line.find(EVENT_MARKER)
        if marker_at < 0:
            return False
        raw = line[marker_at + len(EVENT_MARKER) :].strip()
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            return False
        kind = event.get("type")
        if kind == "collection":
            self._total = int(event.get("total") or 0)
        elif kind == "result":
            status = str(event.get("status") or "ERROR")
            self._completed += 1
            if status not in self._counts:
                status = "ERROR"
                event["status"] = status
            self._counts[status] += 1
            event["completed"] = self._completed
            event["total"] = self._total
            event["percent"] = round((self._completed / self._total * 100.0), 1) if self._total else 0.0
        self._emit(event)
        return True

    def _timeout_process(self) -> None:
        if self.done.is_set():
            return
        self.timed_out = True
        with self._lock:
            proc = self.process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _worker(self) -> None:
        self.started = time.monotonic()
        cmd = self.command()
        env = os.environ.copy()
        tools_path = str(self.root / "tools")
        previous = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = tools_path + (os.pathsep + previous if previous else "")
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        timer = threading.Timer(self.timeout, self._timeout_process)
        timer.daemon = True
        returncode: int | None = None
        launch_error: str | None = None
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                shell=False,
                creationflags=creationflags,
            )
            with self._lock:
                self.process = proc
            self._emit({"type": "process_start", "pid": proc.pid, "command": cmd})
            timer.start()
            assert proc.stdout is not None
            for line in proc.stdout:
                if not self._parse_line(line):
                    self._output.append(line)
                    if sum(map(len, self._output)) > 500_000:
                        self._output = self._output[-2500:]
                    self._emit({"type": "output", "text": line})
            returncode = proc.wait()
        except Exception as exc:
            launch_error = f"{type(exc).__name__}: {exc}"
            self._emit({"type": "output", "text": launch_error + "\n"})
        finally:
            timer.cancel()
            with self._lock:
                self.process = None

        duration = round(time.monotonic() - self.started, 3)
        if self.timed_out:
            outcome = "timeout"
        elif self.cancelled:
            outcome = "cancelled"
        elif launch_error is not None:
            outcome = "error"
        elif returncode == 0:
            outcome = "passed"
        elif returncode == 1:
            outcome = "failed"
        else:
            outcome = "error"
        self.result = {
            "ok": returncode == 0 and not self.timed_out and not self.cancelled,
            "outcome": outcome,
            "returncode": returncode,
            "duration_seconds": duration,
            "command": cmd,
            "total": self._total,
            "completed": self._completed,
            "counts": dict(self._counts),
            "output": "".join(self._output)[-250000:],
        }
        if launch_error:
            self.result["error"] = launch_error
        self._emit({"type": "finished", **self.result})
        self.done.set()


def run_pytest(
    root: Path,
    nodeids: list[str] | None = None,
    *,
    timeout: int = 1800,
    live: bool = False,
) -> dict[str, Any]:
    def console_event(event: dict[str, Any]) -> None:
        if not live:
            return
        kind = event.get("type")
        if kind == "collection":
            print(f"[COLLECTED] {event.get('total', 0)} testów", flush=True)
        elif kind == "start":
            print(f"[RUN] {event.get('nodeid', '')}", flush=True)
        elif kind == "result":
            status = UI_STATUS.get(str(event.get("status")), str(event.get("status")))
            print(
                f"[{status}] {event.get('nodeid', '')} "
                f"({event.get('completed', 0)}/{event.get('total', 0)}; {event.get('percent', 0)}%)",
                flush=True,
            )
        elif kind == "output":
            text = str(event.get("text") or "")
            if "FAILURES" in text or "ERRORS" in text or text.startswith("FAILED ") or text.startswith("ERROR "):
                print(text, end="", flush=True)

    run = PytestRun(root, nodeids, timeout=timeout, on_event=console_event).start()
    return run.wait(timeout + 30)


def print_home(root: Path) -> None:
    data = audit(root)
    print(f"{APP_NAME} {APP_VERSION}")
    print(f"Repo: {data['root']}")
    print(f"Aktywne definicje: {data['definitions']} | ręczne recenzje: {data['manual_reviews']}")
    print("Statusy:", data["by_status"])
    print("Kategorie:", data["by_category"])
    print("\nStatus current oznacza aktywny kontrakt techniczny; sens może wymagać recenzji.")


def text_ui(root: Path) -> None:
    print_home(root)
    print("\nPolecenia: list [tekst], show <nodeid>, run <nodeid>, run-all, audit, review <nodeid> <status>, quit")
    while True:
        try:
            raw = input("tests-studio> ").strip()
        except EOFError:
            return
        if not raw:
            continue
        if raw in {"quit", "exit", "q"}:
            return
        if raw == "audit":
            print(json.dumps(audit(root), indent=2, ensure_ascii=False))
            continue
        if raw == "run-all":
            print(json.dumps(run_pytest(root, live=True), indent=2, ensure_ascii=False))
            continue
        if raw.startswith("list"):
            query = raw[4:].strip()
            for nodeid, item in filtered(root, query)[:200]:
                print(f"[{item.get('status', 'current')}] {nodeid} — {item.get('purpose', '')}")
            continue
        if raw.startswith("show "):
            nodeid = raw[5:].strip()
            try:
                print(json.dumps(effective_contract(root, nodeid), indent=2, ensure_ascii=False))
            except KeyError:
                print("Nieznany nodeid")
            continue
        if raw.startswith("run "):
            nodeid = raw[4:].strip()
            print(json.dumps(run_pytest(root, [nodeid], live=True), indent=2, ensure_ascii=False))
            continue
        if raw.startswith("review "):
            parts = raw.split(maxsplit=2)
            if len(parts) == 3:
                set_review(root, parts[1], parts[2])
                print("Zapisano.")
            continue
        print("Nieznane polecenie.")


def tui(root: Path) -> None:
    while True:
        print("\n" + "=" * 78)
        print_home(root)
        print("\n1. Lista/szukaj  2. Szczegóły  3. Uruchom test  4. Uruchom wszystkie  5. Recenzja  0. Wyjście")
        choice = input("> ").strip()
        if choice == "0":
            return
        if choice == "1":
            q = input("Szukaj: ").strip()
            for nodeid, item in filtered(root, q)[:100]:
                print(f"[{item.get('status')}] {nodeid}\n  {item.get('purpose')}")
        elif choice == "2":
            nodeid = input("nodeid: ").strip()
            try:
                print(json.dumps(effective_contract(root, nodeid), indent=2, ensure_ascii=False))
            except KeyError:
                print("Nieznany nodeid")
        elif choice == "3":
            print(json.dumps(run_pytest(root, [input("nodeid: ").strip()], live=True), indent=2, ensure_ascii=False))
        elif choice == "4":
            print(json.dumps(run_pytest(root, live=True), indent=2, ensure_ascii=False))
        elif choice == "5":
            nodeid = input("nodeid: ").strip()
            status = input("current/review_required/obsolete/incompatible: ").strip()
            notes = input("Notatka: ").strip()
            set_review(root, nodeid, status, notes=notes)
            print("Zapisano.")


def studio_ui(root: Path) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    app = tk.Tk()
    app.title(f"{APP_NAME} {APP_VERSION}")
    app.geometry("1320x860")
    app.minsize(1080, 680)
    style = ttk.Style(app)
    try:
        style.theme_use("vista" if sys.platform.startswith("win") else "clam")
    except tk.TclError:
        pass

    notebook = ttk.Notebook(app)
    notebook.pack(fill="both", expand=True, padx=10, pady=10)
    start = ttk.Frame(notebook)
    tests = ttk.Frame(notebook)
    expectations = ttk.Frame(notebook)
    results = ttk.Frame(notebook)
    notebook.add(start, text="Start")
    notebook.add(tests, text="Testy")
    notebook.add(expectations, text="Oczekiwania")
    notebook.add(results, text="Wyniki")

    def text_with_scrollbars(parent, *, wrap: str = "none"):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        widget = tk.Text(frame, wrap=wrap)
        ybar = ttk.Scrollbar(frame, orient="vertical", command=widget.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=widget.xview)
        widget.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        widget.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        return widget

    info = text_with_scrollbars(start, wrap="word")
    info.insert(
        "1.0",
        json.dumps(audit(root), indent=2, ensure_ascii=False)
        + "\n\ncurrent = aktywny kontrakt techniczny; sens może wymagać recenzji.\n"
        + "Run-all działa w osobnym wątku i pokazuje bieżący test oraz wynik na żywo.",
    )
    info.configure(state="disabled")

    tests.rowconfigure(1, weight=1)
    tests.columnconfigure(0, weight=1)
    top = ttk.Frame(tests)
    top.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
    search_var = tk.StringVar()
    status_var = tk.StringVar(value="all")
    ttk.Label(top, text="Szukaj:").pack(side="left", padx=(0, 4))
    ttk.Entry(top, textvariable=search_var, width=48).pack(side="left", padx=4)
    ttk.Label(top, text="Status:").pack(side="left", padx=(12, 4))
    ttk.Combobox(
        top,
        textvariable=status_var,
        values=["all", *sorted(VALID_REVIEW)],
        state="readonly",
        width=18,
    ).pack(side="left", padx=4)

    tree_frame = ttk.Frame(tests)
    tree_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
    tree_frame.rowconfigure(0, weight=1)
    tree_frame.columnconfigure(0, weight=1)
    tree = ttk.Treeview(tree_frame, columns=("status", "category", "purpose"), show="tree headings")
    tree.heading("#0", text="Nodeid")
    tree.heading("status", text="Status")
    tree.heading("category", text="Kategoria")
    tree.heading("purpose", text="Cel")
    tree.column("#0", width=500, minwidth=250)
    tree.column("status", width=120, minwidth=90)
    tree.column("category", width=120, minwidth=90)
    tree.column("purpose", width=620, minwidth=300)
    tree_y = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=tree_y.set, xscrollcommand=tree_x.set)
    tree.grid(row=0, column=0, sticky="nsew")
    tree_y.grid(row=0, column=1, sticky="ns")
    tree_x.grid(row=1, column=0, sticky="ew")

    buttons = ttk.Frame(tests)
    buttons.grid(row=2, column=0, sticky="ew", padx=8, pady=8)

    detail = text_with_scrollbars(expectations, wrap="none")

    results.rowconfigure(2, weight=1)
    results.columnconfigure(0, weight=1)
    summary = ttk.Frame(results)
    summary.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
    run_state_var = tk.StringVar(value="GOTOWE")
    current_var = tk.StringVar(value="—")
    progress_text_var = tk.StringVar(value="0 / 0 (0%)")
    ttk.Label(summary, text="Stan:").grid(row=0, column=0, sticky="w")
    ttk.Label(summary, textvariable=run_state_var).grid(row=0, column=1, sticky="w", padx=(4, 18))
    ttk.Label(summary, text="Bieżący test:").grid(row=0, column=2, sticky="w")
    ttk.Label(summary, textvariable=current_var).grid(row=0, column=3, sticky="ew", padx=4)
    summary.columnconfigure(3, weight=1)
    ttk.Label(summary, textvariable=progress_text_var).grid(row=0, column=4, sticky="e")

    progress = ttk.Progressbar(results, orient="horizontal", mode="determinate", maximum=1)
    progress.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

    result_pane = ttk.Panedwindow(results, orient="vertical")
    result_pane.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
    status_frame = ttk.Frame(result_pane)
    log_frame = ttk.Frame(result_pane)
    result_pane.add(status_frame, weight=3)
    result_pane.add(log_frame, weight=2)

    status_frame.rowconfigure(1, weight=1)
    status_frame.columnconfigure(0, weight=1)
    counters_frame = ttk.Frame(status_frame)
    counters_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    counter_vars = {name: tk.StringVar(value="0") for name in ("CORRECT", "FAIL", "ERROR", "SKIP", "XFAIL", "XPASS")}
    for col, name in enumerate(counter_vars):
        ttk.Label(counters_frame, text=f"{name}:").grid(row=0, column=col * 2, padx=(0, 3))
        ttk.Label(counters_frame, textvariable=counter_vars[name]).grid(row=0, column=col * 2 + 1, padx=(0, 14))

    status_tree = ttk.Treeview(status_frame, columns=("status", "duration", "nodeid"), show="headings")
    status_tree.heading("status", text="Wynik")
    status_tree.heading("duration", text="Czas [s]")
    status_tree.heading("nodeid", text="Test")
    status_tree.column("status", width=100, minwidth=80)
    status_tree.column("duration", width=95, minwidth=75)
    status_tree.column("nodeid", width=980, minwidth=420)
    status_y = ttk.Scrollbar(status_frame, orient="vertical", command=status_tree.yview)
    status_x = ttk.Scrollbar(status_frame, orient="horizontal", command=status_tree.xview)
    status_tree.configure(yscrollcommand=status_y.set, xscrollcommand=status_x.set)
    status_tree.grid(row=1, column=0, sticky="nsew")
    status_y.grid(row=1, column=1, sticky="ns")
    status_x.grid(row=2, column=0, sticky="ew")

    log_frame.rowconfigure(0, weight=1)
    log_frame.columnconfigure(0, weight=1)
    result_text = tk.Text(log_frame, wrap="none")
    log_y = ttk.Scrollbar(log_frame, orient="vertical", command=result_text.yview)
    log_x = ttk.Scrollbar(log_frame, orient="horizontal", command=result_text.xview)
    result_text.configure(yscrollcommand=log_y.set, xscrollcommand=log_x.set)
    result_text.grid(row=0, column=0, sticky="nsew")
    log_y.grid(row=0, column=1, sticky="ns")
    log_x.grid(row=1, column=0, sticky="ew")

    result_buttons = ttk.Frame(results)
    result_buttons.grid(row=3, column=0, sticky="ew", padx=8, pady=8)
    stop_button = ttk.Button(result_buttons, text="Zatrzymaj", state="disabled")
    stop_button.pack(side="left", padx=4)
    ttk.Button(
        result_buttons,
        text="Wyczyść wyniki",
        command=lambda: (status_tree.delete(*status_tree.get_children()), result_text.delete("1.0", "end")),
    ).pack(side="left", padx=4)

    event_queue: queue.Queue[dict[str, Any]] = queue.Queue()
    active_run: PytestRun | None = None
    totals = {"total": 0, "completed": 0}
    counts = {key: 0 for key in counter_vars}

    def selected() -> str | None:
        sel = tree.selection()
        return sel[0] if sel else None

    def refresh(*_args) -> None:
        for iid in tree.get_children():
            tree.delete(iid)
        for nodeid, item in filtered(root, search_var.get(), status_var.get()):
            tree.insert(
                "",
                "end",
                iid=nodeid,
                text=nodeid,
                values=(item.get("status"), item.get("category"), item.get("purpose")),
            )

    def show_detail(*_args) -> None:
        nodeid = selected()
        if not nodeid:
            return
        detail.delete("1.0", "end")
        detail.insert("1.0", json.dumps(effective_contract(root, nodeid), indent=2, ensure_ascii=False))
        notebook.select(expectations)

    def append_log(text: str) -> None:
        if not text:
            return
        result_text.insert("end", text)
        result_text.see("end")

    def reset_run_view() -> None:
        nonlocal totals, counts
        status_tree.delete(*status_tree.get_children())
        result_text.delete("1.0", "end")
        totals = {"total": 0, "completed": 0}
        counts = {key: 0 for key in counter_vars}
        for name, var in counter_vars.items():
            var.set("0")
        progress.configure(maximum=1, value=0)
        progress_text_var.set("0 / 0 (0%)")
        current_var.set("—")

    def set_running_controls(running: bool) -> None:
        state = "disabled" if running else "normal"
        run_one_button.configure(state=state)
        run_all_button.configure(state=state)
        stop_button.configure(state="normal" if running else "disabled")

    def handle_event(event: dict[str, Any]) -> None:
        nonlocal active_run
        kind = event.get("type")
        if kind == "process_start":
            run_state_var.set("RUNNING")
            append_log("START: " + " ".join(event.get("command", [])) + "\n")
        elif kind == "collection":
            totals["total"] = int(event.get("total") or 0)
            progress.configure(maximum=max(1, totals["total"]))
            progress_text_var.set(f"0 / {totals['total']} (0%)")
        elif kind == "start":
            current_var.set(str(event.get("nodeid") or "—"))
        elif kind == "result":
            totals["completed"] = int(event.get("completed") or totals["completed"] + 1)
            totals["total"] = int(event.get("total") or totals["total"])
            raw_status = str(event.get("status") or "ERROR")
            shown = UI_STATUS.get(raw_status, raw_status)
            if shown not in counts:
                shown = "ERROR"
            counts[shown] += 1
            counter_vars[shown].set(str(counts[shown]))
            percent = float(event.get("percent") or 0.0)
            progress.configure(maximum=max(1, totals["total"]), value=totals["completed"])
            progress_text_var.set(f"{totals['completed']} / {totals['total']} ({percent:.1f}%)")
            iid = f"{totals['completed']:06d}"
            status_tree.insert(
                "",
                "end",
                iid=iid,
                values=(shown, f"{float(event.get('duration') or 0.0):.3f}", event.get("nodeid", "")),
            )
            status_tree.see(iid)
        elif kind == "output":
            append_log(str(event.get("text") or ""))
        elif kind == "finished":
            outcome = str(event.get("outcome") or "error")
            if outcome == "passed":
                run_state_var.set("CORRECT")
            elif outcome == "failed":
                run_state_var.set("FAIL")
            elif outcome == "cancelled":
                run_state_var.set("CANCELLED")
            elif outcome == "timeout":
                run_state_var.set("TIMEOUT")
            else:
                run_state_var.set("ERROR")
            current_var.set("—")
            append_log("\nFINAL:\n" + json.dumps(event, indent=2, ensure_ascii=False) + "\n")
            set_running_controls(False)
            active_run = None

    def poll_events() -> None:
        drained = False
        while True:
            try:
                event = event_queue.get_nowait()
            except queue.Empty:
                break
            drained = True
            handle_event(event)
        if active_run is not None or drained:
            app.after(50, poll_events)

    def start_run(nodeids: list[str] | None) -> None:
        nonlocal active_run
        if active_run is not None:
            messagebox.showinfo(APP_NAME, "Testy już są uruchomione.")
            return
        reset_run_view()
        notebook.select(results)
        run_state_var.set("STARTING")
        set_running_controls(True)
        active_run = PytestRun(root, nodeids, timeout=1800, on_event=event_queue.put).start()
        app.after(25, poll_events)

    def run_one() -> None:
        nodeid = selected()
        if nodeid:
            start_run([nodeid])

    def run_all() -> None:
        if messagebox.askyesno(APP_NAME, "Uruchomić cały aktywny zestaw testów?"):
            start_run(None)

    def stop_run() -> None:
        if active_run is not None and messagebox.askyesno(APP_NAME, "Zatrzymać bieżący przebieg testów?"):
            run_state_var.set("STOPPING")
            active_run.stop()

    stop_button.configure(command=stop_run)

    def review_dialog() -> None:
        nodeid = selected()
        if not nodeid:
            return
        item = effective_contract(root, nodeid)
        win = tk.Toplevel(app)
        win.title("Recenzja kontraktu")
        win.geometry("720x500")
        status = tk.StringVar(value=item.get("status", "current"))
        purpose = tk.StringVar(value=item.get("purpose", ""))
        expected = tk.StringVar(value=item.get("expected", ""))
        ttk.Label(win, text=nodeid, wraplength=680).pack(anchor="w", padx=10, pady=8)
        ttk.Combobox(win, textvariable=status, values=sorted(VALID_REVIEW), state="readonly").pack(fill="x", padx=10, pady=4)
        ttk.Label(win, text="Purpose").pack(anchor="w", padx=10)
        ttk.Entry(win, textvariable=purpose).pack(fill="x", padx=10)
        ttk.Label(win, text="Expected").pack(anchor="w", padx=10)
        ttk.Entry(win, textvariable=expected).pack(fill="x", padx=10)
        notes_frame = ttk.Frame(win)
        notes_frame.pack(fill="both", expand=True, padx=10, pady=6)
        notes_frame.rowconfigure(0, weight=1)
        notes_frame.columnconfigure(0, weight=1)
        notes = tk.Text(notes_frame, wrap="word")
        notes_y = ttk.Scrollbar(notes_frame, orient="vertical", command=notes.yview)
        notes.configure(yscrollcommand=notes_y.set)
        notes.grid(row=0, column=0, sticky="nsew")
        notes_y.grid(row=0, column=1, sticky="ns")
        notes.insert("1.0", str(item.get("notes") or ""))

        def save() -> None:
            set_review(
                root,
                nodeid,
                status.get(),
                purpose.get(),
                expected.get(),
                notes.get("1.0", "end").strip(),
            )
            win.destroy()
            refresh()

        ttk.Button(win, text="Zapisz", command=save).pack(pady=8)

    ttk.Button(buttons, text="Odśwież", command=refresh).pack(side="left", padx=4)
    ttk.Button(buttons, text="Szczegóły", command=show_detail).pack(side="left", padx=4)
    run_one_button = ttk.Button(buttons, text="Uruchom wybrany", command=run_one)
    run_one_button.pack(side="left", padx=4)
    ttk.Button(buttons, text="Recenzja", command=review_dialog).pack(side="left", padx=4)
    run_all_button = ttk.Button(buttons, text="Uruchom wszystkie", command=run_all)
    run_all_button.pack(side="right", padx=4)

    search_var.trace_add("write", refresh)
    status_var.trace_add("write", refresh)
    tree.bind("<Double-1>", show_detail)
    refresh()
    app.mainloop()


def self_test() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="jazn-tests-studio-") as td:
        root = Path(td)
        (root / "tests").mkdir()
        (root / "tools" / "jazn_tests_studio").mkdir(parents=True)
        (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        plugin_source = Path(__file__).resolve().parent / "jazn_tests_studio" / "progress_plugin.py"
        if not plugin_source.is_file():
            # Running as tools/jazn_tests_studio.py in a checkout.
            plugin_source = support_dir(find_root()) / "progress_plugin.py"
        (root / "tools" / "jazn_tests_studio" / "__init__.py").write_text("", encoding="utf-8")
        (root / "tools" / "jazn_tests_studio" / "progress_plugin.py").write_text(
            plugin_source.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (root / "tests" / "test_demo.py").write_text(
            "def test_ok():\n    assert True\n\ndef test_skip():\n    import pytest\n    pytest.skip('demo')\n",
            encoding="utf-8",
        )
        events: list[dict[str, Any]] = []
        result = PytestRun(root, timeout=60, on_event=events.append).start().wait(90)
        types = {str(event.get("type")) for event in events}
        statuses = {str(event.get("status")) for event in events if event.get("type") == "result"}
        ok = result["ok"] and {"collection", "start", "result", "finished"}.issubset(types) and "PASSED" in statuses and "SKIPPED" in statuses
        return {"ok": ok, "result": result, "event_types": sorted(types), "statuses": sorted(statuses)}


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--root")
    parser.add_argument("--ui", choices=["text", "tui", "studio"])
    sub = parser.add_subparsers(dest="command")
    p_catalog = sub.add_parser("catalog")
    p_catalog.add_argument("--filter", default="")
    p_catalog.add_argument("--status", default="all")
    p_catalog.add_argument("--limit", type=int, default=200)
    p_catalog.add_argument("--json", action="store_true")
    p_show = sub.add_parser("show")
    p_show.add_argument("nodeid")
    p_run = sub.add_parser("run")
    p_run.add_argument("nodeid")
    p_run.add_argument("--timeout", type=int, default=1800)
    p_all = sub.add_parser("run-all")
    p_all.add_argument("--timeout", type=int, default=1800)
    sub.add_parser("audit")
    sub.add_parser("self-test")
    p_review = sub.add_parser("review")
    p_review.add_argument("nodeid")
    p_review.add_argument("--status", required=True, choices=sorted(VALID_REVIEW))
    p_review.add_argument("--purpose", default="")
    p_review.add_argument("--expected", default="")
    p_review.add_argument("--note", default="")
    args = parser.parse_args()

    if args.command == "self-test":
        payload = self_test()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload["ok"] else 1

    root = find_root(args.root)
    if args.command == "audit":
        print(json.dumps(audit(root), indent=2, ensure_ascii=False))
        return 0
    if args.command == "catalog":
        rows = filtered(root, args.filter, args.status)[: args.limit]
        if args.json:
            print(json.dumps(dict(rows), indent=2, ensure_ascii=False))
        else:
            for nodeid, item in rows:
                print(f"[{item.get('status')}] {nodeid} — {item.get('purpose')}")
        return 0
    if args.command == "show":
        print(json.dumps(effective_contract(root, args.nodeid), indent=2, ensure_ascii=False))
        return 0
    if args.command == "run":
        print(json.dumps(run_pytest(root, [args.nodeid], timeout=args.timeout, live=True), indent=2, ensure_ascii=False))
        return 0
    if args.command == "run-all":
        result = run_pytest(root, timeout=args.timeout, live=True)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1
    if args.command == "review":
        set_review(root, args.nodeid, args.status, args.purpose, args.expected, args.note)
        return 0

    ui = args.ui or ("studio" if sys.platform.startswith("win") else ("tui" if sys.stdin.isatty() else "text"))
    if ui == "studio":
        studio_ui(root)
    elif ui == "tui":
        tui(root)
    else:
        text_ui(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
