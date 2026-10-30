"""Reviewed execution map. Regression evidence never certifies full Studio parity."""
from __future__ import annotations

from .local_acceptance import CATALOG, STUDIO_CATALOG

# Literal paths only. These suites use synthetic temporary projects; no operator
# command, private database or test expression is interpolated into a shell.
REGRESSIONS = {
    "gui-daemon": ("tests/test_jazn_run_studio_daemon_routing.py",),
    "ollama-two-turns": ("tests/test_jazn_run_studio_chat_contract.py",),
    "chat-reconnect": ("tests/test_jazn_run_studio_reconnect_acceptance_qt.py",),
    "chat-resume": ("tests/test_jazn_run_studio_delivery_ack.py",),
    "daemon-restart": ("tests/test_heart_system_public_restart.py",),
    "smoke-isolation": ("tests/test_package_smoke_workspace_isolation.py",),
    "config-persistence": ("tests/test_jazn_system_root_config.py",),
    "studios-parity": ("tests/test_jazn_run_studio_12_manual_studio_gates.py",),
    "offline-exe": ("tests/test_jazn_run_studio_bundle_integrity.py",),
    "ui-accessibility": ("tests/test_jazn_run_studio_workbench_qt.py",),
    "studio-system": ("tests/test_jazn_operator_studio.py",),
    "studio-start": ("tests/test_jazn_start_studio_dashboard.py",),
    "studio-configuration": ("tests/test_jazn_run_studio_configuration_native_qt.py",),
    "studio-memory": ("tests/test_memory_studio_step_workflows.py",),
    "studio-memory-rebuild": ("tests/test_memory_rebuild_p0_studio.py",),
    "studio-test-studio": ("tests/test_tests_studio_run_history_p1.py",),
    "studio-generator": ("tests/test_jazn_pack_generator_studio_portability.py",),
    "studio-dependencies": ("tests/test_dependency_studio_repeated_profiles.py",),
    "studio-python-runtime": ("tests/test_jazn_run_studio_integrations.py",),
    "studio-version-rebuild": ("tests/test_jazn_run_studio_version_native_qt.py",),
    "studio-chat-import": ("tests/test_memory_studio_step_workflows.py",),
    "studio-memory-restore": ("tests/test_memory_restore_tool.py",),
}
LIVE_CASES = frozenset({"gui-daemon", "ollama-two-turns", "chat-reconnect", "chat-resume", "daemon-restart"})
GUI_CASES = frozenset({"chat-reconnect", "ui-accessibility", "studio-configuration", "studio-version-rebuild"})
MODES = {"automatic": "Automatyczny", "assisted": "Wspomagany", "manual": "Ręczny"}
TARGETS = {
    "studio-system": ("Developer", "operator"), "studio-start": ("Usługi i procesy", "start"),
    "studio-configuration": ("Konfiguracja Qt", "configuration"), "studio-memory": ("Dowody MEMORY", "memory"),
    "studio-memory-rebuild": ("Studia Jaźni", "rebuild"), "studio-test-studio": ("Katalog testów", "tests"),
    "studio-generator": ("Studia Jaźni", "packages"), "studio-dependencies": ("Studia Jaźni", "dependencies"),
    "studio-python-runtime": ("Studia Jaźni", "python"), "studio-version-rebuild": ("Wersje Qt", "versions"),
    "studio-chat-import": ("Studia Jaźni", "memory"), "studio-memory-restore": ("Studia Jaźni", "memory"),
}

