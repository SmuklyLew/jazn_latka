# Historical clean-room contract tests before V111

Source HEAD: `a0d98f065628d3333e487a845d2428fe3882ab49` (V110), PR #464.
Original committed blobs, copied byte-for-byte:
- `tests/test_package_distribution_cleanroom_activation_observability.py`: `5893277adb932110937409befdf6114332593bd0`
- `tests/test_package_distribution_cleanroom_prestart_contract.py`: `2f8505ae704ee45dcdb5daa9f2fbf83a4ff76cb6`

The active tests were updated to match the current fresh-unprovisioned
negative case and the verified managed interpreter handoff. Security
assertions (fail-closed, status, heartbeat, provenance) are retained.
These historical snapshots are not part of default pytest collection.
