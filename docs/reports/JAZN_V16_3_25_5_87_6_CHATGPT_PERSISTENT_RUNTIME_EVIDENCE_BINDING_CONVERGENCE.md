# Jaźń v16.3.25.5.87.6 — ChatGPT persistent-runtime evidence binding convergence

## Problem
Strukturalnie poprawny, lecz stary remote-runtime payload mógł wyglądać jak bieżąca trasa po restarcie gatewayu lub daemona.

## Zmiana
Publiczny Streamable HTTP publikuje per-process `gateway_instance_id`, `observed_at_utc` i redagowany binding do `runtime_instance_id`, `runtime_version` oraz `runtime_heartbeat_at_utc`. Publiczny i Secure MCP Tunnel classifier wymagają świeżości, canonical runtime binding i bieżącej host connector/app capability.

MCP pozostaje transportem; tożsamość, pamięć, turn lineage i finalizacja pozostają własnością jednego persistent runtime Jaźni.

## Źródła
- https://blog.modelcontextprotocol.io/posts/2026-07-28/
- https://developers.openai.com/plugins/build/app-quickstart
- https://developers.openai.com/api/docs/guides/tools-connectors-mcp

## Kryteria akceptacji
Brak bindingu, rozbieżna instancja, zła wersja, stary heartbeat lub brak host capability => route false. Pełny świeży binding + transport readiness + host capability => route true.
