import test from 'node:test';
import assert from 'node:assert/strict';
import { isValidNewPassword } from '../src/utils/passwordPolicy.js';
import { passwordResetError } from '../src/utils/passwordReset.js';
import { registerLocales } from '../src/utils/locales.js';
import { isOtpError, otpErrorMessage } from '../src/utils/registrationOtp.js';

test('registration and password reset enforce one shared policy; symbols remain optional', () => {
  for (const value of ['Password1', 'Password1!', 'A1bcdefg', `A1${'x'.repeat(70)}`]) {
    assert.equal(isValidNewPassword(value), true);
    for (const t of Object.values(registerLocales)) assert.equal(passwordResetError(value, value, t), '');
  }
  for (const value of ['', 'short', 'password1', 'Password', 'Password 1', 'Password1ก',
    `A1${'x'.repeat(71)}`]) {
    assert.equal(isValidNewPassword(value), false);
    for (const t of Object.values(registerLocales)) assert.equal(passwordResetError(value, value, t), t.passwordInvalid);
  }
});

test('registration password errors are localized without being treated as OTP expiry', () => {
  const messages = [
    'Password must be 8 or more characters and at most 72 UTF-8 bytes.',
    'Password must be at least 8 characters, include an uppercase letter, and at most 72 UTF-8 bytes.',
    'Password must be 8-72 printable ASCII characters, include an uppercase letter and a number; symbols are optional and spaces are not allowed.',
  ];
  for (const detail of messages) {
    const error = { response: { data: { detail } } };
    for (const t of Object.values(registerLocales)) assert.equal(otpErrorMessage(error, t, 'fallback'), t.passwordInvalid);
    assert.equal(isOtpError(error), false);
  }
  const validationError = { response: { data: { detail: [{ loc: ['body', 'new_password'], msg: 'Password must include an uppercase letter.' }] } } };
  for (const t of Object.values(registerLocales)) assert.equal(otpErrorMessage(validationError, t, 'fallback'), t.passwordInvalid);
});
