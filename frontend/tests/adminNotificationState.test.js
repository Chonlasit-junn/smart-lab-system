import test from "node:test";
import assert from "node:assert/strict";
import {
  adminNotificationStateKey,
  readAdminNotificationState,
  writeAdminNotificationState,
} from "../src/utils/adminNotificationState.js";

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
}

test("Admin notification state is scoped to the normalized account email", () => {
  assert.equal(
    adminNotificationStateKey(" Admin@Example.test "),
    adminNotificationStateKey("admin@example.test"),
  );
  assert.notEqual(
    adminNotificationStateKey("admin@example.test"),
    adminNotificationStateKey("other@example.test"),
  );
});

test("Admin notification state stores read and dismissed IDs and tolerates invalid storage", () => {
  const storage = createStorage();
  writeAdminNotificationState(storage, "admin@example.test", {
    dismissed: ["ticket:8"],
    seen: ["ticket:8", "guest-approval:3"],
  });
  assert.deepEqual(readAdminNotificationState(storage, "ADMIN@example.test"), {
    dismissed: ["ticket:8"],
    seen: ["ticket:8", "guest-approval:3"],
  });

  const brokenStorage = createStorage({ [adminNotificationStateKey("admin@example.test")]: "not-json" });
  assert.deepEqual(readAdminNotificationState(brokenStorage, "admin@example.test"), {
    dismissed: [],
    seen: [],
  });
});
