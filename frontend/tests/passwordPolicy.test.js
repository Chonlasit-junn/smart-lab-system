import test from 'node:test';
import assert from 'node:assert/strict';
import { isValidNewPassword } from '../src/utils/passwordPolicy.js';
import { passwordResetError } from '../src/utils/passwordReset.js';
import { registerLocales } from '../src/utils/locales.js';
import { isOtpError, otpErrorMessage } from '../src/utils/registrationOtp.js';

test('registration and recovery share character/UTF-8 limits without trimming valid passwords', () => {
  for (const value of ['12345678', 'x'.repeat(72), 'ก'.repeat(24), '😀'.repeat(8), ' padded password ']) {
    assert.equal(isValidNewPassword(value), true);
    for (const t of Object.values(registerLocales)) assert.equal(passwordResetError(value, value, t), '');
  }
  for (const value of ['', 'short', ' '.repeat(8), 'x'.repeat(73), 'ก'.repeat(25), '😀'.repeat(4)]) {
    assert.equal(isValidNewPassword(value), false);
    for (const t of Object.values(registerLocales)) assert.equal(passwordResetError(value, value, t), t.passwordInvalid);
  }
});

test('registration password errors are localized without being treated as OTP expiry', () => {
  const error = { response: { data: { detail: 'Password must be 8 or more characters and at most 72 UTF-8 bytes.' } } };
  for (const t of Object.values(registerLocales)) assert.equal(otpErrorMessage(error, t, 'fallback'), t.passwordInvalid);
  assert.equal(isOtpError(error), false);
});
