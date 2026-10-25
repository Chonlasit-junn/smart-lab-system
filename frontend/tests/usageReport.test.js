import assert from "node:assert/strict";
import test from "node:test";
import { initialReportDates, reportDateError, reportErrorKey, saveReportBlob, usageReportParams } from "../src/utils/usageReport.js";
import { reportLocales } from "../src/utils/reportLocales.js";
import { getAdminReturnPath } from "../src/utils/adminModeSwitch.js";

test("defaults to seven Bangkok calendar days even near UTC midnight", () => {
  assert.deepEqual(initialReportDates(new Date("2026-10-24T18:00:00Z")), { dateFrom: "2026-10-19", dateTo: "2026-10-25" });
});

test("validates real calendar dates, inclusive 31-day range and reversed dates", () => {
  assert.equal(reportDateError("2026-10-01", "2026-10-31"), "");
  assert.equal(reportDateError("2026-10-01", "2026-11-01"), "dateRange");
  assert.equal(reportDateError("2026-10-02", "2026-10-01"), "dateRange");
  assert.equal(reportDateError("2026-02-30", "2026-03-01"), "dateRequired");
  assert.equal(reportDateError("", "2026-10-01"), "dateRequired");
});

test("sends all selected filters without UI pagination or timezone conversion", () => {
  assert.deepEqual(usageReportParams({ dateFrom: "2026-10-01", dateTo: "2026-10-02", labId: "2", deviceId: "3", userId: 4 }, "th"),
    { date_from: "2026-10-01", date_to: "2026-10-02", language: "th", lab_id: 2, device_id: 3, user_id: 4 });
  assert.deepEqual(usageReportParams({ dateFrom: "2026-10-01", dateTo: "2026-10-02", labId: "", deviceId: "" }, "en"),
    { date_from: "2026-10-01", date_to: "2026-10-02", language: "en" });
});

test("decodes JSON errors received as blobs and maps safe localized feedback", async () => {
  assert.equal(await reportErrorKey({ response: { data: new Blob([JSON.stringify({ detail: "REPORT_TOO_LARGE" })]) } }), "tooLarge");
  assert.equal(await reportErrorKey({ response: { status: 403 } }), "accessDenied");
  assert.equal(await reportErrorKey({ response: { data: new Blob(["not-json"]) } }), "exportFailed");
  assert.equal(await reportErrorKey({ response: { data: { detail: "REPORT_BUSY" } } }), "busy");
});

test("downloads the XLSX blob and releases temporary browser resources", () => {
  const calls = [];
  const link = { click: () => calls.push("click"), remove: () => calls.push("remove") };
  const environment = {
    document: { createElement: () => link, body: { appendChild: () => calls.push("append") } },
    URL: { createObjectURL: () => "blob:test", revokeObjectURL: (value) => calls.push(value) },
    setTimeout: (callback) => callback(),
  };
  saveReportBlob(new Blob(["file"]), "report.xlsx", environment);
  assert.equal(link.download, "report.xlsx");
  assert.deepEqual(calls, ["append", "click", "remove", "blob:test"]);
});

test("reports remain within admin return paths and both locales cover every UI message", () => {
  assert.equal(getAdminReturnPath("/admin/reports"), "/admin/reports");
  assert.deepEqual(Object.keys(reportLocales.th).sort(), Object.keys(reportLocales.en).sort());
  assert.notEqual(reportLocales.th.title, reportLocales.en.title);
});
