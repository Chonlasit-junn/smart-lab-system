import assert from 'node:assert/strict';
import test from 'node:test';
import { passwordResetError, passwordResetLocales } from '../src/utils/passwordReset.js';

test('reset password validates confirmation and bcrypt byte limits in both languages', () => {
  for (const t of Object.values(passwordResetLocales)) {
    assert.equal(passwordResetError('long-password', 'long-password', t), '');
    assert.equal(passwordResetError('short', 'short', t), t.passwordInvalid);
    assert.equal(passwordResetError(' '.repeat(8), ' '.repeat(8), t), t.passwordInvalid);
    assert.equal(passwordResetError('long-password', 'different', t), t.passwordMismatch);
    assert.equal(passwordResetError('ก'.repeat(24), 'ก'.repeat(24), t), '');
    assert.equal(passwordResetError('ก'.repeat(25), 'ก'.repeat(25), t), t.passwordInvalid);
    assert.equal(passwordResetError('😀'.repeat(4), '😀'.repeat(4), t), t.passwordInvalid);
    assert.equal(passwordResetError('😀'.repeat(8), '😀'.repeat(8), t), '');
  }
});

test('recovery translations reuse OTP errors and provide separate recovery wording', () => {
  for (const t of Object.values(passwordResetLocales)) {
    for (const key of ['notice', 'reset', 'success', 'otpExpired', 'otpReplaced', 'otpAttemptsExceeded', 'otpResend']) {
      assert.equal(typeof t[key], 'string');
      assert.ok(t[key].length > 0);
    }
  }
});
