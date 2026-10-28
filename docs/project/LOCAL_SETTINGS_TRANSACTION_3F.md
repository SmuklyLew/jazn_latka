# 3F — transactional local Studio settings

For roots with `.settings/`, mutable Studio settings belong in
`.settings_local/operator/jazn_run_studio/settings.json`. The legacy file in
`ROOT/workspace_runtime/jazn_run_studio/settings.json` is a **read-only** import
source, never overwritten or adopted from another worktree.

Writes by **cooperating** processes hold a persistent `.lock` sidecar in the
same directory, recheck expected SHA-256 under that lock, write and fsync a
temporary file in that directory, then use `os.replace`. Never unlink the
lock sidecar between writes: otherwise waiting writers may lock a stale inode.

Limitations:
- This does not protect against a malicious or privileged actor concurrently
  renaming parent directories (TOCTOU) on Windows. Code rejects existing
  symlinks/junctions and rechecks paths immediately before replacement.
- Non-cooperating tools editing settings can bypass the lock.
- Python documents POSIX atomic rename on successful `os.replace`; this is
  not a blanket transactional guarantee for every Windows filesystem.
- Legacy SYSTEM configuration update is still a separate transaction; only
  migrated roots use an isolated single-settings-file write.
- Historical `~/.jazn/acceptance` profiles are not automatically adopted or
  destroyed. A deliberate migration needs separate root/instance/heartbeat
  verification.

The patch does not start, stop, restart daemons or alter MEMORY.
