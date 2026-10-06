# Jaźń 16.3.25.5.113 — Remote-only ChatGPT ingress convergence

## Cel

Ta aktualizacja usuwa losowo dostępny lokalny/process executor ChatGPT z normalnej ścieżki rozmowy. Zwykła wiadomość może wejść do Jaźni wyłącznie przez rzeczywiście wywoływalną aplikację/MCP powiązaną z jednym persistent runtime. Lokalny executor, filesystem i ZIP bootstrap pozostają wyłącznie jawną ścieżką serwisową `operator_recovery`.

## Zmiana architektury

Normalna ścieżka:

```text
ChatGPT current-message app/tool exposure
  -> jazn_status
  -> verified persistent runtime
  -> jazn_generate_visible_reply
  -> jazn_resume_visible_reply (tylko gdy wymagany)
  -> jazn_finalize_reply
  -> accepted display_exact
```

Brak kompletnego toolsetu nie powoduje już próby Pythona, terminala, ZIP bootstrapu ani automatycznego handoffu.

## Najważniejsze zmiany

- dodano `ChatGptIngressMode.REMOTE_ONLY` i `OPERATOR_RECOVERY`;
- preflight ordinary-chat fail-closed blokuje local executor nawet wtedy, gdy taki executor przypadkowo istnieje;
- jawny `operator_recovery` zachowuje dotychczasowe lokalne narzędzia serwisowe;
- `host-preflight` uznaje zweryfikowany remote runtime za pozytywny gate;
- wymagany zestaw czterech kanonicznych narzędzi ma wersjonowany fingerprint/revision;
- `jazn_status` publikuje revision/SHA wymaganej powierzchni;
- loader Projektu i `AGENTS.chatgpt.md` zostały przełączone na remote-only;
- stale/frozen snapshot aplikacji kończy się instrukcją Refresh/Recreate/republish, a nie fallbackiem executora;
- publiczny Streamable HTTP i Secure MCP Tunnel pozostają transportami do tego samego persistent runtime.

## Granice platformy

Kod repozytorium nie może sam wymusić ekspozycji aplikacji Jaźni w każdej wiadomości ChatGPT. Brak bieżącej callable aplikacji pozostaje hostowym blockerem i kończy się fail-closed. Ta aktualizacja nie przedstawia samej instalacji, URL-a, tunelu ani starego snapshotu narzędzi jako dowodu conversation-ready.

## Walidacja

Nowy test `tests/test_chatgpt_remote_only_ingress_convergence.py` obejmuje:
- brak promocji local executora w remote-only;
- zachowanie jawnego operator recovery;
- pozytywny remote route;
- fingerprint toolsetu;
- startup contract;
- loader remote-only;
- stale app refresh guidance;
- identity wersji 16.3.25.5.113.

Pełne wyniki CI należy traktować jako release evidence dopiero po wykonaniu workflow na branchu. Metadane release `PACKAGE_INTEGRITY_MANIFEST.json` i `SOURCE_PROVENANCE.json` nie są edytowane ręcznie; obowiązuje kanoniczny release metadata sync/workflow.
