import test from "node:test";
import assert from "node:assert/strict";
import {
  getInitialTicketReplyStatus,
  getTicketReplyStatus,
  getTicketReplyStatusPresentation,
  getTicketStatusForReply,
} from "../src/utils/ticketStatus.js";

test("supports all reply statuses and maps them to the existing ticket states", () => {
  assert.deepEqual(
    ["received", "in_progress", "resolved"].map(getTicketStatusForReply),
    ["open", "in_progress", "closed"],
  );
  assert.equal(getTicketReplyStatusPresentation("received").color, "warning");
  assert.equal(getTicketReplyStatusPresentation("in_progress").color, "info");
  assert.equal(getTicketReplyStatusPresentation("resolved").color, "success");
});

test("uses the most recent reply status and supports legacy resolution replies", () => {
  assert.equal(
    getInitialTicketReplyStatus({ replies: [{ status: "received" }, { status: "resolved" }] }),
    "resolved",
  );
  assert.equal(getTicketReplyStatus({ is_resolved: true }), "resolved");
  assert.equal(getTicketReplyStatus({ is_resolved: false }), "in_progress");
});

test("maps tickets without replies to their current state", () => {
  assert.equal(getInitialTicketReplyStatus({ status: "closed" }), "resolved");
  assert.equal(getInitialTicketReplyStatus({ status: "in_progress" }), "in_progress");
  assert.equal(getInitialTicketReplyStatus({ status: "open" }), "received");
});
