import assert from 'node:assert/strict';
import test from 'node:test';
import { registerLocales } from '../src/utils/locales.js';
import { isOtpError, otpDeadlines, otpErrorMessage, requiresNewOtp, retrySeconds, secondsUntil, shouldShowRegistrationOtpControls } from '../src/utils/registrationOtp.js';

test('OTP deadlines use remaining server durations, not a client/server clock comparison', () => {
  assert.deepEqual(otpDeadlines({ expires_in_seconds: 590, retry_after_seconds: 50 }, 1000), {
    expiresAt: 591000, resendAt: 51000,
  });
  assert.equal(secondsUntil(2000, 1001), 1);
  assert.equal(secondsUntil(2000, 2000), 0);
  assert.equal(secondsUntil(2000, 5000), 0);
});

test('expiry and exhausted-attempt responses are translated in Thai and English', () => {
  for (const t of Object.values(registerLocales)) {
    const error = { response: { data: { detail: 'OTP expired. Please request a new code.' } } };
    assert.equal(otpErrorMessage(error, t, 'fallback'), t.otpExpired);
    assert.equal(isOtpError(error), true);
    assert.equal(requiresNewOtp(error), true);
    error.response.data.detail = 'Too many OTP attempts. Please wait and request a new code.';
    assert.equal(otpErrorMessage(error, t, 'fallback'), t.otpAttemptsExceeded);
  }
});

test('unknown validation shapes are safe and normal API string errors remain supported', () => {
  assert.equal(otpErrorMessage({ response: { data: { detail: [{ msg: 'invalid' }] } } }, {}, 'fallback'), 'fallback');
  assert.equal(otpErrorMessage({ response: { data: { detail: 'Custom API error' } } }, {}, 'fallback'), 'Custom API error');
  assert.equal(isOtpError({}), false);
  assert.equal(requiresNewOtp({ response: { data: { detail: 'Invalid OTP. Please try again.' } } }), false);
  assert.equal(otpErrorMessage({ response: { data: { detail: '__proto__' } } }, {}, 'fallback'), '__proto__');
});

test('cooldown follows Retry-After and falls back safely', () => {
  assert.equal(retrySeconds({ response: { headers: { 'retry-after': '540' } } }), 540);
  assert.equal(retrySeconds({ response: { headers: { 'retry-after': 'not-a-number' } } }), 60);
  assert.equal(retrySeconds({}), 60);
});

test('registration OTP countdown and resend controls are limited to the verification step', () => {
  assert.equal(shouldShowRegistrationOtpControls(1), false);
  assert.equal(shouldShowRegistrationOtpControls(2), true);
  assert.equal(shouldShowRegistrationOtpControls(3), false);
  assert.equal(shouldShowRegistrationOtpControls(4), false);
});
