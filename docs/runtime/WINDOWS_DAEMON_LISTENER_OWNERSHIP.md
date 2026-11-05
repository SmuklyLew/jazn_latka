# Windows daemon listener ownership

The canonical `JaznDaemonServer` sets Winsock `SO_EXCLUSIVEADDRUSE` before
binding its TCP socket. Address reuse remains enabled on non-Windows systems;
Windows disables `SO_REUSEADDR`. Failure to obtain an exclusive socket, including
an unavailable exclusive option, aborts construction before daemon capability
state is written. There is no shared-listener fallback.

Windows permits another socket using `SO_REUSEADDR` to bind an occupied address,
with indeterminate connection routing. `SO_EXCLUSIVEADDRUSE`, set before bind,
prevents that address sharing. See Microsoft's
[Winsock ownership guidance](https://learn.microsoft.com/en-us/windows/win32/winsock/using-so-reuseaddr-and-so-exclusiveaddruse)
and [exclusive option reference](https://learn.microsoft.com/en-us/windows/win32/winsock/so-exclusiveaddruse).

Socket ownership is one prerequisite. ROOT, version, process fingerprint,
daemon instance, endpoint identity, heartbeat and conversation readiness remain
separate canonical gates. A listening socket does not certify a Jaźń turn.

Native Windows tests use only fresh synthetic roots and owned random ports.
They check socket options, competing daemons, a competing reusable listener in
both orders, state-write refusal and reopening a cleanly closed unused listener.
They do not certify accepted finalization, real model generation, service
installation or release acceptance. Existing result-read retries and timeouts
are unchanged; any regression result must be reported for its actual source SHA.
