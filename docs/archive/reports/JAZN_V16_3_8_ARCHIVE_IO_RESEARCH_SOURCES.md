# Jaźń v16.3.8 — archive I/O research sources

## Python ZIP / ZIP64

- Python 3.14 `zipfile`: https://docs.python.org/3/library/zipfile.html
  - supports ZIP64;
  - does not handle multipart ZIP directly;
  - warns against extracting untrusted archives without inspection;
  - documents resource exhaustion / decompression bomb risks.

## 7z

- py7zr documentation: https://py7zr.readthedocs.io/en/latest/
- py7zr API: https://py7zr.readthedocs.io/en/latest/api.html
- py7zr 7z format description: https://py7zr.readthedocs.io/en/stable/archive_format.html
  - `SevenZipFile` supports creation/extraction/testing;
  - password-protected 7z is supported;
  - multi-volume input can be presented as a joined stream/file and py7zr also documents multi-volume workflows;
  - `testzip()` validates member CRCs when present.

## AES ZIP

- pyzipper project page: https://pypi.org/project/pyzipper/
  - WinZip AES compatible ZIP read/write;
  - AES strength 128/192/256 bits;
  - default AES strength is 256 bits.

## Security design

- Python `zipfile` extraction warnings and decompression pitfalls:
  https://docs.python.org/3/library/zipfile.html
- Python `tarfile` extraction-filter security guidance (applied here as general archive hardening principles):
  https://docs.python.org/3/library/tarfile.html

The implementation deliberately does not trust filename extensions, does not persist archive passwords, preflights member paths/types/sizes/ratios, rejects links and case-folding collisions, verifies package sidecar SHA-256 before joining split parts, extracts to a sibling staging directory, verifies the extracted tree, then commits atomically.
