import assert from "node:assert/strict";
import test from "node:test";

import {
  getLabDateReference,
  getLabNowParts,
  getLabNowReference,
} from "../src/utils/labTime.js";

test("converts an instant to the Lab calendar and clock", () => {
  const instant = new Date("2026-09-21T17:30:00.000Z");

  assert.deepEqual(getLabNowParts(instant), {
    year: 2026,
    month: 9,
    day: 22,
    hour: 0,
    minute: 30,
    second: 0,
  });
  assert.equal(getLabNowReference(instant), Date.UTC(2026, 8, 22, 0, 30));
});

test("creates a timezone-independent reference for a Lab slot", () => {
  assert.equal(
    getLabDateReference(2026, 8, 22, 8, 40),
    Date.UTC(2026, 8, 22, 8, 40),
  );
});
