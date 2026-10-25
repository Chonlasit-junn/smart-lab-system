import { getLabNowParts } from "./labTime.js";

export const REPORT_MAX_DAYS = 31;
const DAY_MS = 86_400_000;

export function initialReportDates(now = new Date()) {
  const { year, month, day } = getLabNowParts(now);
  const dateTo = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  const start = new Date(`${dateTo}T00:00:00Z`);
  start.setUTCDate(start.getUTCDate() - 6);
  return { dateFrom: start.toISOString().slice(0, 10), dateTo };
}

export function reportDateError(dateFrom, dateTo) {
  const parse = (value) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return NaN;
    const parsed = Date.parse(`${value}T00:00:00Z`);
    return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value ? parsed : NaN;
  };
  const start = parse(dateFrom);
  const end = parse(dateTo);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "dateRequired";
  if (end < start || (end - start) / DAY_MS >= REPORT_MAX_DAYS) return "dateRange";
  return "";
}

export function usageReportParams({ dateFrom, dateTo, labId, deviceId, userId }, language) {
  const params = { date_from: dateFrom, date_to: dateTo, language };
  for (const [key, value] of [["lab_id", labId], ["device_id", deviceId], ["user_id", userId]]) {
    if (value) params[key] = Number(value);
  }
  return params;
}

export async function reportErrorKey(error) {
  let data = error.response?.data;
  if (data instanceof Blob) {
    try { data = JSON.parse(await data.text()); } catch { data = null; }
  }
  const codes = { REPORT_DATE_RANGE: "dateRange", REPORT_TOO_LARGE: "tooLarge", REPORT_BUSY: "busy", REPORT_FILTER_NOT_FOUND: "filterMissing" };
  if (codes[data?.detail]) return codes[data.detail];
  if ([401, 403].includes(error.response?.status)) return "accessDenied";
  return "exportFailed";
}

export function saveReportBlob(blob, filename, { document, URL, setTimeout } = window) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  try {
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
  } finally {
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
