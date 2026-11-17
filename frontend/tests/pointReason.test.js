import assert from "node:assert/strict";
import test from "node:test";
import { shouldDisplayPointLog } from "../src/utils/pointReason.js";

test("hides zero point logs without a reason", () => {
  assert.equal(shouldDisplayPointLog({ change: 0, reason: null }), false);
  assert.equal(shouldDisplayPointLog({ change: "0", reason: "  " }), false);
});

test("keeps point logs with a reason or a nonzero change", () => {
  assert.equal(shouldDisplayPointLog({ change: 0, reason: "late_cancel" }), true);
  assert.equal(shouldDisplayPointLog({ change: -5, reason: null }), true);
  assert.equal(shouldDisplayPointLog({ change: 5, reason: null }), true);
});

test("keeps point logs without a usable change value", () => {
  assert.equal(shouldDisplayPointLog({ reason: null }), true);
});
