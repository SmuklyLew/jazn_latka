# Studio .71: fix direct-script Windows build failure

Evidence: GitHub Actions run https://github.com/SmuklyLew/jazn_latka/actions/runs/40069842029, job 120801424764.
PyInstaller COLLECT completed but tools/jazn_run_studio/build.py raised
ModuleNotFoundError: No module named 'tools' when importing the onedir manifest writer.

Python's sys.path first entry for direct script execution is the containing
script directory, not necessarily the repository root; unlike -m execution.
Official reference: https://docs.python.org/3.12/library/sys_path_init.html

The corrected writer selects a sibling import for direct build.py execution,
and a package-relative module import when imported as tools.jazn_run_studio.build.
No PYTHONPATH changes, no removal of hash checks, no antivirus bypass.
New regression tests both modes, including isolated Python -I with no
repository root on sys.path. The Windows package job now asserts that the
actual PyInstaller onedir inventory is valid before GUI smoke.

Evidence boundary: .70's six OS/Python test jobs succeeded, but its package
job failed. None of these results is .71 evidence. Verify final-source CI,
canonical release metadata synchronization, Windows frozen GUI and offline
external SYSTEM separately. Avast IDP.Generic remains HOLD; P1–P3 UI parity,
Windows health-check repeatability and local MCP framing remain open.
