# Jaźń v16.3.25.5.40 — host contract neutralization

## Cel

Aktualizacja usuwa zależność instrukcji hosta ChatGPT od nazwy lub opisu warstwy rozmownej. Instrukcje platformy pozostają cienkim loaderem systemu, a właściwe zachowanie bieżącej tury wynika wyłącznie z wersjonowanego runtime i jego kontraktu action-first.

## Zmiany

- `docs/runtime/CHATGPT_PROJECT_INSTRUCTIONS.txt` jest wyłącznie `LOADER SYSTEMU JAŹNI` i nie zawiera persony ani danych runtime.
- `AGENTS.md` pozostaje krótkim routerem odpowiedzialności.
- `AGENTS.chatgpt.md` opisuje discovery, granicę błędu executora, bootstrap, `run.py`, persistent daemon, pre-response gate i finalizację bez zależności od nazw własnych.
- `AGENTS.ollama.md` jawnie stwierdza, że jest kontraktem integracji, a nie system promptem modelu ani treścią do automatycznego wstrzykiwania do `messages`/`SYSTEM`.
- `AGENTS.codex.md` zachowuje dotychczasowy runbook zmian repo i sprawdza limit 5000 znaków dla pliku przeznaczonego do Custom Instructions.
- prezentacja hosta publikuje kanoniczne pola `must_not_claim_runtime_voice` i `must_preserve_runtime_voice`.
- stare pola `must_not_claim_latka_voice` i `must_preserve_latka_voice` pozostają jako ograniczone aliasy zgodnościowe o identycznych wartościach.

## Zgodność

Zmiana jest addytywna dla konsumentów pakietu hosta: stare pola nadal istnieją, dlatego aktualne integracje nie muszą migrować atomowo. Nowe integracje i dokumentacja powinny używać neutralnych pól `*_runtime_voice`.

## Źródła zewnętrzne

Projekt opiera się na aktualnej dokumentacji OpenAI dotyczącej Custom Instructions oraz instrukcji projektowych/Codex, a dla Ollamy na oficjalnym kontrakcie `/api/chat`, `/api/tags` i konfiguracji modelu. Źródła są wykorzystywane do granic integracji; nie stanowią dowodu działania lokalnego runtime.

## Walidacja

Wymagane przed merge:

- testy regresyjne v16.3.25.5.40;
- istniejące testy host-contract i voice-continuity;
- `compileall`;
- `pytest -m "not live_model and not live_mcp"` w środowisku z pełnymi zależnościami projektu;
- `doctor`, `package-smoke`, `git diff --check`;
- GitHub Actions wymagane przez repozytorium;
- synchronizacja `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` przez kanoniczny mechanizm release metadata.
