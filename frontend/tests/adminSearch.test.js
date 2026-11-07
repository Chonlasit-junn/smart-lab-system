import test from "node:test";
import assert from "node:assert/strict";
import { filterAdminReservations, filterLabsBySearch } from "../src/utils/adminSearch.js";

const reservations = [
  {
    id: 12,
    booking_date: "2026-11-07",
    start_time: "08:40",
    status: "reserved",
    purpose: "Research project",
    user: { first_name: "Pakin", last_name: "Noonnak" },
    lab: { code: "LAB01", name: "Smart Lab Center" },
  },
  {
    id: 13,
    booking_date: "2026-11-08",
    start_time: "12:00",
    status: "cancelled",
    purpose: "Class work",
    user: { first_name: "Test", last_name: "User" },
    lab: { code: "LAB02", name: "Media Lab" },
  },
];

test("Admin reservation search filters by user, lab, and purpose case-insensitively", () => {
  assert.deepEqual(filterAdminReservations(reservations, "pakin", "en-US"), [reservations[0]]);
  assert.deepEqual(filterAdminReservations(reservations, "lab02", "en-US"), [reservations[1]]);
  assert.deepEqual(filterAdminReservations(reservations, "CLASS WORK", "en-US"), [reservations[1]]);
});

test("Admin reservation search leaves rows unchanged for a blank query", () => {
  assert.equal(filterAdminReservations(reservations, "  ", "en-US"), reservations);
  assert.deepEqual(filterAdminReservations(reservations, "missing", "en-US"), []);
});

test("Manage Labs search matches code, name, and location", () => {
  const labs = [
    { code: "LAB01", name: "Smart Lab Center", location: "Building 5" },
    { code: "LAB02", name: "Media Room", location: "Building 2" },
  ];
  assert.deepEqual(filterLabsBySearch(labs, "building 2"), [labs[1]]);
  assert.deepEqual(filterLabsBySearch(labs, "SMART LAB"), [labs[0]]);
  assert.equal(filterLabsBySearch(labs, ""), labs);
});
