import assert from "node:assert/strict";
import test from "node:test";

import {
  connectionState,
  formatValue,
  rowsForOverview,
  valueState,
} from "../../latka_jazn/resources/runtime_console/model.mjs";

test("runtime console model maps truth states deterministically", () => {
  assert.equal(valueState(true), "ready");
  assert.equal(valueState(false), "down");
  assert.equal(valueState("active_trusted"), "ready");
  assert.equal(valueState("partial_unverified"), "degraded");
  assert.equal(valueState(null), "unknown");
});

test("runtime console uses text-safe scalar formatting", () => {
  assert.equal(formatValue(true), "tak");
  assert.equal(formatValue(false), "nie");
  assert.equal(formatValue(undefined), "—");
  assert.equal(formatValue("<script>alert(1)</script>"), "<script>alert(1)</script>");
});

test("runtime console projects bounded overview rows", () => {
  const rows = rowsForOverview({
    runtime: { active_state: "active_trusted", endpoint_reachable: true },
    memory: { continuity_ready: true },
    visible_turn: { accepted_visible_turn_required: true },
  });
  assert.equal(rows.runtime[1][1], "active_trusted");
  assert.equal(rows.memory.at(-1)[1], true);
  assert.equal(rows.turn[1][1], true);
});

test("runtime console connection state follows runtime evidence, not transport open", () => {
  assert.equal(
    connectionState({ runtime: { active_state: "active_trusted", endpoint_reachable: true } }),
    "ready",
  );
  assert.equal(
    connectionState({ runtime: { active_state: "active_degraded", endpoint_reachable: true } }),
    "degraded",
  );
  assert.equal(
    connectionState({ runtime: { active_state: "inactive", endpoint_reachable: false } }),
    "down",
  );
  assert.equal(connectionState({ runtime: {} }), "unknown");
});
