import assert from 'node:assert/strict';
import test from 'node:test';
import { passwordResetError, passwordResetLocales, passwordResetRequirements, isValidPasswordReset } from '../src/utils/passwordReset.js';

test('reset password validates confirmation and bcrypt byte limits in both languages', () => {
  for (const t of Object.values(passwordResetLocales)) {
    assert.equal(passwordResetError('Password1', 'Password1', t), '');
    assert.equal(passwordResetError('Password1!', 'Password1!', t), '');
    assert.equal(passwordResetError('password1', 'password1', t), t.passwordInvalid);
    assert.equal(passwordResetError('Password', 'Password', t), t.passwordInvalid);
    assert.equal(passwordResetError('short', 'short', t), t.passwordInvalid);
    assert.equal(passwordResetError('Password 1', 'Password 1', t), t.passwordInvalid);
    assert.equal(passwordResetError('Password1ก', 'Password1ก', t), t.passwordInvalid);
    assert.equal(passwordResetError('Password1', 'different', t), t.passwordMismatch);
    assert.equal(passwordResetError(`A1${'x'.repeat(70)}`, `A1${'x'.repeat(70)}`, t), '');
    assert.equal(passwordResetError(`A1${'x'.repeat(71)}`, `A1${'x'.repeat(71)}`, t), t.passwordInvalid);
  }
});

test('password checklist begins unchecked and marks each rule independently', () => {
  assert.deepEqual(passwordResetRequirements(''), {
    minLength: false, uppercase: false, number: false, allowedCharacters: true, maxLength: true,
  });
  assert.deepEqual(passwordResetRequirements('Password'), {
    minLength: true, uppercase: true, number: false, allowedCharacters: true, maxLength: true,
  });
  assert.equal(isValidPasswordReset('Password1'), true);
  assert.equal(isValidPasswordReset('Password1!'), true);
  assert.equal(isValidPasswordReset('Password1ก'), false);
});

test('recovery translations reuse OTP errors and provide separate recovery wording', () => {
  for (const t of Object.values(passwordResetLocales)) {
    for (const key of ['notice', 'reset', 'success', 'otpExpired', 'otpReplaced', 'otpAttemptsExceeded', 'otpResend', 'passwordMinLength', 'passwordUppercase', 'passwordNumber', 'passwordCharacters', 'passwordMaxLength']) {
      assert.equal(typeof t[key], 'string');
      assert.ok(t[key].length > 0);
    }
  }
});
