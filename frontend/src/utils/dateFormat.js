const DATE_PARTS = {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
};

const resolveLocale = (locale) => {
  const requestedLocale = String(locale || "").toLowerCase();
  if (requestedLocale.startsWith("th")) return "th-TH";
  if (requestedLocale.startsWith("en")) return "en-GB";

  if (typeof document !== "undefined") {
    const documentLocale = String(document.documentElement.lang || "").toLowerCase();
    if (documentLocale.startsWith("th")) return "th-TH";
  }

  // en-GB keeps the day/month/year order even before the language provider
  // has finished applying the document language.
  return "en-GB";
};

const parseDate = (value) => {
  if (!value) return null;
  if (value instanceof Date) {
    return new Date(value.getTime());
  }

  const rawValue = String(value);
  const dateOnlyMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(rawValue);
  if (dateOnlyMatch) {
    const [, year, month, day] = dateOnlyMatch;
    return new Date(Number(year), Number(month) - 1, Number(day));
  }

  return new Date(value);
};

export function formatDate(value, locale, { fallback = "—" } = {}) {
  const date = parseDate(value);
  if (!date || Number.isNaN(date.getTime())) return fallback;

  return date.toLocaleDateString(resolveLocale(locale), DATE_PARTS);
}

export function formatDateTime(
  value,
  locale,
  { fallback = "—", includeSeconds = false } = {},
) {
  const date = parseDate(value);
  if (!date || Number.isNaN(date.getTime())) return fallback;

  const resolvedLocale = resolveLocale(locale);
  const formattedDate = date.toLocaleDateString(resolvedLocale, DATE_PARTS);
  const formattedTime = date.toLocaleTimeString(resolvedLocale, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    ...(includeSeconds ? { second: "2-digit" } : {}),
  });

  return `${formattedDate} ${formattedTime}`;
}
