# Jaźń v127.21 — lokalny Ollama reconnect: historia zaakceptowanej sesji

## Dowód regresji (Windows, 20.11.2026)

Testowany runtime v127.20, `--chat-ollama --ollama-model gemma3:latest
--session-id local-v12720-smoke`: trzy zaakceptowane tury, po `/exit`
daemon pozostał `active_trusted` i `runtime_write_ready=true`.

Po ponownym dołączeniu użytkownik zapytał:

> Czy pamiętasz hasło, które podałem w naszej poprzedniej rozmowie przed
> odłączeniem terminala? Jeśli tak, podaj je dokładnie.

Dwie tury (osobne `request_id`, to samo `user_text_sha256`) zostały
odrzucone z `runtime_turn_not_accepted`. Audyt `runtime_audit.sqlite3`
potwierdził:

- `selected_route=memory_experience_recall`;
- `selected_handler=MemoryExperienceRecallHandler`;
- `failure_kind=FINALIZATION_REJECTED`;
- `failure_reason_code=classified_non_dynamic_response`;
- `canonical_persistence_commit=rejected/turn_not_accepted`;
- diagnostyka `REPAIR_SYNTHESIS`, bez zaakceptowanego final.

Są to dowody z dostarczonej diagnostyki użytkownika. Brak surowych wiadomości,
sekretów i prywatnej MEMORY w tym raporcie.

## Przyczyna i poprawka

`is_session_dialogue_reference()` nie uznawał jawnego odwołania do wiadomości
„przed odłączeniem terminala” za historię **tej samej** sesji. Ogólny routing
`pamiętasz` przechodził zatem do autobiograficznego
`MemoryExperienceRecallHandler`, który poprawnie wymaga ugruntowanej MEMORY.

Nowy, wąski warunek rozpoznaje `przed odłączeniem terminala` oraz
`po ponownym podłączeniu/połączeniu terminala` jako odwołania do **kanonicznej
bieżącej sesji**, o ile zapytanie ma konkretny przedmiot i nie zawiera jawnych
odniesień do innego czatu lub historycznego czasu. W ten sposób
`contextual_continuation_question` może korzystać z już istniejącej,
ograniczonej projekcji **zaakceptowanych, hash-bound session turns**.

To nie jest eskalacja do autobiographical MEMORY. Sam tekst pytania nie
poświadcza dostępności historii: przy braku zaakceptowanych rekordów wolno
powiedzieć wyłącznie, że brak zweryfikowanego źródła.

Nie zmieniono `runtime_truth_gate`, `RuntimeAnswerValidator`,
`MemoryExperienceRecallHandler`, zasad accepted finalization, SHA,
continuity ani polityki no-replay.

## Testy regresji

`tests/test_terminal_reconnect_session_recall.py` obejmuje:
- dokładne pytanie z raportu operatora;
- `memory_intent.operation=none` oraz routing do
  `contextual_continuation_question`, nie pamięci autobiograficznej;
- brak zmyślonego selektora wcześniejszej wiadomości;
- jawne cross-session/temporal references;
- brak historii zaakceptowanej bez awansu do MEMORY.

Przykładowe komendy w zweryfikowanym checkout:

```powershell
python -X utf8 -m pytest -q tests/test_terminal_reconnect_session_recall.py tests/test_conversation_model_context_continuity.py tests/test_generative_dialogue_nlg_convergence.py
python -X utf8 -m pytest -q tests/test_test_suite_governance.py
python -X utf8 -m latka_jazn.tools.release_metadata_sync --root . --base-branch master --check --json
```

Dodatkowo wymagany jest pełny gate GitHub Actions na ostatnim SHA;
sukces statycznych testów nie zastępuje testu lokalnej generacji z Ollamą.

## Procedura odbioru operatora na Windows (nieautomatyczna)

1. **Nie instalować patcha do działającego runtime.** Najpierw uzyskać
   zgodny kanoniczny manifest oraz `SOURCE_PROVENANCE`, zweryfikować `doctor`,
   `package-smoke` i osobny root testowy.
2. Z uruchomionym zweryfikowanym daemonem i lokalną Ollamą przeprowadzić
   dwie zaakceptowane tury z neutralnym, nieprywatnym znacznikiem.
3. Użyć `/exit` (tylko odłącza klienta), dołączyć ponownie z
   **tym samym** `--session-id` i spytać o wiadomość sprzed odłączenia.
4. Potwierdzić `contextual_continuation_question`, zaakceptowany
   `final_visible_text`, brak `runtime_turn_rejected` i niezmieniony
   `daemon_instance_id`.
5. Przypadek nowej sesji, `--no-carryover` lub braku historycznych
   accepted turns **musi odmówić odgadywania**.

Żaden rejected request nie może być automatycznie przesyłany ponownie;
oddziela się terminalowy `/exit` od zatrzymania daemonu.

## Stan odbioru

Ten raport dokumentuje kod i zakres walidacji, nie poświadcza samodzielnie
`pytest`, realnego Windows Ollama E2E ani readiness nowej wersji. PR
pozostaje Draft do końca wymaganej weryfikacji.
