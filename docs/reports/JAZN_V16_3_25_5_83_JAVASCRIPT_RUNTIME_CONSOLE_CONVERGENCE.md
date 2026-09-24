# Jaźń v16.3.25.5.83 — JavaScript Runtime Console Convergence

## Zakres

Wydanie wprowadza pierwszy efekt-bearing JavaScript w aktywnym SYSTEM, ale
utrzymuje językową granicę odpowiedzialności:

```text
Python = runtime authority + lifecycle + memory + turn/finalization
JavaScript = local browser presentation + reactive rendering + independent UI tests
```

Nie przenosi routingu, pamięci, cognition, identity ani finalizacji do Node.

## Implementacja

- nowa lokalna `run.py runtime-console`;
- statyczne ESM w `latka_jazn/resources/runtime_console/`, więc zasoby trafiają
  do istniejącego `system` package profile przez `latka_jazn/**`;
- read-only HTTP API z bounded projection zamiast ekspozycji surowego statusu;
- SSE dla live updates;
- strict CSP/security headers i loopback-only binding;
- brak npm runtime dependencies;
- Node 24 używany wyłącznie do CI/tooling tests;
- Python tests weryfikują security boundary i packaging.

## Granica prawdy

Runtime Console jest obserwatorem. Widok `active_trusted` nie jest dowodem
zaakceptowanej widocznej tury. Pole visible-turn zachowuje istniejący kontrakt,
że PID/heartbeat/endpoint nigdy nie wystarczają do autorstwa odpowiedzi.

Samo otwarcie SSE również nie oznacza runtime readiness; stan UI pochodzi z
projekcji statusu runtime.

## Zbieżność branchy

Branch powstał bezpośrednio z bieżącego `master` v16.3.25.5.82. Otwarte linie
Memory Studio są traktowane jako niezależne: nie są cherry-pickowane, ponieważ
są rozbieżne z bieżącym masterem i nie są potrzebne do kontraktu Runtime Console.

## Źródła

Projekt został zweryfikowany względem bieżących oficjalnych dokumentacji
Node.js, MDN, Python oraz OWASP. Szczegółowa lista jest w
`docs/tools/JAZN_RUNTIME_CONSOLE.md`.

## Walidacja

Wyniki testów i CI są dopisywane wyłącznie na podstawie rzeczywistych uruchomień.
Brak lokalnego executora nie jest przedstawiany jako zaliczony test.
