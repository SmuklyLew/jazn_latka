# Semantic routing completion v15.1.0.3.96

This update closes the seven omissions identified after the voice-continuity patch:

1. dedicated post-update coverage audit route;
2. generic connector/tool context rather than a web-only marker;
3. one controlled regeneration after a forbidden host-voice prefix;
4. daemon-presentation and private-MCP two-phase contract test;
5. generated semantic variants and an independent audit command;
6. runtime identity bump to v15.1.0.3.96-semantic-routing-completion;
7. a separate semantic CI lane plus an explicit human-review boundary.

The retry is deliberately bounded. It applies only when the sole finalization defect is `forbidden_host_voice_prefix`. Hash, binding, timestamp, replay, persistence and other integrity violations remain immediately fail-closed.
