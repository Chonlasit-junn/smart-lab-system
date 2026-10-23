import assert from 'node:assert/strict';
import test from 'node:test';
import { registerLocales, translateLocaleMessage } from '../src/utils/locales.js';
import { isValidPhoneNumber, normalizePhoneInput } from '../src/utils/phoneNumber.js';
import { isPendingUser } from '../src/pages/verifyUsersUtils.js';
import { canSwitchAdminMode, getAdminReturnPath } from '../src/utils/adminModeSwitch.js';

test('phone input strips pasted text and limits accepted digit count', () => {
  assert.equal(normalizePhoneInput('user@example.com'), '');
  assert.equal(normalizePhoneInput('+66 (81) 234-5678'), '66812345678');
  assert.equal(normalizePhoneInput('1'.repeat(20)).length, 15);
  assert.equal(isValidPhoneNumber('0812345678'), true);
  assert.equal(isValidPhoneNumber('12345678'), false);
  assert.equal(isValidPhoneNumber('user123456789'), false);
});

test('registration feedback text switches language with the selected locale', () => {
  const english = registerLocales.en.otpVerified;
  assert.equal(
    translateLocaleMessage(english, registerLocales.en, registerLocales.th),
    registerLocales.th.otpVerified,
  );
  assert.equal(
    translateLocaleMessage('Account Name', registerLocales.en, registerLocales.th),
    'Account Name',
  );
});

test('a rejected guest is considered complete only after it disappears from pending users', () => {
  assert.equal(isPendingUser([{ id: 7 }], '7'), true);
  assert.equal(isPendingUser([], 7), false);
  assert.equal(isPendingUser(null, 7), false);
});

test('only admin accounts can switch modes and return paths stay within admin pages', () => {
  assert.equal(canSwitchAdminMode({ roleName: 'admin' }), true);
  assert.equal(canSwitchAdminMode({ roleName: 'student' }), false);
  assert.equal(canSwitchAdminMode(null), false);
  assert.equal(getAdminReturnPath('/manage-labs'), '/manage-labs');
  assert.equal(getAdminReturnPath('/admin/points'), '/admin/points');
  assert.equal(getAdminReturnPath('/booking'), '/admin');
  assert.equal(getAdminReturnPath('https://example.com'), '/admin');
});
