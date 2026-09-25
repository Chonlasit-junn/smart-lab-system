export const LAB_TIMEZONE = "Asia/Bangkok";

const LAB_DATE_TIME_PARTS = {
  timeZone: LAB_TIMEZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
};

export function getLabNowParts(value = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", LAB_DATE_TIME_PARTS)
    .formatToParts(value)
    .reduce((result, part) => {
      if (part.type !== "literal") result[part.type] = Number(part.value);
      return result;
    }, {});

  return parts;
}

export function getLabCalendarDate(value = new Date()) {
  const { year, month, day } = getLabNowParts(value);
  // Keep the Lab calendar date stable even when the browser is in another
  // timezone or observes daylight-saving changes.
  return new Date(year, month - 1, day, 12, 0, 0, 0);
}

export function getLabDateReference(year, monthIndex, day, hours = 0, minutes = 0) {
  return Date.UTC(year, monthIndex, day, hours, minutes, 0, 0);
}

export function getLabNowReference(value = new Date()) {
  const { year, month, day, hour, minute } = getLabNowParts(value);
  return getLabDateReference(year, month - 1, day, hour, minute);
}
