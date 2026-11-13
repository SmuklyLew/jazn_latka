# Historical test snapshot before JSS daemon-only CLI enforcement

Source branch: `fix/v114-main-jss-runtime-recovery-20261108`
Source commit: `c71ba46f99e39924d1d27082a2236bf4a2036151`
Source file: `tests/test_jazn_run_studio_daemon_routing.py`

This is a byte-for-byte copy of the active test before enforcing `--ensure-daemon` in the JSS CLI transport. The active test keeps its original name and additionally requires the daemon-only contract.
