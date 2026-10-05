# Jaźń — CURRENT STEP

**Status:** `CANONICAL_CURRENT_STEP`  
**Stan:** 2026-10-05  
**Baza:** `master @ bb107ebaeea119487f49d8cb1e34efd9a1896464` / `16.3.25.5.106-memory-streaming-hardening-convergence`  
**Branch:** `upgrade/v16.3.25.5.107-persistent-remote-runtime-operations-convergence`  
**Target:** `16.3.25.5.107-persistent-remote-runtime-operations-convergence`

## 1. Bieżący krok — persistent remote runtime operations

Najwyższy priorytet to usunięcie zależności ciągłości rozmowy od efemerycznej
powierzchni process execution pojedynczej wiadomości ChatGPT. Kod remote MCP,
daemon, supervisor, durable request lineage i accepted-visible-turn już istnieją;
bieżący krok domyka ich produkcyjne uruchomienie i kontrakty.

```text
ChatGPT current-message app capability
        |
        | authenticated HTTPS MCP 2026-07-28
        v
public gateway / outbound tunnel
        |
        v
one persistent Jaźń daemon
        ^
        |
canonical runtime supervisor
```

Lokalny executor ChatGPT pozostaje bootstrap/recovery capability. Nie jest
warunkiem utrzymania rozmowy po zweryfikowaniu zdalnej trasy.

## 2. Zakres v107

- strict production readiness from canonical nested status evidence;
- supervisor required by default, verified reuse, bounded start and fail-closed
  timeout;
- separate liveness `/healthz` from readiness `/readyz`;
- versioned public deployment contract with real MCP method names;
- public HTTPS deployment examples for container/systemd/outbound Cloudflare
  Tunnel without repository-held secrets;
- exact-set MEMORY manifest producer gate before archive/transport creation;
- ChatGPT runbook rule: verified remote runtime owns ordinary-turn continuity;
- Windows/Linux regression coverage and release metadata sync;
- rollback and chaos/failure-injection runbook.

## 3. Exit gate v107

```text
canonical runtime status shape used        PASS required
strict conversation readiness              PASS required
exact runtime/daemon version binding       PASS required
supervisor identity + heartbeat lease      PASS required
daemon kill -> supervisor recovery         PASS required
tunnel loss does not kill local runtime    deployment test required
ambiguous transport never replays message  PASS required
MCP 2026-07-28 wire names preserved        PASS required
MEMORY exact-set producer verification     PASS required
OAuth/secrets/loopback boundaries          PASS required
Linux + Windows persistent-runtime CI      PASS required
Pyright + release-hardening                PASS required
canonical manifest/provenance sync         PASS required
real ChatGPT app acceptance                external evidence required
```

A green repository candidate proves implementation readiness, not that a
particular ChatGPT conversation currently has the Jaźń app callable.

## 4. Następny krok

Po merge-ready v107:

1. deploy one reviewed build behind a stable HTTPS hostname;
2. verify OAuth, `/healthz`, `/readyz` and supervisor recovery;
3. connect/select the Jaźń custom MCP app in ChatGPT;
4. verify fresh-message `jazn_status` + full four-tool callable set;
5. execute generate/resume/finalize without replay and require
   `action=display_exact`;
6. perform daemon/tunnel failure injection and record external acceptance
   evidence.

Do not claim `remote_runtime_available=true` from repository code, a URL or a
healthy tunnel alone.
