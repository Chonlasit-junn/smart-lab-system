export function passwordPolicyRequirements(value) {
  const password = typeof value === 'string' ? value : '';
  return {
    minLength: Array.from(password).length >= 8,
    uppercase: /[A-Z]/.test(password),
    number: /[0-9]/.test(password),
    allowedCharacters: /^[\x21-\x7E]*$/.test(password),
    maxLength: new TextEncoder().encode(password).length <= 72,
  };
}

export function isValidNewPassword(value) {
  return typeof value === 'string'
    && Object.values(passwordPolicyRequirements(value)).every(Boolean);
}
