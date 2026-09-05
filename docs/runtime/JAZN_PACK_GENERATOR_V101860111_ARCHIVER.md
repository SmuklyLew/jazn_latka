# Jaźń Pack Generator 10.1.86.0.111 — clean archiver contract

`tools/jazn_pack_generator.py` is a small public launcher. Active maintained
implementation files live under `tools/jazn_pack_generator_app/`.

The generator has one service core and three interfaces: classic text terminal,
cursor terminal TUI, and native Tk/ttk Studio.

Its scope is deliberately limited to archiving:
- SYSTEM — the selected Jaźń folder without the memory boundary and mutable host state;
- MEMORY — the selected/verified memory root;
- SYSTEM+MEMORY — one logical ZIP containing both.

A package is first created as a standard ZIP64 archive and verified with CRC.
If transport splitting is selected and required, that single logical ZIP is
then split byte-for-byte into `.zip.001`, `.002`, ... pieces. The split format
is not claimed to be a native multi-disk ZIP; it is a transport layer and must
be joined before ordinary ZIP tools consume it. SHA-256 is recorded for the
logical ZIP and each part.

Dependency wheelhouses, Python runtimes, platform targets and
`latka_jazn.tools.package_distribution` are outside this tool's scope.
