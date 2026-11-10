# Historical test snapshot before resume log visibility

Source branch: `fix/v114-main-jss-runtime-recovery-20261108`.
Source file: `tests/test_jazn_chat_terminal_recovery.py`.
Release line: `16.3.25.5.116.0.34.94.6.114`.

Copied the active test byte-for-byte before adding an assertion that sanitized `chat:resume` diagnostics appear in Output / Logi; no user prompt or final candidate is logged. This historical snapshot is outside the active pytest collection.
