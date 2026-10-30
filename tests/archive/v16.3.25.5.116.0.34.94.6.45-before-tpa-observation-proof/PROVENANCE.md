# Immutable historical test snapshot

Original: `tests/test_jazn_tpa_evidence.py`, commit
`b2b205cfae14fda4a037503b6b1c682be1520441`, runtime .94.6.45.
SHA256: `1af7d680ef4ccdce8db61ec9b9f7e7d40e4b042bec27bc964d3f6efba8182496`.
The active human-observation test now supplies a valid synthetic JUnit and
exit code before recording PASS. Its earlier history/append-only assertions
remain intact. This snapshot is byte-for-byte and must not be changed.

Also preserved: `test_jazn_tpa_live_full_gate.py` from the same commit,
SHA256 `4e2666dbae8faec853b79320c57811218600b9b61445d91f7706c5bab0db7af4`.
Its active synthetic fixture now includes identity, distinct accepted turns and
display acknowledgements. The zero-exit and separate human-gate assertions remain.
