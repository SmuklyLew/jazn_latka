export function valueState(value) {
  if (value === true) return "ready";
  if (value === false) return "down";
  if (value === null || value === undefined || value === "") return "unknown";
  const normalized = String(value).toLowerCase();
  if (["ready", "active_ready", "active_trusted", "ok", "verified"].includes(normalized)) return "ready";
  if (normalized.includes("degraded") || normalized.includes("partial") || normalized.includes("pending")) return "degraded";
  if (normalized.includes("inactive") || normalized.includes("blocked") || normalized.includes("failed") || normalized.includes("down")) return "down";
  return "unknown";
}

export function formatValue(value) {
  if (value === true) return "tak";
  if (value === false) return "nie";
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "—";
  return String(value);
}

export function rowsForOverview(snapshot = {}) {
  const runtime = snapshot.runtime ?? {};
  const memory = snapshot.memory ?? {};
  const visible = snapshot.visible_turn ?? {};
  const nlp = snapshot.nlp ?? {};
  const rest = snapshot.rest ?? {};
  return {
    runtime: [
      ["stan", runtime.operational_state ?? runtime.active_state],
      ["daemon", runtime.active_state],
      ["endpoint", runtime.endpoint_reachable],
      ["PID żyje", runtime.pid_alive],
      ["runtime core", runtime.runtime_core_ready],
      ["system fully ready", runtime.system_fully_ready],
      ["heartbeat [s]", runtime.heartbeat_age_seconds],
    ],
    memory: [
      ["transactional", memory.transactional_ready],
      ["search", memory.search_ready],
      ["search status", memory.search_status],
      ["legacy search", memory.legacy_search_ready],
      ["continuity", memory.continuity_ready],
    ],
    turn: [
      ["status", visible.status],
      ["accepted final wymagany", visible.accepted_visible_turn_required],
      ["liveness wystarcza", visible.daemon_liveness_sufficient],
      ["ready", visible.ready],
    ],
    capability: [
      ["NLP core", nlp.core_ready],
      ["NLP enhanced", nlp.enhanced_ready],
      ["NLP status", nlp.enhanced_status],
      ["rest scheduler", rest.scheduler_ready],
      ["rest running", rest.scheduler_running],
      ["rest status", rest.scheduler_status],
    ],
  };
}

export function connectionState(snapshot = {}) {
  const runtime = snapshot.runtime ?? {};
  if (runtime.active_state === "active_trusted" && runtime.endpoint_reachable === true) return "ready";
  if (runtime.endpoint_reachable === true) return "degraded";
  if (runtime.endpoint_reachable === false || String(runtime.active_state ?? "").startsWith("inactive")) return "down";
  return "unknown";
}
