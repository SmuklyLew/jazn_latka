# Studio Pamięci .80.1 — jawny kontrakt repozytorium Test04

Status: IN_PROGRESS. Konwergencja z masterem affabf5618934bd8efb39b0b1d074f7529116643 została zapisana i wypchnięta: merge 037adcdd, metadane 052ad40ebf53587a789c1d897570c64d18a80102. Ten etap naprawia Test04; nie zastępuje prywatnej akceptacji.

Usunięto produkcyjną stałą EXPECTED_BRANCH wskazującą feature/memory-sqlite-test-04. ProtocolRequest, Python CLI i operator PowerShell przyjmują expected_branch / expected_ref. Brak obu blokuje wykonanie przed zapisem. Oczekiwany branch sprawdzany jest dokładnie, a ref rozwiązywany przez Git do commita i porównywany z HEAD. Podanie obu wymaga zgodności obu. Odłączony HEAD jest dozwolony wyłącznie przy zgodnym jawnym ref bez wymagania nazwy brancha. Sprawdzanie brudnego drzewa pozostaje niezależne.

30 testów PASS: istniejący Test04 oraz nowy test kontraktu repozytorium (rzeczywiste syntetyczne repozytoria Git, brak oczekiwania, niewłaściwy branch, brakujący ref, stary commit, detached HEAD, dirty tree, zachowanie pól request/parser i odmowa PowerShell bez oczekiwania). Przed zmianą historycznego testu zapisano dokładny blob z 052ad40e wraz z hashem w tests/archive/branches/16.3.25.5.80__052ad40ebf53/. Asercje integralności, faz, recall i ochrony prywatnych danych nie zostały osłabione.

Wersja .80.1 została sprawdzona jako wolna w branchach, tagach i wydaniach. Pełna walidacja publiczna, nowy prywatny chain Test00–Final i zamrożony benchmark nadal wymagają wykonania. Raporty .76 i .80 pozostają historyczne; dalsze wyniki dopisywać jako nowe evidence.
