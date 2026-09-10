# Jaźń — CURRENT STEP

**Status:** `CANONICAL_CURRENT_STEP`  
**Stan:** 2026-09-10
**Baza:** `master @ 2bb162a118e56b8a757ae20a925e0a7d1295487f` / `16.3.25.5.59-conversation-runtime-orchestration-convergence`
**Branch:** `upgrade/v16.3.25.5.60-main-entrypoint-chatgpt-live-convergence`
**Target:** `16.3.25.5.60-main-entrypoint-persistent-chatgpt-convergence`

## 1. Bieżący krok — main-first + persistent ChatGPT

Najwyższy priorytet to usunięcie błędu ownership wykrytego w prawdziwej rozmowie ChatGPT: żywy daemon/PID nie gwarantował, że każda wiadomość hosta przechodzi przez runtime, ponieważ aktywna instrukcja kazała uruchamiać świeże `run.py chat-gpt -- <message>` dla każdej tury.

Bieżąca migracja:

```text
run.py                   thin user launcher
  ↓
main.py                  single central control plane
  ↓
Conversation/runtime services
  ↓
one persistent ChatGPT stdin/JSONL bridge per executor session
  ↓
persistent daemon/session owner
```

## 2. Zakres v60

- odchudzić `run.py` do launchera;
- przenieść centralny top-level dispatch/lifecycle/recovery/finalization do `main.py`;
- zachować `latka_jazn.cli` jako parser/service layer bez drugiego control-plane importu w kanonicznej trasie;
- utrzymywać jeden `chat-gpt` process i ten sam stdin/stdout przez kolejne tury;
- prowadzić phase-2 host candidate/finalization tym samym kanałem;
- nie używać płatnego OpenAI API w trasie ChatGPT;
- traktować MCP jako transport opcjonalny, nie requirement dla bieżącego hosta/Plus;
- zaktualizować aktywne AGENTS/runbook/loader/help/discovery;
- dodać command-parity, persistent multi-turn, reconnect/idempotency i no-paid-API tests;
- wykonać compileall, Pyright, deterministic tests, CI i canonical manifest sync.

## 3. Exit gate v60

```text
run.py thin                              PASS required
main.py single control owner             PASS required
no per-message CLI in active ChatGPT docs PASS required
persistent JSONL 10+ turns               PASS required
same-channel phase2                      PASS required
reconnect without duplicate turn/final  PASS required
paid OpenAI API not required/auto-used   PASS required
runtime lineage on every visible turn    PASS required
Linux + Windows CI                       PASS required
package integrity after canonical sync   PASS required
```

Dokumentacja, branch, PID lub pojedynczy test nie certyfikują samodzielnie tego gate.

## 4. Następny krok po v60

Dopiero po v60 można bezpiecznie wykonać kolejną część `CONVERSATION_RUNTIME_CONVERGENCE_PLAN.md`:

1. wydzielić `ConversationRunner` z dużego `main.py`, pozostawiając `main.py` composition ownerem;
2. ujednolicić daemon/session execution owner;
3. utrwalić pełny `TurnStateMachine`;
4. podłączyć memory/affect/NLP/tool policy przez typed lifecycle events;
5. wykonać source-aware memory i causal/ablation evidence;
6. utrzymać szerszą roadmapę Memory/Affect/attachment/NLP bez naruszania jej gates.

## 5. Granica naukowa

„Neurologiczny” oznacza funkcjonalne połączenia software: ingress, routing, working state, memory, salience/affect, decision, action, source monitoring, finalization i autonomic lifecycle. Nie oznacza biologicznego układu nerwowego ani dowodu świadomości.
