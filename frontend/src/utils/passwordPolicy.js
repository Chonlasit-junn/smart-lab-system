export function isValidNewPassword(value) {
  return typeof value === 'string' && Array.from(value).length >= 8
    && value.trim().length > 0 && new TextEncoder().encode(value).length <= 72;
}
