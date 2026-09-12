#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

APP_NAME = "Jaźń - Studio testów"
APP_VERSION = "1.1.0"
VALID_REVIEW = {"current", "review_required", "obsolete", "incompatible"}


def find_root(explicit: str | None = None) -> Path:
    starts: list[Path] = []
    if explicit:
        starts.append(Path(explicit).expanduser().resolve())
    starts.extend([Path.cwd().resolve(), Path(__file__).resolve().parent])
    checked: list[str] = []
    for start in starts:
        for candidate in (start, *start.parents):
            marker = candidate / "tests"
            checked.append(str(candidate))
            if marker.is_dir() and (candidate / "pyproject.toml").is_file():
                return candidate
    raise SystemExit("Nie znaleziono katalogu repozytorium z tests/ i pyproject.toml. Sprawdzono: " + ", ".join(dict.fromkeys(checked)))


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


def run_pytest(root: Path, nodeids: list[str] | None = None, *, timeout: int = 1800) -> dict[str, Any]:
    cmd = [sys.executable, "-X", "utf8", "-m", "pytest", "-q"]
    if nodeids:
        cmd.extend(nodeids)
    else:
        cmd.extend(["tests", "--ignore=tests/archive"])
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=timeout, shell=False)
        output = (proc.stdout or "") + (proc.stderr or "")
        return {
            "ok": proc.returncode == 0,
            "outcome": "passed" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "command": cmd,
            "output": output[-250000:],
        }
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") if isinstance(exc.stdout, str) else "") + ((exc.stderr or "") if isinstance(exc.stderr, str) else "")
        return {"ok": False, "outcome": "timeout", "returncode": None, "duration_seconds": round(time.monotonic() - started, 3), "command": cmd, "output": output[-250000:]}


def filtered(root: Path, query: str = "", status: str = "all") -> list[tuple[str, dict[str, Any]]]:
    q = query.lower().strip()
    result: list[tuple[str, dict[str, Any]]] = []
    for nodeid in sorted(contracts(root)):
        item = effective_contract(root, nodeid)
        if status != "all" and item.get("status") != status:
            continue
        haystack = " ".join([nodeid, str(item.get("purpose", "")), str(item.get("category", "")), " ".join(item.get("tags", []))]).lower()
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
        by_status[item.get("status", "current")] = by_status.get(item.get("status", "current"), 0) + 1
        by_category[item.get("category", "unknown")] = by_category.get(item.get("category", "unknown"), 0) + 1
    return {
        "app": f"{APP_NAME} {APP_VERSION}",
        "root": str(root),
        "definitions": payload.get("active_definition_count", len(rows)),
        "manual_reviews": len(reviews),
        "by_status": by_status,
        "by_category": by_category,
    }


