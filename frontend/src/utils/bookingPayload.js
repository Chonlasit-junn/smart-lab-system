export const DEFAULT_BOOKING_PURPOSE = "General use";

export function buildBookingPayload({ labId, bookingDate, slotNumber }) {
  return {
    lab_id: labId,
    booking_date: bookingDate,
    slot_number: slotNumber,
    purpose: DEFAULT_BOOKING_PURPOSE,
    total_participants: 1,
  };
}
