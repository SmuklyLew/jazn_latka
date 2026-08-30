# Jaźń v16.3.1 — host finalization, provenance i polski NLP

## Zakres

Ta aktualizacja naprawia dwa niezależne błędy odkryte po v16.3.0 i rozszerza deterministyczną warstwę polskiego NLP. Nie usuwa epistemicznego truth gate. Rozdziela swobodny język odpowiedzi od typowanych dowodów, które muszą wspierać silne twierdzenia o wykonanych działaniach.

## Naprawione błędy

1. **Host-attested tool evidence ginęło przed końcowym epistemic gate.**
   `external_tool_evidence` było walidowane w phase-2, lecz trafiało tylko do `client_context`. Teraz zaakceptowane attestations są projektowane do ograniczonego `external_evidence` i przekazywane do `FinalVisibleReplyCapture`.
2. **Regex `RUNTIME_ACTION` wymagał wyłącznie lokalnego runtime eventu.**
   Twierdzenie „wykonałam audyt” mogło zostać odrzucone mimo prawdziwego GitHub/web provenance. Guard dopuszcza teraz tylko semantycznie pasujące host-attested tool actions; lokalne testy, komendy i uruchomienie runtime nadal wymagają lokalnego runtime evidence.
3. **CLI daemon fast-path nie był host-finalization clientem.**
   `chatgpt_bridge_one_shot_daemon_fast_path` jest teraz objęty tym samym phase-1 bindingiem co pozostałe host-capable clients, a `main.py` korzysta z jednego idempotentnego `attach_chatgpt_host_contract` zamiast budować i zapisywać drugi kontrakt.
4. **Domyślny workspace przy `<host>/runtime_roots/<version>` trafiał o poziom za nisko.**
   Host-level `workspace_runtime` jest teraz rozwiązywany jako `<host>/workspace_runtime`, zgodnie z dokumentowanym single canonical workspace.
5. **Projektowy słownik lematów miał niespójną normalizację i blokował prywatne rozszerzenie.**
   Klucze są ładowane przez NFC + casefold + ASCII-fold, zasób pakietowy działa także bez jawnego `root`, a prywatny `memory/raw/polish_lemma_overrides.json` może nadpisać projektowy wpis zamiast być ignorowanym.
6. **Morfologia miała drugi, rozbieżny suffix-strip.**
   `PolishMorphologyAnalyzer` korzysta teraz z kanonicznego layered lemmatizer i może przenosić POS/morph z opcjonalnych providerów. Builtin pozostaje lekkim fallbackiem.
7. Usunięto stare aktywne numery runtime z zasobów NLP oraz przypadkowe historyczne sformułowania z dokumentacji/korpusu przykładów.

## Granica prawdy dla tool provenance

Host-attested evidence zawiera tylko ograniczony `tool`, `operation` oraz referencje/URL-e źródeł. Runtime zachowuje rozróżnienie:

- `runtime_action_event_ids` — dowód działania wykonanego po stronie lokalnego runtime;
- `external_tool_action_ids` + `external_tool_actions` — uwierzytelniona deklaracja hosta o GitHub/web action;
- `external_source_ids` — źródła treści; samo źródło treści nie dowodzi wykonania działania.

Dla zapisów/aktualizacji zewnętrzne provenance musi wskazywać semantycznie zapisową operację GitHub. `web.run:search` nie może dowodzić „zaktualizowałam kod”. „Uruchomiłam runtime” i „wykonałam test” nadal wymagają lokalnego runtime eventu.

## Polski NLP

- rozszerzony słownik domenowy i odmiany kluczowych czasowników aktualizacji, audytu, finalizacji, źródeł, narzędzi i NLP;
- `casefold()` zamiast prostego `lower()` w kanonicznej normalizacji;
- spójne folded lookup dla diakrytyków;
- wspólny pipeline lematów/POS/morfologii zamiast równoległych heurystyk;
- opcjonalne Stanza/Morfeusz2 pozostają nieobowiązkowe, aby start runtime był model-free i fail-closed;
- rozszerzone przykłady treningowo-ewaluacyjne intencji system-update dla patch/NLP/provenance.

## Źródła techniczne

### Walidacja LLM i narzędzi

- OpenAI, **Structured Outputs** — JSON Schema i constrained decoding zwiększają niezawodność struktury, ale nie eliminują błędów semantycznych: https://openai.com/index/introducing-structured-outputs-in-the-api/
- OpenAI, **Function Calling** — `strict: true` gwarantuje zgodność argumentów z obsługiwanym schematem; aplikacja nadal musi obsługiwać edge cases i walidację: https://help.openai.com/en/articles/8555517-function-calling-updates
- OWASP, **AI Agent Security Cheat Sheet** — walidacja outputu przed wykonaniem/wyświetleniem, schema validation i bounded action scopes: https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html

### Polski NLP

- spaCy, **Polish trained pipelines** — `pl_core_news_sm` zawiera morphologizer i trainable lemmatizer, oparte m.in. na UD Polish PDB i NKJP: https://spacy.io/models/pl
- spaCy, **Lemmatizer** — regułowy lematyzator zależy od POS dostarczonego wcześniej przez tagger/morphologizer: https://spacy.io/api/lemmatizer/
- Stanza, **Lemmatization** — lematyzacja korzysta z tokenizacji/MWT/POS i może łączyć model z dictionary lookup: https://stanfordnlp.github.io/stanza/lemma.html
- Stanza, **POS & Morphological Features** — UPOS/XPOS/UFeats jako jawna warstwa morfologiczna: https://stanfordnlp.github.io/stanza/pos.html

### Trening i ewaluacja modeli

- Hugging Face Transformers, **Fine-tuning** — dalszy trening modelu pretrained na mniejszym zbiorze zadaniowym/domenowym: https://huggingface.co/docs/transformers/training
- Hugging Face TRL, **SFT Trainer** — supervised fine-tuning jako standardowa metoda post-training: https://huggingface.co/docs/trl/sft_trainer
- OpenAI, **Evals API** — jawne kryteria testowe, schemat danych oraz uruchamianie porównań modeli/konfiguracji: https://platform.openai.com/docs/api-reference/evals
- OpenAI, **Trustworthy third-party evaluations** — dla agentów/tool workflows wynik zależy także od środowiska i setupu, więc ewaluacja nie może ograniczać się do pojedynczej odpowiedzi chatbota: https://openai.com/index/trustworthy-third-party-evaluations-foundations/

## Wymagane regresje

Aktualizacja dodaje testy dla:

- audytu wspieranego przez host-attested GitHub evidence;
- odrzucenia `web.run:search` jako dowodu aktualizacji kodu;
- odrzucenia GitHub evidence jako dowodu lokalnego testu/uruchomienia runtime;
- przeniesienia external tool evidence aż do `persist_final_visible_reply`;
- fast-path daemon → awaiting_host_finalization → phase-2 completion;
- host-level workspace przy katalogu `runtime_roots`;
- polskich kluczy z diakrytykami, merge project/private overrides, packaged dictionary bez jawnego root;
- wspólnego morphology/lemma pipeline i rozpoznawania patch+NLP update intent.
