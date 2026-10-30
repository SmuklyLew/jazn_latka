# Historical test snapshot

Source: `tests/test_tpa_2_history_qt.py` at commit
`c1e177da4aad741c413b00e6820743efd64af33d`.
Runtime: `16.3.25.5.116.0.34.94.6.43-tpa-durable-history`.
SHA256: `d164f467606ebce6a1ee9ac17d3ef188005b2d08243010e05d7e15a4cd58116f`.
Reason: add a runtime non-None assertion before accessing panel.report, preserving
the original Qt restart/history contract and satisfying the active-tree type gate.
Snapshot is byte-for-byte and append-only; excluded from active pytest collection.