# Concrete operator procedures supplement the executable regression subset.
# Every sandbox exposes fresh inputs/ and its own runtime/operator directories.
PROCEDURES = {
    "gui-daemon": ("Wybierz model i Wykonaj odbiór izolowany. Panel tworzy własny SYSTEM/port, uruchamia kanoniczny start i sprawdza tożsamość oraz heartbeat.", "Otwórz log i dowód .live.json: conversation_ready musi być true, a cleanup.ok true; brak modelu nie jest gotowością rozmowy."),
    "ollama-two-turns": ("Kliknij Wykryj modele, wybierz model z listy zainstalowanych modeli lokalnej Ollamy i wybierz Wykonaj odbiór izolowany; niczego nie pobieramy.", "Obserwuj dwie zaakceptowane odpowiedzi w Przebieg / log. Druga ma odtworzyć losowy kod; sprawdź session_id, różne identyfikatory tur i potwierdzenie wyświetlenia."),
    "chat-reconnect": ("Wykonaj odbiór izolowany z wybranym modelem. Po pierwszej turze wykonawca zamknie tylko swój transport i połączy go ponownie.", "W dowodzie porównaj session_id i odtworzenie kodu w drugiej turze; utrata sesji lub kontekstu musi dać FAIL."),
    "chat-resume": ("Wykonaj odbiór izolowany z modelem. Wykonawca przerwie własny transport po send i będzie odpytywał zapisany request_id.", "Sprawdź jedną zaakceptowaną finalizację i brak powtórnego send; zaakceptowana odpowiedź pojawia się w panelu przed ACK."),
    "daemon-restart": ("Wykonaj odbiór izolowany. Po pierwszej zaakceptowanej turze wykonawca użyje publicznego restart wyłącznie swojej instancji.", "Porównaj nowe instance_id, niezmienioną session_id i odtworzenie kodu po restarcie. Niepowodzenie kontroli tożsamości blokuje sprzątanie obcych procesów."),
    "smoke-isolation": ("Otwórz JUnit podtestu: fixture tworzy własne markery i sprawdza ich niezmienność przy package-smoke.", "Nie wybieraj operacyjnego workspace. Zapisz obserwację sentinelów i ścieżek testowych z logu; brak danych przed/po oznacza nie ustalono."),
    "config-persistence": ("Otwórz izolowane Studio → Konfiguracja Qt. Zmień ścieżkę wyłącznie w projekcie testowym, sprawdź preview i zapisz po potwierdzeniu.", "Wczytaj ponownie profil, sprawdź poprzedni profil oraz konflikt CAS. Porównaj pliki operatora w obszarze przebiegu; nie migruj aktywnej instalacji."),
    "studios-parity": ("Wykonaj oddzielne odbiory wszystkich 12 pozycji studio-* na tym samym SHA; katalog i JUnit nie są dowodami migracji.", "Porównaj dowody z STUDIO_MIGRATION.md. Brak natywnego przepływu Qt oznacz BLOCKED/FAIL i opisz konkretną brakującą operację."),
    "offline-exe": ("W osobnej maszynie Windows/VM skopiuj wydany EXE wraz z całym onedir, BUILD_INFO i manifestem. Zapisz SHA256, wersję, źródłowy SHA oraz wynik kanonicznej weryfikacji pakietu.", "Odłącz sieć wyłącznie tej VM, uruchom EXE, przejdź podstawowe ekrany i workflow offline z lokalnym wheelhouse. Dołącz tekstowy raport, log i identyfikację zrzutów; bez takiego odbioru nie wpisuj PASS."),
    "ui-accessibility": ("Otwórz izolowane Studio. Sprawdź Tab/Shift+Tab/Space/Enter, wielokrotny pokaz/ukryj logi oraz okno 860×580.", "Porównaj jasny i ciemny motyw przy 100%, 150%, 200% DPI. Dołącz raport z rozmiarem, skalą, fokusem i zrzutami; ocena offscreen nie zastępuje Windows."),
    "studio-system": ("Otwórz izolowane Studio → Developer; porównaj diagnostykę, połączenia i ustawienia z klasycznym System Studio.", "Sprawdź odmowę usługi i plan aktualizacji bez apply. Brak natywnego podglądu aktualizacji lub audytu zapisz jako brak parzystości."),
    "studio-start": ("Otwórz izolowane Studio → Usługi i procesy. Porównaj katalog zadań, logi i kontrolki własności z Start Studio.", "Uruchom tylko własny daemon z nowego obszaru, sprawdź status i zatrzymaj go. Złe warunki mają pokazać konkretną blokadę, bez zielonego stanu z samego PID."),
    "studio-configuration": ("Otwórz izolowane Studio → Konfiguracja Qt. Sprawdź mapę ścieżek, preview diff, zapis, reload i przywrócenie poprzedniego profilu.", "Zmień pole i spróbuj zamknąć okno; sprawdź ochronę szkicu, nieprawidłową ścieżkę i konflikt równoczesnego zapisu. Używaj tylko nowego obszaru."),
    "studio-memory": ("Otwórz izolowane Studio → Dowody MEMORY. Stwórz testowy projekt przez publiczny workflow, wybierz inputs/source.txt i sprawdź role baz/proweniencję.", "Przejdź walidację źródła, kandydatów, afekt i protokół na danych syntetycznych. Niedostępny natywny krok opisz jako BLOCKED; nie dołączaj prywatnej bazy."),
    "studio-memory-rebuild": ("Otwórz izolowane Studio → Studia Jaźni → Memory Rebuild. Utwórz własny projekt i plan z inputs/source.txt; odczytaj walidację przed wykonaniem.", "Sprawdź brak źródła, anulowanie, raport i eksport wyłącznie do własnego obszaru. Zapisy dopiero po podglądzie i potwierdzeniu."),
    "studio-test-studio": ("Otwórz izolowane Studio → Katalog testów. Sprawdź wyszukiwanie, oczekiwania i recenzje; uruchom wybrany podtest na fixture.", "Anuluj dłuższy test, otwórz wynik/historyczny przebieg i przywróć wybór. Brak edytora recenzji lub historii Qt pozostaje jawną luką."),
    "studio-generator": ("Otwórz izolowane Studio → Studia Jaźni → Generator paczek. Użyj inputs/ jako źródła i nowego katalogu outputs/ dla plan/pack.", "Przejdź verify, split/join oraz błąd brakującej części. Sprawdź anulowanie i ustawienia; nie pakuj SYSTEM użytkownika ani prywatnej MEMORY."),
    "studio-dependencies": ("Otwórz izolowane Studio → Studia Jaźni → Studio Zależności. Wskaż wybrany interpreter testowy, profil i kanoniczny lock/wheelhouse.", "Najpierw inspect/verify; instalację do testowego venv wykonaj wyłącznie po podglądzie i potwierdzeniu. Brak wheelhouse/offline pozostaw BLOCKED."),
    "studio-python-runtime": ("Otwórz izolowane Studio → Studia Jaźni → Python Runtime. Wykonaj detect-host i porównaj wybrany interpreter, wersję i pakiety.", "Sprawdź brakujący interpreter i niepoprawny pakiet. Operacje instalacji/bundle kieruj wyłącznie do nowego testowego katalogu po potwierdzeniu."),
    "studio-version-rebuild": ("Otwórz izolowane Studio → Wersje Qt. Porównaj AST/wersję ze stagingiem, a następnie preview/backup z klasycznym Version Rebuild.", "Nie zapisuj do aktywnej instalacji. Brak edycji/diff/rollback w natywnej stronie oznacza niepełną migrację, nawet jeśli odczyt wersji działa."),
    "studio-chat-import": ("Otwórz izolowane Studio → Studia Jaźni → Memory. Użyj inputs/source.txt w publicznym planie importu do nowego syntetycznego projektu.", "Sprawdź tożsamość źródła, powtórny import, verify, kolejkę i wyszukiwanie. Brak osobnego przepływu Qt opisz jako BLOCKED; nie importuj prywatnych rozmów."),
    "studio-memory-restore": ("Otwórz izolowane Studio → Studia Jaźni → Memory. Utwórz syntetyczny projekt i baseline publicznym narzędziem; wybierz scan/plan przed restore.", "Porównaj plan, backup i compare; restore wyłącznie własnego projektu po potwierdzeniu. Brak natywnego workflow plan/compare/restore pozostaje BLOCKED."),
}


