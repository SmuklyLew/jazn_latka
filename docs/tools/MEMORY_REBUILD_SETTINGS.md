# Memory Rebuild — ustawienia Studio v16.3.16

Memory Rebuild rozdziela **ustawienia narzędzia** od **ustawień projektu**. Nie są to te same dane i nie powinny być zapisywane do jednego pliku projektu.

## `memory_rebuild_settings.json`

Studio automatycznie tworzy pełny plik ustawień narzędzia przy pierwszym uruchomieniu.

Kolejność wyboru lokalizacji:

1. jawne `--settings`;
2. `JAZN_MEMORY_REBUILD_SETTINGS`;
3. `<JAZN_RUNTIME_WORKSPACE_DIR>/memory_rebuild_settings.json`;
4. `<tool_root>/memory_rebuild_settings.json`;
5. `<cwd>/memory_rebuild_settings.json`.

Gdy runtime ma jawny host-level workspace, plik mutable nie trafia do wersjonowanego `active_root`.

Schemat:

```json
{
  "schema_version": "jazn_memory_rebuild_settings/v1",
  "runtime": {
    "require_fts5": true,
    "embeddings_enabled": false,
    "embedding_model": null,
    "retrieval_limit": 20,
    "min_lexical_score": 0.0,
    "require_provenance": true,
    "automatic_l2": false,
    "automatic_l3": false,
    "automatic_activation": false
  },
  "studio": {
    "theme_name": "latka-terminal"
  }
}
```

Zapis jest atomowy: najpierw powstaje sąsiedni plik `.tmp`, a następnie `os.replace()` zastępuje poprzednią wersję.

Stary płaski JSON zawierający bezpośrednio pola `MemoryRebuildSettings` pozostaje obsługiwany. Studio przy zapisie/uruchomieniu z `create=True` migruje go do pełnego schematu.

## Co wolno zmieniać w ustawieniach narzędzia

Edytowalne i walidowane:

- `retrieval_limit` — `1..500`;
- `min_lexical_score` — `0..1`;
- `embeddings_enabled`;
- `embedding_model` — obowiązkowy, gdy embeddingi są włączone;
- `studio.theme_name`.

Tylko do odczytu / wymuszone:

- `require_fts5=true`;
- `require_provenance=true`;
- `automatic_l2=false`;
- `automatic_l3=false`;
- `automatic_activation=false`.

To nie są ukryte przełączniki. Próba złamania tych invariantów w JSON kończy się błędem walidacji.

## Ustawienia projektu

Każdy projekt nadal przechowuje własne dane w `*.memory-rebuild.json`. Studio v16.3.16 pozwala je edytować bez przechodzenia do starego, ograniczonego menu.

Edytowalne są:

- nazwa projektu;
- tryb `developer/system`;
- `target_root`;
- `source_directory`;
- `test04_acceptance_report`;
- `system_acceptance`;
- wszystkie zwykłe ustawienia z `DEFAULT_SETTINGS`, m.in. skanowanie, walidacja, backup, klasyfikacja, analiza tematów, limity i częstotliwość raportowania.

Ustawienia, które obniżają poziom ochrony albo rozszerzają zakres automatycznego działania, wymagają dodatkowego potwierdzenia w Studio. Dotyczy to m.in. `continue_on_error`, `apply_reclassification`, `force_topics`, wyłączenia backupu/pełnej walidacji oraz wyłączenia zachowania pełnych branchy i dokładnego tekstu źródłowego.

Tylko do odczytu / wymuszone na `false` pozostają:

- `automatic_experience_approval`;
- `automatic_l2`;
- `automatic_l3`.

`unified_database_path` jest pokazywane w ustawieniach projektu, ale zmienia się je przez **PROJEKTOWANIE → Baza docelowa**, aby nie tworzyć dwóch konkurujących ścieżek edycji.

## Obsługa Studio

Na stronie **USTAWIENIA**:

- `Enter` otwiera edytor wybranej sekcji;
- `S` zapisuje ponownie pełny `memory_rebuild_settings.json`;
- `T` przełącza theme i od razu zapisuje wybór;
- sekcje bezpieczeństwa i środowiska pozostają informacyjne/read-only.

Zmiany w ustawieniach są trwałe; nie są już wyłącznie informacją wyświetlaną na ekranie.
