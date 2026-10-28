import assert from 'node:assert/strict';
import test from 'node:test';
import { loginLocales } from '../src/utils/locales.js';
import { loginFeedback } from '../src/utils/loginFeedback.js';

test('login distinguishes approval, disabled account, rate limit and invalid credentials in both languages', () => {
  for (const t of Object.values(loginLocales)) {
    const error = (status, detail) => ({ response: { status, data: { detail } } });
    assert.deepEqual(loginFeedback(error(403, 'Your account is pending admin approval.'), t), { pending: true, message: t.pendingMsg });
    assert.deepEqual(loginFeedback(error(403, 'This account is not active.'), t), { pending: false, message: t.inactiveMsg });
    assert.equal(loginFeedback(error(401, 'Invalid email or password.'), t).message, t.invalidMsg);
    assert.equal(loginFeedback({}, t).message, t.unavailableMsg);
    assert.equal(loginFeedback(error(500, 'private backend details'), t).message, t.unavailableMsg);
    assert.ok(t.rateLimited);
    assert.equal(loginFeedback({ response: { status: 429, headers: { 'retry-after': '300' } } }, t).message, t.rateLimited.replace('{seconds}', '300'));
  }
});

test('stored API error can be rendered again in the selected language', () => {
  const error = { response: { status: 429 } };
  assert.notEqual(loginFeedback(error, loginLocales.th).message, loginFeedback(error, loginLocales.en).message);
});
