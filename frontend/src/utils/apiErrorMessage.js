const STATUS_TRANSLATION_KEYS = {
  401: "common.apiErrorSessionExpired",
  403: "common.apiErrorPermissionDenied",
  404: "common.apiErrorNotFound",
  409: "common.apiErrorConflict",
  422: "common.apiErrorInvalidRequest",
  429: "common.apiErrorRateLimited",
};

const DETAIL_TRANSLATION_KEYS = {
  "This time slot has already passed.": "user.timePassed",
  "Must book at least 2 hours in advance.": "user.requiresNotice",
  "Cannot book more than 2 days in advance.": "user.advanceBooking",
  "Time slot conflicts with a scheduled class.": "user.reservedForClass",
  "You already have an upcoming reservation. Cancel it before booking another.": "user.upcomingBookingLimitReached",
  "Booking is unavailable while the account has an active penalty.": "user.bookingBlockedByPolicy",
  "Guest account must be approved before requesting points.": "user.pointRequestGuestApproval",
  "Admins do not need to request points.": "user.adminCannotRequestPoints",
};

export function getApiErrorMessage(error, translate, fallbackMessage) {
  const detail = error?.response?.data?.detail;
  const detailMessage = typeof detail === "string" ? detail : detail?.message;

  if (typeof detailMessage === "string") {
    const normalizedDetail = detailMessage.trim();
    if (Object.hasOwn(DETAIL_TRANSLATION_KEYS, normalizedDetail)) {
      return translate(DETAIL_TRANSLATION_KEYS[normalizedDetail]);
    }

    const remainingSeats = detailMessage.match(/^Not enough seats available\. \((\d+) seats left\)$/);
    if (remainingSeats) return `${translate("user.seatsLeft")}: ${remainingSeats[1]}`;

    const currentPoints = detailMessage.match(/^Point requests are available only when your score is 0 \(current: (\d+)\)\.$/);
    if (currentPoints) {
      return translate("user.pointRequestOnlyAtZero").replace("{points}", currentPoints[1]);
    }
  }

  const status = error?.response?.status;
  if (!error?.response) return translate("common.apiErrorNetwork");
  if (status >= 500) return translate("common.apiErrorServer");

  const translationKey = STATUS_TRANSLATION_KEYS[status];
  if (translationKey) return translate(translationKey);

  return fallbackMessage || translate("common.loadFailed");
}
