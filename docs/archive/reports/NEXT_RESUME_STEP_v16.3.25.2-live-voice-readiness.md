# NEXT_RESUME_STEP — v16.3.25.2 live Voice readiness

Status zapisano 2026-08-29 po uruchomieniu bezpiecznika limitu Codex (13% pozostałego okna). Nie rozpoczęto etapu G ani instalacji zasobów NLP.

## Punkt wznowienia

- Repo referencyjne: `D:\.AI\jazn_latka_master` — bez zmian.
- Worktree roboczy: `D:\.AI\jazn_branchs\v16.3.25.2-live-voice-readiness`.
- Branch: `fix/v16.3.25.2-live-voice-readiness`.
- Base: `e6a2ca5a6aa01f08b0406e3e6b771461910cfc66` (`origin/master` po świeżym fetchu).
- Ostatni zielony checkpoint funkcjonalny: `fe3549ac5d90db4d78859e230d412311759ba326`.
- Wersja: `16.3.25.2-live-voice-readiness`.
- Push/PR: **NOT RUN**.

Pierwsza komenda po wznowieniu:

```powershell
cd D:\.AI\jazn_branchs\v16.3.25.2-live-voice-readiness
git status --short --branch
```

Następny etap: G — dodać `nlp_enhanced_ready` oparte na wykonanych capability-probes oraz syntetyczny, jawnie etykietowany polski corpus regresyjny. Ciężki probe Stanza powinien działać wyłącznie w trybie `deep`; brak modeli lub brak wykonanego probe nie może dać stanu zielonego. NLP pozostaje opcjonalne i nie blokuje `runtime_core_ready` ani `voice_live_ready`.

## Checkpointy

1. `cbd4244` — `fix: require live daemon evidence for Voice readiness`
2. `bf6e264` — `feat: separate core and system readiness profiles`
3. `61ac591` — `feat: bind Voice E2E proof to each visible turn`
4. `61c65b1` — `test: cover false-green Voice and issue 185 in CI`
5. `fe3549a` — `feat: probe dictionary lookup readiness without network`

## Dowody lokalne

- Reprodukcja na bazowym masterze: stale marker + martwy daemon dawał `voice_ready=true`; test był RED przed poprawką.
- Etapy A/B: 32 ukierunkowane testy Voice/startup/readiness — **PASS**.
- Etap C: 10 testów readiness/status — **PASS**; osobny realny cykl lokalnego daemona — **PASS**.
- Etap D: deterministyczny test dwóch tur tego samego daemona oraz negatywne przypadki Voice E2E — 6 testów — **PASS**. Wcześniejszy szerszy przebieg miał 56 PASS i 1 FAIL w syntetycznym tekście drugiej tury; tekst fixture poprawiono, a test docelowy po poprawce jest zielony. Szerokiego przebiegu nie powtórzono jeszcze po tej korekcie.
- Etap E: 31 testów Voice/readiness/#185/security — **PASS**.
- Etap F: 19 testów łączonych dictionary/Voice — **PASS**; końcowy focused run 4 testów słownika — **PASS**.
- `git diff --check origin/master...HEAD` — **PASS**.
- Stan worktree przed utworzeniem tego raportu — czysty.

## Wciąż niewykonane

- G — `nlp_enhanced_ready` i syntetyczny polski corpus.
- H — oficjalny dry-run `tools/Install-JaznPolishReasoningResources.ps1`, potem osobno Morfeusz2 i rekomendowany Stanza PL; żadnych modeli w Git.
- I — finalny raport, release metadata sync i powtórna kontrola generatora.
- Pełny pytest, compileall, repozytoryjny Pyright, Windows acceptance i końcowy audit wykluczeń — **NOT RUN**.
- GitHub Actions Windows/Ubuntu — **NOT RUN**; wymagają pushu.
- Push brancha i ewentualny PR — **NOT RUN**.
- Issue #180 pozostaje osobnym P1 i nie może zostać zamknięte tym hotfixem.

## Granice zakresu

Nie kontynuować na tym branchu Memory Rebuild v4, prywatnego importu pamięci, attachment ingress ani przebudowy architektury poznawczej. Nie commitować `memory/`, `workspace_runtime/`, modeli, SQLite/WAL/SHM, ZIP-ów, sekretów ani prywatnych eksportów.
