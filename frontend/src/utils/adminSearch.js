import { formatDate } from "./dateFormat.js";

function normalizeQuery(query) {
  return String(query ?? "").trim().toLocaleLowerCase();
}

export function filterAdminReservations(reservations, query, locale) {
  const normalizedQuery = normalizeQuery(query);
  if (!normalizedQuery) return reservations;

  return reservations.filter((row) => {
    const userName = `${row.user?.first_name || ""} ${row.user?.last_name || ""}`;
    const searchableText = [
      row.id,
      userName,
      row.lab?.code,
      row.lab?.name,
      row.booking_date,
      formatDate(row.booking_date, locale, { fallback: "" }),
      row.start_time,
      row.end_time,
      row.status,
      row.purpose,
      row.total_participants,
    ].filter(Boolean).join(" ").toLocaleLowerCase();
    return searchableText.includes(normalizedQuery);
  });
}

export function filterLabsBySearch(labs, query) {
  const normalizedQuery = normalizeQuery(query);
  if (!normalizedQuery) return labs;

  return labs.filter((lab) =>
    [lab.code, lab.name, lab.location]
      .filter(Boolean)
      .join(" ")
      .toLocaleLowerCase()
      .includes(normalizedQuery),
  );
}
