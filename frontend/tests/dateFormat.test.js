import assert from "node:assert/strict";
import test from "node:test";

import { formatDate, formatDateTime } from "../src/utils/dateFormat.js";

test("formats English dates as day/month/year even when en-US is requested", () => {
  assert.equal(formatDate("2026-09-19", "en-US"), "19/09/2026");
});

test("formats Thai dates as day/month/year without shifting date-only values", () => {
  assert.match(formatDate("2026-09-19", "th-TH"), /^19\/09\/2569$/);
});

test("keeps the day/month/year order on date-time values", () => {
  assert.match(formatDateTime("2026-09-19T14:30:00", "en-US"), /^19\/09\/2026 \d{2}:\d{2}$/);
  assert.equal(formatDate("not-a-date", "en-GB", { fallback: "-" }), "-");
});
