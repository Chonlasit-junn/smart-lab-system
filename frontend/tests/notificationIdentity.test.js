import test from 'node:test';
import assert from 'node:assert/strict';
import { readNotificationToken } from '../src/utils/notificationClient.js';

const token = sub => {
  const bytes = new TextEncoder().encode(JSON.stringify({ sub }));
  return `qa.${btoa(String.fromCharCode(...bytes))}.qa`;
};
function withStorage(storage, verify) {
  const previous = globalThis.window;
  globalThis.window = { localStorage: storage };
  try { verify(); } finally {
    if (previous === undefined) delete globalThis.window;
    else globalThis.window = previous;
  }
}

test('credentials must belong to the displayed account, including Unicode identities', () => {
  for (const email of ['a@example.com', 'ผู้ใช้@ตัวอย่าง.ไทย']) {
    const credential = token(email);
    withStorage({ getItem: () => credential }, () => {
      assert.equal(readNotificationToken(email), credential);
      assert.equal(readNotificationToken(email.toUpperCase()), credential);
      assert.equal(readNotificationToken('other@example.com'), null);
      assert.equal(readNotificationToken(), credential);
    });
  }
});

test('missing credentials, malformed subjects and disabled storage fail closed', () => {
  for (const value of [null, '', 'not-a-jwt', 'qa.%%%.qa', token(null), token(123)]) {
    withStorage({ getItem: () => value }, () => assert.equal(readNotificationToken('a@example.com'), null));
  }
  withStorage({ getItem() { throw Error('Unavailable'); } }, () => assert.equal(readNotificationToken('a@example.com'), null));
});
