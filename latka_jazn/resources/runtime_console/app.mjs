import { connectionState, formatValue, rowsForOverview, valueState } from "./model.mjs";

const byId = (id) => document.getElementById(id);
const refreshButton = byId("refresh");
let lastOverview = null;

function renderRows(target, rows) {
  target.replaceChildren();
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = formatValue(value);
    dd.className = `value-${valueState(value)}`;
    target.append(dt, dd);
  }
}

function renderConnection(snapshot, forcedState = null) {
  const state = forcedState ?? connectionState(snapshot);
  const dot = byId("connection-dot");
  dot.className = `dot ${state}`;
  const labels = {
    ready: "połączenie live",
    degraded: "połączenie zdegradowane",
    down: "runtime niedostępny",
    unknown: "stan połączenia nieznany",
  };
  byId("connection-label").textContent = labels[state] ?? labels.unknown;
}

function renderLive(snapshot) {
  renderConnection(snapshot);
  const runtime = snapshot.runtime ?? {};
  if (runtime.active_state) {
    byId("runtime-state").textContent = formatValue(runtime.active_state);
  }
  if (snapshot.runtime_version) {
    byId("runtime-version").textContent = snapshot.runtime_version;
  }
  byId("generated-at").textContent = snapshot.generated_at_utc ?? "—";
}

function renderOverview(snapshot) {
  lastOverview = snapshot;
  renderLive(snapshot);
  const rows = rowsForOverview(snapshot);
  renderRows(byId("runtime-card"), rows.runtime);
  renderRows(byId("memory-card"), rows.memory);
  renderRows(byId("turn-card"), rows.turn);
  renderRows(byId("capability-card"), rows.capability);
  byId("truth-boundary").textContent = snapshot.truth_boundary ?? "";
  byId("raw-json").textContent = JSON.stringify(snapshot, null, 2);
}

async function refreshOverview() {
  refreshButton.disabled = true;
  try {
    const response = await fetch("/api/v1/overview", {
      cache: "no-store",
      mode: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderOverview(await response.json());
  } catch (error) {
    renderConnection(lastOverview ?? {}, "degraded");
    byId("truth-boundary").textContent = `Błąd odczytu overview: ${error}`;
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener("click", refreshOverview);
await refreshOverview();

const events = new EventSource("/api/v1/events");
events.addEventListener("runtime", (event) => {
  try {
    renderLive(JSON.parse(event.data));
  } catch {
    renderConnection(lastOverview ?? {}, "degraded");
  }
});
events.addEventListener("open", () => renderConnection(lastOverview ?? {}, "ready"));
events.addEventListener("error", () => renderConnection(lastOverview ?? {}, "degraded"));
