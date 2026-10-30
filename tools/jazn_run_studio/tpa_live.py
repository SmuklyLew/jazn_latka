"""Assisted acceptance client over canonical services, only in a fresh staging.

No lifecycle implementation lives here: Controller delegates start/status/stop
and restart to run.py/main.py; ChatClient owns the normal durable transport.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Protocol
import queue
import socket
import sys
import time
from uuid import uuid4

from .chat import ChatClient
from .core import Controller, Settings
from .external import run as run_external
from .probes import ollama
from .tpa_catalog import LIVE_CASES, TARGETS, scenario
from .tpa_reports import redact
from .tpa_reports import safe_child
from .tpa_paths import TOKEN_ENV, validate_staging


def frame(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False), flush=True)


def cleanup(folder: Path, python: str) -> dict:
    """Read-only identity observation before stopping only a run-owned staging."""
    owner = safe_child(folder, "owner.json")
    for name in ("SYSTEM", "runtime", "memory", "operator"):
        safe_child(folder, name)
    if not owner.exists():
        return {"ok": True, "reason": "daemon_not_started"}
    if not owner.is_file() or owner.stat().st_size > 4096:
        raise ValueError("Nieprawidłowy dowód własności testowego daemona")
    saved = json.loads(owner.read_text(encoding="utf-8"))
    stage = folder / "SYSTEM"
    if not isinstance(saved, dict) or saved.get("root") != str(stage.resolve()) or not stage.is_dir():
        raise ValueError("Niezgodny katalog właściciela daemona")
    os.environ.update(JAZN_RUNTIME_WORKSPACE_DIR=str(folder / "runtime"),
                      JAZN_MEMORY_ROOT=str(folder / "memory"), JAZN_MEMORY_MODE="off",
                      JAZN_OPERATOR_STATE_ROOT=str(folder / "operator"), JAZN_STUDIO_ACCEPTANCE_PROFILE="isolated")
    core = Controller(stage, Settings(python=python, daemon_url=saved["url"]))
    try:
        job = core.start_action("status")
        if not job.done.wait(45):
            return {"ok": False, "reason": "Nie zakończono weryfikacji tożsamości; odmowa zatrzymania."}
        observations = drain(core)
        evidence = next((v for _, kind, v in observations if kind == "evidence"), {})
        if evidence.get("active_state") in {"inactive", "stopped", "dead"} and not evidence.get("endpoint_reachable"):
            return {"ok": True, "reason": "own_daemon_inactive"}
        if not (evidence.get("root_matches") is True and evidence.get("process_identity_confirmed") is True
                and evidence.get("endpoint_identity_matches") is True
                and evidence.get("version_matches") is True and evidence.get("heartbeat_fresh") is True
                and isinstance(evidence.get("instance_id"), str) and bool(evidence["instance_id"])
                and isinstance(saved.get("instance_id"), str) and bool(saved["instance_id"])
                and evidence.get("instance_id") == saved["instance_id"]):
            return {"ok": False, "reason": "Nie potwierdzono własnej instancji; odmowa stop obcego daemona."}
        stopped = core.start_action("stop")
        return {"ok": stopped.done.wait(45) and stopped.state == "succeeded", "reason": stopped.error or "canonical_stop"}
    finally:
        core.close()


def drain(core: Controller) -> list[tuple]:
    events = []
    for channel in (core.critical_events, core.events):
        while True:
            try:
                events.append(channel.get_nowait())
            except queue.Empty:
                break
    return events


def capture_action(core: Controller, key: str, tick, records: list[dict]) -> dict:
    """Consume public events while the controller still owns its raw buffer.

    Controller deliberately clears Job.output before publishing completion.
    Retain redacted event evidence, never depend on that private buffer.
    """
    job = core.start_action(key)
    seen: list[tuple] = []

    def collect() -> None:
        for event in drain(core):
            seen.append(event)
            source, kind, value = event
            if source == job.key and kind == "log":
                frame({"event": "progress", "text": core.redactor.text(str(value))})

    while not job.done.wait(0.1):
        collect()
        tick()
    time.sleep(0.03)
    collect()
    raw = "\n".join(str(v) for source, kind, v in seen if source == job.key and kind == "log")
    try:
        diagnostic = redact(json.loads(raw), core.redactor)
    except ValueError:
        diagnostic = core.redactor.text(raw[-8000:])
    records.append({"action": key, "state": job.state, "exit_code": job.returncode, "observed": diagnostic})
    if job.state != "succeeded":
        raise ValueError("Kanoniczna operacja " + key + ": " + str(job.error)
                         + "; " + (core.redactor.text(raw[-1200:]) or "nie ustalono szczegółów; sprawdź log własnego daemona"))
    return next((v for _, kind, v in seen if kind == "evidence"), {})


class ReceiptCore(Protocol):
    @property
    def root(self) -> Path: ...


class ReceiptClient(Protocol):
    def resume_command(self, request_id: str, /) -> list[str]: ...


def await_daemon_receipt(core: ReceiptCore, client: ReceiptClient, request_id: str, tick, *, timeout_seconds: float = 45.0) -> dict:
    """Prove daemon-side admission before intentionally killing the transport.

    A flushed stdin pipe is not an acknowledgement that a request exists in the
    durable daemon job store. Poll only the original request_id; never replay
    the user's text. The read-only daemon-result command does not consume or
    acknowledge the final, which remains bound to the GUI's eventual ACK.
    """
    until = time.monotonic() + timeout_seconds
    attempts = 0
    while time.monotonic() < until:
        tick()
        attempts += 1
        try:
            probe = run_external(client.resume_command(request_id), cwd=core.root, timeout=12)
            response = json.loads(probe.stdout)
        except (OSError, ValueError, TimeoutError) as exc:
            raise ValueError("Nie można zweryfikować przyjęcia tury: " + type(exc).__name__) from exc
        if not isinstance(response, dict) or response.get("request_id") != request_id:
            raise ValueError("Odpowiedź daemona nie jest związana z request_id")
        if response.get("accepted") is True and response.get("job_status") in {
            "queued", "running", "awaiting_host_finalization", "completed",
        }:
            return {"request_id": request_id, "job_status": response["job_status"],
                    "confirmed": True, "probe_attempts": attempts}
        if response.get("error_code") != "chat_job_not_found":
            raise ValueError("Daemon odrzucił potwierdzenie tury: "
                             + str(response.get("error_code") or response.get("job_status") or "unexpected_result"))
        time.sleep(0.15)
    raise TimeoutError("Daemon nie potwierdził przyjęcia oryginalnego request_id")


def exercise(root: Path, folder: Path, case_id: str, python: str, model: str) -> dict:
    if case_id not in LIVE_CASES or folder.is_symlink() or any(folder.iterdir()):
        raise ValueError("Odbiór wymaga nowego własnego katalogu i znanego scenariusza")
    if model:
        try:
            present = ollama(model).get("selected_model_present") is True
        except OSError:
            return {"status": "BLOCKED", "reason": "Lokalna Ollama nie odpowiada. Uruchom usługę właściwym workflow Studio, sprawdź model i ponów odbiór; nie uruchomiono daemona testowego.",
                    "evidence": {"service_reachable": False, "cleanup": {"ok": True}, "turns": []}}
        if not present:
            return {"status": "BLOCKED", "reason": "Wybrany model nie jest dostępny w lokalnej Ollamie; nie pobrano modelu.",
                    "evidence": {"service_reachable": True, "selected_model_present": False, "cleanup": {"ok": True}, "turns": []}}
    elif case_id != "gui-daemon":
        return {"status": "BLOCKED", "reason": "Wybierz istniejący lokalny model Ollama do rzeczywistego odbioru rozmowy.", "evidence": {"turns": []}}
    from latka_jazn.tools.release_staging import create_system_smoke_staging
    stage = folder / "SYSTEM"
    frame({"event": "progress", "text": "Tworzę zweryfikowany staging SYSTEM; MEMORY pozostaje wyłączona."})
    create_system_smoke_staging(root, stage)
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]
    os.environ.update(JAZN_RUNTIME_WORKSPACE_DIR=str(folder / "runtime"), JAZN_MEMORY_ROOT=str(folder / "memory"),
                      JAZN_OPERATOR_STATE_ROOT=str(folder / "operator"), JAZN_MEMORY_MODE="off",
                      JAZN_STUDIO_ACCEPTANCE_PROFILE="isolated", JAZN_MODEL_ADAPTER="ollama" if model else "null",
                      JAZN_OLLAMA_MODEL=model, JAZN_OLLAMA_BASE_URL="http://127.0.0.1:11434")
    core = Controller(stage, Settings(python=python, model=model, daemon_url=f"http://127.0.0.1:{port}"))
    deadline = time.monotonic() + 420
    evidence: dict = {"case_id": case_id, "root": str(stage), "url": core.settings.daemon_url,
                      "turns": [], "memory_mode": "off", "canonical_transport": "Controller/ChatClient"}
    status = "BLOCKED"
    reason = "Nie zakończono odbioru."

    def tick() -> None:
        if (folder / "cancel.flag").exists():
            raise InterruptedError("Anulowano odbiór; zatrzymuję wyłącznie własne zasoby.")
        if time.monotonic() > deadline:
            raise TimeoutError("Przekroczono limit odbioru.")

    def action(key: str) -> dict:
        return capture_action(core, key, tick, evidence.setdefault("actions", []))

    def connected() -> ChatClient:
        client = ChatClient(core)
        core.chat = client
        client.connect()
        while client.job is None or client.job.proc is None:
            tick()
            if client.job is not None and client.job.done.is_set():
                raise ValueError("Nie uruchomiono kanonicznego transportu rozmowy")
            time.sleep(0.1)
        return client

    def disconnect(client: ChatClient) -> None:
        if client.job is not None and not client.job.done.is_set():
            core.stop_owned("chat")
            while not client.job.done.wait(0.1):
                tick()

    def final(client: ChatClient, *, resume: bool = False) -> dict:
        last_poll = 0.0
        while True:
            tick()
            if resume and time.monotonic() - last_poll > 1:
                pending_poll = core.jobs.get("chat:resume")
                if pending_poll is None or pending_poll.done.is_set():
                    client.resume()  # Same durable request, never resend text.
                    last_poll = time.monotonic()
            for source, kind, value in drain(core):
                if resume and source == "chat:resume" and kind == "state" and isinstance(value, dict):
                    if value.get("state") == "failed":
                        raise ValueError("Wznowienie request_id zakończyło się błędem: "
                                         + str(value.get("error") or "resume_failed"))
                if kind == "chat_final":
                    frame({"event": "accepted_final", **value})
                    ack = json.loads(sys.stdin.readline())
                    if ack.get("displayed_request_id") != value["request_id"]:
                        raise ValueError("Brak potwierdzenia wyświetlenia wyniku w panelu TPA")
                    client.acknowledge_final(value["request_id"])
                    core.confirm_visible_turn(value)
                    return value
            time.sleep(0.1)

    try:
        owned = {"root": str(stage.resolve()), "url": core.settings.daemon_url, "instance_id": None}
        (folder / "owner.json").write_text(json.dumps(owned), encoding="utf-8")
        action("start")
        observed = action("status")
        evidence["identity"] = observed
        owned = {"root": str(stage.resolve()), "url": core.settings.daemon_url,
                 "instance_id": observed.get("instance_id")}
        (folder / "owner.json").write_text(json.dumps(owned), encoding="utf-8")
        if not all(observed.get(k) is True for k in ("root_matches", "version_matches", "process_identity_confirmed", "endpoint_identity_matches", "heartbeat_fresh")):
            raise ValueError("Nie potwierdzono pełnej tożsamości testowego daemona.")
        if case_id == "gui-daemon":
            status = "PASS" if observed.get("conversation_ready") is True else "BLOCKED"
            reason = "Tożsamość i gotowość testowego daemona potwierdzone." if status == "PASS" else "Tożsamość potwierdzona, ale conversation_ready nie jest true; odbiór nie został zaliczony."
        else:
            client = connected()
            session_id = client.session_id
            code = "TPA" + uuid4().hex[:8].upper()
            request = client.send("Zapamiętaj na potrzeby tej testowej rozmowy kod " + code + ". Potwierdź krótko.")
            if case_id == "chat-resume":
                evidence["admission"] = await_daemon_receipt(core, client, request, tick)
                disconnect(client)
                value = final(client, resume=True)
                if value["request_id"] != request:
                    raise ValueError("Wznowiono inną turę")
                evidence["turns"].append(value)
            else:
                evidence["turns"].append(final(client))
                if case_id in {"chat-reconnect", "daemon-restart"}:
                    disconnect(client)
                    if case_id == "daemon-restart":
                        owned["instance_id"] = None
                        (folder / "owner.json").write_text(json.dumps(owned), encoding="utf-8")
                        action("restart")
                        next_identity = action("status")
                        if next_identity.get("instance_id") == observed.get("instance_id") or next_identity.get("root_matches") is not True:
                            raise ValueError("Restart nie dał nowej własnej instancji")
                        owned["instance_id"] = next_identity.get("instance_id")
                        (folder / "owner.json").write_text(json.dumps(owned), encoding="utf-8")
                        evidence["restarted_identity"] = next_identity
                    client = connected()
                if client.session_id != session_id:
                    raise ValueError("Sesja zmieniła się po ponownym połączeniu")
                client.send("Jaki kod podałem wcześniej w tej rozmowie? Podaj dokładnie sam kod.")
                second = final(client)
                evidence["turns"].append(second)
                if code not in second["text"]:
                    raise ValueError("Druga odpowiedź nie odtworzyła syntetycznego kodu; ciągłość niepotwierdzona.")
                for key in ("request_id", "turn_id", "trace_id"):
                    if len({v[key] for v in evidence["turns"]}) != 2:
                        raise ValueError("Nieprawidłowe rozdzielenie identyfikatorów tur")
            evidence["session_id"] = session_id
            status, reason = "PASS", "Rzeczywisty odbiór przez kanoniczny transport i walidator, z wyświetleniem oraz ACK w TPA."
    except InterruptedError as exc:
        status, reason = "CANCELLED", str(exc)
    except TimeoutError as exc:
        status, reason = "TIMEOUT", str(exc)
    except (OSError, ValueError, RuntimeError) as exc:
        reason = core.redactor.text(str(exc))[:1500]
        status = "FAIL" if evidence["turns"] else "BLOCKED"
    finally:
        core.close()
        for job in tuple(core.jobs.values()):
            if job.key == "chat":
                job.done.wait(5)
        try:
            clean = cleanup(folder, python)
        except (OSError, ValueError, RuntimeError) as exc:
            clean = {"ok": False, "reason": type(exc).__name__}
        evidence["cleanup"] = clean
        if not clean["ok"]:
            status = "BLOCKED"
            reason += " Nie potwierdzono sprzątnięcia własnego daemona: " + clean["reason"]
    return {"status": status, "reason": reason, "evidence": evidence}


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--folder", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--sandbox", action="store_true")
    args = parser.parse_args()
    try:
        folder = validate_staging(args.root, args.folder, args.run_id, args.case,
                                  os.environ.get(TOKEN_ENV, ""), cleaning=args.cleanup)
    except (OSError, ValueError) as exc:
        frame({"event": "result", "status": "BLOCKED", "reason": "Odmowa walidacji katalogu odbioru: " + str(exc),
               "pre_start_rejected": not args.cleanup,
               "evidence": {"cleanup": {"ok": not args.cleanup, "reason": "daemon_not_started" if not args.cleanup else "validation_rejected"}}})
        return 1
    if args.cleanup:
        result = cleanup(folder, sys.executable)
    elif args.sandbox:
        result = sandbox(args.root, folder, args.case, sys.executable, args.model)
    else:
        result = exercise(args.root, folder, args.case, sys.executable, args.model)
    frame({"event": "result", **result})
    # The cleanup contract reports {"ok": bool}, not {"status": "PASS"}.
    # Keep process exit codes aligned with their respective result schemas.
    if args.cleanup:
        return 0 if result.get("ok") is True else 1
    return 0 if result.get("status") == "PASS" else 1


def sandbox(root: Path, folder: Path, case_id: str, python: str, model: str) -> dict:
    """Open the actual Studio over a fresh synthetic project, then verify cleanup."""
    import subprocess
    from .core import save_settings
    from latka_jazn.tools.release_staging import create_system_smoke_staging
    scenario(case_id)
    if any(folder.iterdir()):
        raise ValueError("Obszar testowy musi być nowy")
    stage = folder / "SYSTEM"
    create_system_smoke_staging(root, stage)
    inputs = folder / "inputs"
    inputs.mkdir()
    (inputs / "source.txt").write_text("TPA SYNTHETIC SOURCE\nKod testowy: TPA-SYNTHETIC-2026. To dane fikcyjne do testów importu i pakowania.\n", encoding="utf-8")
    (inputs / "invalid.json").write_text('{"synthetic": invalid JSON', encoding="utf-8")
    (folder / "outputs").mkdir()
    instructions = "\n\n".join(scenario(case_id)["guide"])
    (folder / "PROCEDURA.txt").write_text(instructions + "\n\nŹródło: inputs/source.txt\nBłąd walidacji: inputs/invalid.json\nEksporty: outputs/\nProjekt i baseline utwórz publicznym workflow; nie kopiuj baz użytkownika.\n", encoding="utf-8")
    frame({"event": "progress", "text": "Obszar odbioru: " + str(folder) + "; procedura: PROCEDURA.txt, syntetyczne dane: inputs/, wyniki: outputs/."})
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    os.environ.update(JAZN_RUNTIME_WORKSPACE_DIR=str(folder / "runtime"), JAZN_MEMORY_ROOT=str(folder / "memory"),
                      JAZN_OPERATOR_STATE_ROOT=str(folder / "operator"), JAZN_MEMORY_MODE="off", JAZN_STUDIO_ACCEPTANCE_PROFILE="isolated")
    settings = Settings(python=python, model=model, daemon_url=f"http://127.0.0.1:{port}")
    save_settings(stage, settings, None)
    (folder / "owner.json").write_text(json.dumps({"root": str(stage.resolve()), "url": settings.daemon_url, "instance_id": None}), encoding="utf-8")
    section, studio = TARGETS.get(case_id, ("Pulpit", ""))
    env = dict(os.environ)
    env.update(JAZN_TPA_TARGET_SECTION=section, JAZN_TPA_TARGET_STUDIO=studio)
    # An explicit operator action opens a visible interactive window.
    env.pop("QT_QPA_PLATFORM", None)
    proc = subprocess.Popen([python, "-X", "utf8", str(stage / "run_studio.py"), "--root", str(stage)],
                            cwd=stage, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, shell=False,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    cancelled = False
    try:
        while proc.poll() is None:
            if (folder / "cancel.flag").exists():
                cancelled = True
                proc.terminate()
                try:
                    proc.wait(5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(5)
                break
            time.sleep(0.1)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)
        clean = cleanup(folder, python)
    return {"status": "CANCELLED" if cancelled else "PASS" if proc.returncode == 0 and clean["ok"] else "BLOCKED",
            "reason": "Otwarto i zamknięto rzeczywisty izolowany obszar Studio. Ocena przepływów wymaga checklisty i dowodów; nie jest to pełny odbiór.",
            "evidence": {"sandbox": True, "exit_code": proc.returncode, "cleanup": clean, "section": section, "studio": studio}}


if __name__ == "__main__":
    raise SystemExit(main())
