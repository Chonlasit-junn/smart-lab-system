import test from "node:test";
import assert from "node:assert/strict";
import { blacklistFormError, normalizeWebsiteDomain, serializeBlacklistForm } from "../src/utils/blacklistPolicy.js";

test("website URLs are reduced to a canonical domain before sending", () => {
  assert.equal(normalizeWebsiteDomain("https://EXAMPLE.com:443/private?q=secret#token"), "example.com");
  assert.equal(normalizeWebsiteDomain("sub.example.com/path"), "sub.example.com");
  assert.equal(normalizeWebsiteDomain("https://bücher.example"), "xn--bcher-kva.example");
});

test("rejects non-web schemes, credentials, search text and malformed domains", () => {
  for (const value of ["chrome://settings", "file:///secret", "javascript:alert(1)",
    "https://user:pass@example.com", "not a URL", "https://bad..example.com", "example.com:bad",
    "https://example.com\\@evil.com", "*.example.com"]) {
    assert.equal(normalizeWebsiteDomain(value), null, value);
  }
});

test("website rules require an explicit domain rather than guessing from display name", () => {
  const form = { app_name: "Example", description: "", match_type: "website_domain", match_value: "" };
  assert.equal(blacklistFormError(form), "admin.websiteDomainRequired");
  assert.equal(blacklistFormError({ ...form, match_value: "not a website" }), "admin.websiteDomainInvalid");
  assert.equal(blacklistFormError({ ...form, match_value: "example.com" }), null);
  assert.equal(blacklistFormError({ ...form, app_name: " " }), "admin.appNameRequired");
});

test("website payload omits private URL parts without changing the display name", () => {
  const form = { app_name: " Example site ", description: " Test ", match_type: "website_domain",
    match_value: "https://EXAMPLE.com/private?secret=1" };
  assert.deepEqual(serializeBlacklistForm(form), {
    app_name: "Example site", description: "Test", match_type: "website_domain", match_value: "example.com",
  });
  assert.equal(form.match_value, "https://EXAMPLE.com/private?secret=1");
});

test("program rules retain explicit matching names and legacy rule types", () => {
  const form = { app_name: "Star Rail", description: "", match_type: "process_name", match_value: "StarRail.exe" };
  assert.equal(serializeBlacklistForm(form).match_value, "StarRail.exe");
  assert.equal(serializeBlacklistForm({ ...form, match_value: "" }).match_value, "Star Rail");
  assert.equal(serializeBlacklistForm({ ...form, match_type: "exe_path", match_value: "C:\\Games\\StarRail.exe" }).match_type, "exe_path");
});
