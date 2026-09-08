# STATUS — rest/NLP readiness convergence

- base: `master@9d135ae00a305c8f73b1a25b96d39c6c3729d0cc`
- branch docelowy: `fix/v16.3.25.5-rest-nlp-readiness-convergence`
- etap: diagnoza zakończona, implementacja rozpoczęta
- prywatne dane: nieużywane i niecommitowane
- release metadata: nieedytowane ręcznie

## Dowody z live runtime przed zmianą

- `/ready.rest_cycle_status.enabled = true`
- `/ready.rest_cycle_status.state = waiting_for_idle`
- `/ready.rest_cycle_status.rest_scheduler_ready = true`
- `/ready.rest_cycle_status.rest_scheduler_running = true`
- `run.py status.system_readiness_profile.rest_scheduler = ready:false, status:unknown`
- `run.py status.system_readiness_profile.nlp_enhanced = ready:null, status:not_yet_capability_probed`

To rozdziela błąd raportowania scheduler-a od rzeczywistej awarii scheduler-a oraz brak wykonywanego probe NLP od samej obecności kodu NLP.
