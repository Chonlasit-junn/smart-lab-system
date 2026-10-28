import { retrySeconds } from './registrationOtp.js';

export function loginFeedback(error, translations) {
  const status = error?.response?.status;
  const detail = error?.response?.data?.detail;
  if (status === 429) {
    return { pending: false, message: translations.rateLimited.replace('{seconds}', retrySeconds(error)) };
  }
  if (status === 403 && detail === 'Your account is pending admin approval.') {
    return { pending: true, message: translations.pendingMsg };
  }
  if (status === 403 && detail === 'This account is not active.') {
    return { pending: false, message: translations.inactiveMsg };
  }
  return { pending: false, message: status === 401 ? translations.invalidMsg : translations.unavailableMsg };
}
