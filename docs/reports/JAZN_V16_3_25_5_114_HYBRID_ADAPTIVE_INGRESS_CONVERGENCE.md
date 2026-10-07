# Jaźń 16.3.25.5.114 — Hybrid/adaptive ingress convergence

## Cel

v114 przywraca bezpieczne działanie Jaźni w zwykłym środowisku ChatGPT, w którym
bieżąca wiadomość może nie dostać aplikacji Jaźni, ale host może rzeczywiście
udostępnić lokalny executor. Nie cofa persistent remote runtime z v113:
remote pozostaje trasą preferowaną.

## Zmiana kontraktu

Domyślny ordinary-chat ingress zmienia się z `remote_only` na
`hybrid_adaptive`:

```text
verified current-message remote runtime
  -> use remote
else
bounded verified host-local process/bootstrap
  -> use local persistent runtime
else
fail closed
```

`REMOTE_ONLY` pozostaje wspieranym trybem ścisłym.
`OPERATOR_RECOVERY` pozostaje jawnym trybem serwisowym i jedynym trybem, który
może promować zaakceptowany host handoff.

## Implementacja

- dodano `ChatGptIngressMode.HYBRID_ADAPTIVE`;
- ordinary adaptive preflight preferuje zweryfikowaną trasę remote;
- local executor może zostać promowany tylko gdy remote route nie jest gotowa
  przed submittem wiadomości;
- wykorzystano istniejący bounded probe contract: jedna podstawowa próba i
  najwyżej jedna niezależna alternatywa;
- pre-spawn host errors pozostawiają filesystem/package jako unknown;
- hybrid ordinary-chat blokuje automatyczny host handoff;
- plugin prompt i startup contract opisują remote-first/local-fallback;
- Project loader ponownie dopuszcza zweryfikowany SYSTEM ZIP bootstrap;
- v113 remote-only dokument pozostaje historyczny, nie został usunięty.

## Niezmienione granice

v114 nie osłabia:

- aktualnego current-message toolset gate dla remote MCP;
- `jazn_status` readiness/version binding;
- request idempotency;
- zakazu replayu wiadomości po submit;
- turn/finalization lineage;
- `MessageEnvelope`;
- accepted `action=display_exact`;
- SYSTEM integrity/path-safety bootstrap;
- MEMORY provenance/readiness;
- public MCP OAuth i Secure MCP Tunnel security.

## Testy regresyjne

Aktywny test `test_chatgpt_hybrid_adaptive_ingress_convergence.py` obejmuje:

- local fallback przy braku remote;
- remote priority przy jednoczesnej dostępności local;
- zachowanie jawnego strict `REMOTE_ONLY`;
- pre-spawn failure i filesystem unknown;
- single-alternative-probe budget;
- zakaz automatic handoff w ordinary chat;
- zachowanie operator recovery;
- startup contract;
- thin Project loader;
- plugin defaultPrompt;
- release identity v114.

Zmodyfikowane testy v113 zostały najpierw skopiowane bajt-w-bajt do
`tests/archive/v16.3.25.5.113-pre-v114-hybrid-adaptive-ingress/`.

## Granica dowodu

Kod i testy repozytorium mogą potwierdzić politykę routingu, ale nie mogą
stworzyć hostowego executora ani wymusić ekspozycji aplikacji w konkretnej
wiadomości ChatGPT. Rzeczywista sesja jest conversation-ready dopiero po
zaobserwowaniu jednej z dozwolonych tras oraz pełnego runtime/finalization
evidence.