def execution_map() -> list[dict]:
    """Each catalogue row has executable regression and a distinct full gate."""
    items = []
    for original in (*CATALOG, *STUDIO_CATALOG):
        key = original["id"]
        mode = "automatic" if key in {"smoke-isolation", "config-persistence"} else "assisted"
        if key == "offline-exe":
            mode = "manual"
        requirements = ["pytest"] + (["PySide6"] if key in GUI_CASES else [])
        if key == "studio-memory-rebuild":
            requirements.append("prompt_toolkit")
        steps = [
            "Uruchom przypisany podtest regresyjny i otwórz jego wynik oraz JUnit.",
            *PROCEDURES[key],
            "Dołącz raport obserwacji i porównaj z kryterium: " + original["expected"],
        ]
        limitations = "Podtest na danych syntetycznych. Nie potwierdza pełnego odbioru ani migracji Studio."
        if key in LIVE_CASES:
            limitations += " Odbiór izolowany używa rzeczywistego daemona; rozmowa wymaga wybranego lokalnego modelu Ollama."
        if key.startswith("studio-") or key == "studios-parity":
            limitations += " Macierz STUDIO_MIGRATION.md nadal zawiera nieukończone przepływy Qt."
        items.append({**original, "mode": mode, "files": list(REGRESSIONS[key]),
                      "requirements": requirements, "executor": "pytest (izolowany proces)",
                      "live_executor": "TPA → kanoniczny Controller/ChatClient" if key in LIVE_CASES else None,
                      "guide": steps, "limitations": limitations,
                      "coverage": "regression_subset", "full_gate": "NOT_RUN"})
    return items


def scenario(case_id: str) -> dict:
    for item in execution_map():
        if item["id"] == case_id:
            return item
    raise ValueError("Nieznany scenariusz TPA")
