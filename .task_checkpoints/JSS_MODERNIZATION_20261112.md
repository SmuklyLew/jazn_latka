# JSS modernization checkpoint

Branch: codex/v127-jss-ui-modernization-20261112
Initial HEAD: 8efa3fd49045b549811615b5cc73e63539a80df4
Usage: usage_unknown

## Stage 1
Implemented persisted 1/10/30/60 s cadence (default 10), immediate open read,
stop both view timers on hide, per-service scheduling errors, >=10 s CLI status
cadence. Existing Controller workers deduplicate in-flight reads.
26 targeted tests PASS (Python D:/ .AI/.venv/Scripts/python.exe, Qt offscreen).
Evidence: D:/.AI/.codex/visualizations/2026/11/12/01a1d160-d847-7461-9b0c-431b319e45cf/stage1-r3.xml
Earlier runs: setup denied default TEMP; then 25 PASS/1 FAIL (old opening count).
Historical tests preserved byte-for-byte with source SHA/hash.

## Remaining
Stages 2-6 pending. Full regression, real GUI/DPI, isolated daemon/Ollama,
release metadata synchronization/idempotence, push and PR not yet completed.
RELEASE_NOT_ACCEPTED. Production runtime/MEMORY untouched.
