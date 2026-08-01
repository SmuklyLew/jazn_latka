# Final implementation notes

The implementation intentionally keeps legacy CLI JSONL finalization available, but the private MCP path is now preferred because it prevents the host from copying mutable contract fields. Both paths terminate in the same runtime finalization and persistence code.

No version number was changed. No private memory, runtime workspace, token, package archive, or database was committed. Package integrity and source provenance files were not edited manually.
