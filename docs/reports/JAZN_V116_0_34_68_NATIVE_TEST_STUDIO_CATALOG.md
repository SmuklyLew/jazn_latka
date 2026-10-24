# .68 native Test Studio catalog — partial P2/P3 migration

A first **native Qt** capability now uses canonical `tools.jazn_tests_studio.core.filtered`
on explicit user action to show test names, purposes, categories, status and
expected assertions. This does not run pytest, save reviews, modify MEMORY,
start legacy UI or claim complete Test Studio parity.

Read-only surface: `tools/jazn_run_studio/test_catalog_view.py`.
It is exposed as a dedicated page in the shared Qt shell. Search and status
filter rely on the existing Test Studio catalog/reviews contract. Only the first
300 records render, with explicit total/displayed counts; missing or corrupt
catalog shows an unavailable state rather than zero successful tests.
Selection displays the full expectation text of the selected record.
Qt widgets disable editing, and no write/run buttons exist.

Regression: `tests/test_jazn_run_studio_native_test_catalog_qt.py`;
Windows and Linux Python 3.12–3.14 native CI matrix updated.
Existing `window.py` preserved byte-for-byte under
`tests/archive/v16.3.25.5.116.0.34.67-before-test-catalog-native/window.py`
per repository change policy.

**Remaining work:** selected-test execution with progress/cancel; expectations
review editor with CAS and audit; history/result navigation, accessibility/DPI;
P1 MEMORY workflows and remaining ten+ specialist GUI migration. Neither the
current feature nor prior CI means all 12 applications are Qt-native.
P5 EXE security remains HOLD due to unresolved Avast IDP.Generic; offline and
independent SYSTEM acceptance remain NOT RUN.
