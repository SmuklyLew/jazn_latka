# Pack Generator build sources

These modules are build-time sources for the portable two-file Pack Generator.
`tools/build_jazn_pack_generator_bundle.py` embeds their exact bytes together
with the canonical packaging/path modules and records SHA-256 for every source.
The portable distribution remains `jazn_pack_generator.py` plus its settings
JSON; these build sources are not runtime dependencies of the portable tool.
