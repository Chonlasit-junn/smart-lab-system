const errorKeys = {
  'Invalid OTP. Please try again.': 'invalidOtp',
  'Invalid or expired OTP.': 'otpExpired',
  'OTP expired. Please request a new code.': 'otpExpired',
  'OTP replaced. Please use the latest code.': 'otpReplaced',
  'Too many OTP attempts. Please wait and request a new code.': 'otpAttemptsExceeded',
  'Please wait before requesting another OTP.': 'otpCooldown',
  'OTP delivery is unavailable. Please try again later.': 'otpDeliveryUnavailable',
  'OTP service is not configured. Please contact support.': 'otpNotConfigured',
};

export function otpErrorMessage(error, translations, fallback) {
  const detail = error?.response?.data?.detail;
  const faceErrors = {
    'No face detected in the image.': 'faceNotDetected',
    'Exactly one face is required.': 'faceSinglePerson',
    'Face is too small. Please move closer to the camera.': 'faceTooSmall',
  };
  if (Object.hasOwn(faceErrors, detail)) return translations[faceErrors[detail]] || fallback;
  if (detail === 'Password must be 8 or more characters and at most 72 UTF-8 bytes.') return translations.passwordInvalid;
  const key = Object.hasOwn(errorKeys, detail) ? errorKeys[detail] : null;
  return key ? translations[key] : typeof detail === 'string' ? detail : fallback;
}

export function isOtpError(error) {
  return Object.hasOwn(errorKeys, error?.response?.data?.detail);
}

export function requiresNewOtp(error) {
  const detail = error?.response?.data?.detail;
  return Object.hasOwn(errorKeys, detail)
    && ['otpExpired', 'otpReplaced', 'otpAttemptsExceeded'].includes(errorKeys[detail]);
}

export function retrySeconds(error) {
  const value = Number(error?.response?.headers?.['retry-after']);
  return Number.isFinite(value) && value > 0 ? Math.min(3600, Math.ceil(value)) : 60;
}

export function secondsUntil(deadline, now) {
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}

export function shouldShowRegistrationOtpControls(step) {
  return step === 2;
}

export function otpDeadlines(data, now) {
  const expiry = Number(data?.expires_in_seconds ?? 600);
  const retry = Number(data?.retry_after_seconds ?? 60);
  return {
    expiresAt: now + Math.max(0, Number.isFinite(expiry) ? expiry : 600) * 1000,
    resendAt: now + Math.max(0, Number.isFinite(retry) ? retry : 60) * 1000,
  };
}
