import test from "node:test";
import assert from "node:assert/strict";
import { blacklistFormError, serializeBlacklistForm } from "../src/utils/blacklistPolicy.js";

test("program rules retain explicit matching names and legacy rule types", () => {
  const form = { app_name: "Star Rail", description: "", match_type: "process_name", match_value: "StarRail.exe" };
  assert.equal(blacklistFormError(form), null);
  assert.equal(blacklistFormError({ ...form, app_name: " " }), "admin.appNameRequired");
  assert.equal(serializeBlacklistForm(form).match_value, "StarRail.exe");
  assert.equal(serializeBlacklistForm({ ...form, match_value: "" }).match_value, "Star Rail");
  assert.equal(serializeBlacklistForm({ ...form, match_type: "exe_path", match_value: "C:\\Games\\StarRail.exe" }).match_type, "exe_path");
});
