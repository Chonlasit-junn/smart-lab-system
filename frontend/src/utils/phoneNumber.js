export function normalizePhoneInput(value) {
  return String(value ?? "").replace(/\D/g, "").slice(0, 15);
}

export function isValidPhoneNumber(value) {
  return /^\d{9,15}$/.test(String(value ?? ""));
}
