# Jaźń 16.3.25.5.115.15 — Studio pamięci i historia afektu

## Zakres napraw

Rozpoznawanie numerowanych plików conversations JSON wewnątrz ZIP jest spójne z importerem; zasoby w zagnieżdżonych katalogach assets/attachments otrzymują poprawną rolę. Inspekcja JSON rozpoznaje duże eksporty strumieniowo, bez wczytywania całej historii konta, pozostawiając pełną walidację importerowi. Pojedynczy dry-run operuje wyłącznie na tymczasowej kopii bazy, również z uwzględnieniem SQLite WAL.

## Kontekst stanów Jaźni

Tabela memory_l0_affect_turn_context w L0 v6 zapisuje wyłącznie identyfikatory zaobserwowane w oryginalnych źródłach: conversation_id, turn_id, trace_id, message_id, event_time oraz opcjonalny context_sha256. Widok memory_l0_affect_message_links wiąże etykietę z wiadomością wyłącznie przez dokładne dopasowanie identyfikatora rozmowy i identyfikatora wiadomości. Źródła bez takich danych są source_only; niczego nie wyprowadza się z podobieństwa języka, czasu ani sąsiedztwa.

Dla kolejnych modelowanych stanów jest dostępna metoda UnifiedMemoryDatabase.record_accepted_turn_affect z wymaganymi etykietami i danymi tury. Wywołujący runtime ma obowiązek przekazać ją wyłącznie po kanonicznym zaakceptowaniu i utrwaleniu odpowiedzi. Metoda sprawdza strukturę, a nie autentyczność dowodu finalizacji; automatyczne wpięcie w live runtime nadal jest osobnym zadaniem. Idempotencja chroni przed duplikowaniem tej samej tury. Nie ma automatycznej promocji L2/L3.

Granica prawdy: etykiety afektywne są zapisami źródłowymi lub modelowanymi stanami systemu, a nie dowodami biologicznego czy fenomenalnego doświadczenia.

## Testowanie i ograniczenia

Testy syntetyczne weryfikują ZIP, skanowanie, dry-run, modelowany afekt i integralność SQLite. Weryfikacja bieżącego działania z hostem ChatGPT, obsługi prywatnego eksportu konta i pełnego automatycznego zapisu afektu pozostaje osobna. Nie dołączono prywatnych rozmów ani baz. Starszy MEMORY ZIP z niezgodnym manifestem nadal wymaga poprawnej regeneracji z zatwierdzonych danych. Bez zgody użytkownika nie wykonuj merge.

Źródła: https://help.openai.com/en/articles/9106926-transferring-conversations-from-1-chatgpt-account-to-another ; https://www.sqlite.org/backup.html ; https://www.sqlite.org/wal.html .