def set_review(root: Path, nodeid: str, status: str, purpose: str = "", expected: str = "", notes: str = "") -> None:
    if status not in VALID_REVIEW:
        raise SystemExit(f"Niepoprawny status: {status}")
    if nodeid not in contracts(root):
        raise SystemExit(f"Nieznany test: {nodeid}")
    payload = load_reviews(root)
    payload["reviews"][nodeid] = {"status": status, "purpose": purpose, "expected": expected, "notes": notes, "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    save_reviews(root, payload)


def print_home(root: Path) -> None:
    data = audit(root)
    print(f"{APP_NAME} {APP_VERSION}")
    print(f"Repo: {data['root']}")
    print(f"Aktywne definicje: {data['definitions']} | ręczne recenzje: {data['manual_reviews']}")
    print("Statusy:", data["by_status"])
    print("Kategorie:", data["by_category"])
    print("\nStatus current oznacza aktywny, technicznie zarejestrowany kontrakt. Nie jest sam w sobie dowodem, że cel biznesowy nigdy się nie zestarzeje.")


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
            print(json.dumps(audit(root), indent=2, ensure_ascii=False)); continue
        if raw == "run-all":
            print(json.dumps(run_pytest(root), indent=2, ensure_ascii=False)); continue
        if raw.startswith("list"):
            query = raw[4:].strip()
            for nodeid, item in filtered(root, query)[:200]:
                print(f"[{item.get('status','current')}] {nodeid} — {item.get('purpose','')}")
            continue
        if raw.startswith("show "):
            nodeid = raw[5:].strip()
            try: print(json.dumps(effective_contract(root, nodeid), indent=2, ensure_ascii=False))
            except KeyError: print("Nieznany nodeid")
            continue
        if raw.startswith("run "):
            nodeid = raw[4:].strip(); print(json.dumps(run_pytest(root, [nodeid]), indent=2, ensure_ascii=False)); continue
        if raw.startswith("review "):
            parts = raw.split(maxsplit=2)
            if len(parts) == 3:
                nodeid, status = parts[1], parts[2]; set_review(root, nodeid, status); print("Zapisano.")
            continue
        print("Nieznane polecenie.")


def tui(root: Path) -> None:
    while True:
        print("\n" + "=" * 78)
        print_home(root)
        print("\n1. Lista/szukaj  2. Szczegóły  3. Uruchom test  4. Uruchom wszystkie  5. Recenzja  0. Wyjście")
        choice = input("> ").strip()
        if choice == "0": return
        if choice == "1":
            q = input("Szukaj: ").strip()
            for nodeid, item in filtered(root, q)[:100]: print(f"[{item.get('status')}] {nodeid}\n  {item.get('purpose')}")
        elif choice == "2":
            nodeid = input("nodeid: ").strip()
            try: print(json.dumps(effective_contract(root, nodeid), indent=2, ensure_ascii=False))
            except KeyError: print("Nieznany nodeid")
        elif choice == "3":
            print(json.dumps(run_pytest(root, [input("nodeid: ").strip()]), indent=2, ensure_ascii=False))
        elif choice == "4":
            print(json.dumps(run_pytest(root), indent=2, ensure_ascii=False))
        elif choice == "5":
            nodeid = input("nodeid: ").strip(); status = input("current/review_required/obsolete/incompatible: ").strip(); notes = input("Notatka: ").strip(); set_review(root, nodeid, status, notes=notes); print("Zapisano.")


def studio_ui(root: Path) -> None:
    import tkinter as tk
    from tkinter import ttk, messagebox

    app = tk.Tk(); app.title(f"{APP_NAME} {APP_VERSION}"); app.geometry("1280x800"); app.minsize(1080, 680)
    style = ttk.Style(app)
    try: style.theme_use("vista" if sys.platform.startswith("win") else "clam")
    except tk.TclError: pass
    notebook = ttk.Notebook(app); notebook.pack(fill="both", expand=True, padx=10, pady=10)
    start = ttk.Frame(notebook); tests = ttk.Frame(notebook); expectations = ttk.Frame(notebook); results = ttk.Frame(notebook)
    notebook.add(start, text="Start"); notebook.add(tests, text="Testy"); notebook.add(expectations, text="Oczekiwania"); notebook.add(results, text="Wyniki")

    info = tk.Text(start, wrap="word", height=20); info.pack(fill="both", expand=True, padx=12, pady=12)
    info.insert("1.0", json.dumps(audit(root), indent=2, ensure_ascii=False) + "\n\ncurrent = aktywny kontrakt techniczny; sens może wymagać recenzji."); info.configure(state="disabled")

    top = ttk.Frame(tests); top.pack(fill="x", padx=8, pady=8)
    search_var = tk.StringVar(); status_var = tk.StringVar(value="all")
    ttk.Entry(top, textvariable=search_var, width=50).pack(side="left", padx=4)
    ttk.Combobox(top, textvariable=status_var, values=["all", *sorted(VALID_REVIEW)], state="readonly", width=18).pack(side="left", padx=4)
    tree = ttk.Treeview(tests, columns=("status", "category", "purpose"), show="tree headings")
    tree.heading("#0", text="Nodeid"); tree.heading("status", text="Status"); tree.heading("category", text="Kategoria"); tree.heading("purpose", text="Cel")
    tree.column("#0", width=470); tree.column("status", width=120); tree.column("category", width=100); tree.column("purpose", width=500)
    tree.pack(fill="both", expand=True, padx=8, pady=8)

    detail = tk.Text(expectations, wrap="word"); detail.pack(fill="both", expand=True, padx=8, pady=8)
    result_text = tk.Text(results, wrap="word"); result_text.pack(fill="both", expand=True, padx=8, pady=8)

    def selected() -> str | None:
        sel = tree.selection(); return sel[0] if sel else None
    def refresh(*_):
        for iid in tree.get_children(): tree.delete(iid)
        for nodeid, item in filtered(root, search_var.get(), status_var.get()):
            tree.insert("", "end", iid=nodeid, text=nodeid, values=(item.get("status"), item.get("category"), item.get("purpose")))
    def show_detail(*_):
        nodeid = selected()
        if not nodeid: return
        detail.delete("1.0", "end"); detail.insert("1.0", json.dumps(effective_contract(root, nodeid), indent=2, ensure_ascii=False)); notebook.select(expectations)
    def run_one():
        nodeid = selected()
        if not nodeid: return
        result = run_pytest(root, [nodeid]); result_text.delete("1.0", "end"); result_text.insert("1.0", json.dumps(result, indent=2, ensure_ascii=False)); notebook.select(results)
    def run_all():
        if not messagebox.askyesno(APP_NAME, "Uruchomić cały aktywny zestaw testów?"): return
        result = run_pytest(root); result_text.delete("1.0", "end"); result_text.insert("1.0", json.dumps(result, indent=2, ensure_ascii=False)); notebook.select(results)
    def review_dialog():
        nodeid = selected()
        if not nodeid: return
        win = tk.Toplevel(app); win.title("Recenzja kontraktu"); win.geometry("650x420")
        status = tk.StringVar(value=effective_contract(root, nodeid).get("status", "current")); purpose = tk.StringVar(value=effective_contract(root, nodeid).get("purpose", "")); expected = tk.StringVar(value=effective_contract(root, nodeid).get("expected", ""))
        ttk.Label(win, text=nodeid, wraplength=620).pack(anchor="w", padx=10, pady=8)
        ttk.Combobox(win, textvariable=status, values=sorted(VALID_REVIEW), state="readonly").pack(fill="x", padx=10, pady=4)
        ttk.Label(win, text="Purpose").pack(anchor="w", padx=10); ttk.Entry(win, textvariable=purpose).pack(fill="x", padx=10)
        ttk.Label(win, text="Expected").pack(anchor="w", padx=10); ttk.Entry(win, textvariable=expected).pack(fill="x", padx=10)
        notes = tk.Text(win, height=8); notes.pack(fill="both", expand=True, padx=10, pady=6)
        def save(): set_review(root, nodeid, status.get(), purpose.get(), expected.get(), notes.get("1.0", "end").strip()); win.destroy(); refresh()
        ttk.Button(win, text="Zapisz", command=save).pack(pady=8)

    buttons = ttk.Frame(tests); buttons.pack(fill="x", padx=8, pady=6)
    ttk.Button(buttons, text="Odśwież", command=refresh).pack(side="left", padx=4); ttk.Button(buttons, text="Szczegóły", command=show_detail).pack(side="left", padx=4); ttk.Button(buttons, text="Uruchom wybrany", command=run_one).pack(side="left", padx=4); ttk.Button(buttons, text="Recenzja", command=review_dialog).pack(side="left", padx=4); ttk.Button(buttons, text="Uruchom wszystkie", command=run_all).pack(side="right", padx=4)
    search_var.trace_add("write", refresh); status_var.trace_add("write", refresh); tree.bind("<Double-1>", show_detail); refresh(); app.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--root")
    parser.add_argument("--ui", choices=["text", "tui", "studio"])
    sub = parser.add_subparsers(dest="command")
    p_catalog = sub.add_parser("catalog"); p_catalog.add_argument("--filter", default=""); p_catalog.add_argument("--status", default="all"); p_catalog.add_argument("--limit", type=int, default=200); p_catalog.add_argument("--json", action="store_true")
    p_show = sub.add_parser("show"); p_show.add_argument("nodeid")
    p_run = sub.add_parser("run"); p_run.add_argument("nodeid"); p_run.add_argument("--timeout", type=int, default=1800)
    p_all = sub.add_parser("run-all"); p_all.add_argument("--timeout", type=int, default=1800)
    sub.add_parser("audit")
    p_review = sub.add_parser("review"); p_review.add_argument("nodeid"); p_review.add_argument("--status", required=True, choices=sorted(VALID_REVIEW)); p_review.add_argument("--purpose", default=""); p_review.add_argument("--expected", default=""); p_review.add_argument("--note", default="")
    args = parser.parse_args(); root = find_root(args.root)
    if args.command == "audit": print(json.dumps(audit(root), indent=2, ensure_ascii=False)); return 0
    if args.command == "catalog":
        rows = filtered(root, args.filter, args.status)[:args.limit]
        if args.json: print(json.dumps(dict(rows), indent=2, ensure_ascii=False))
        else:
            for nodeid, item in rows: print(f"[{item.get('status')}] {nodeid} — {item.get('purpose')}")
        return 0
    if args.command == "show": print(json.dumps(effective_contract(root, args.nodeid), indent=2, ensure_ascii=False)); return 0
    if args.command == "run": print(json.dumps(run_pytest(root, [args.nodeid], timeout=args.timeout), indent=2, ensure_ascii=False)); return 0
    if args.command == "run-all": print(json.dumps(run_pytest(root, timeout=args.timeout), indent=2, ensure_ascii=False)); return 0
    if args.command == "review": set_review(root, args.nodeid, args.status, args.purpose, args.expected, args.note); return 0
    ui = args.ui or ("studio" if sys.platform.startswith("win") else ("tui" if sys.stdin.isatty() else "text"))
    if ui == "studio": studio_ui(root)
    elif ui == "tui": tui(root)
    else: text_ui(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
