import assert from "node:assert/strict";
import test from "node:test";

import { buildBookingPayload } from "../src/utils/bookingPayload.js";

test("keeps the persisted default booking purpose independent from UI language", () => {
  assert.deepEqual(
    buildBookingPayload({ labId: 4, bookingDate: "2026-10-17", slotNumber: 2 }),
    {
      lab_id: 4,
      booking_date: "2026-10-17",
      slot_number: 2,
      purpose: "General use",
      total_participants: 1,
    },
  );
});
