import test from 'node:test';
import assert from 'node:assert/strict';
import { notificationReadKey, readNotificationId, saveNotificationId } from '../src/utils/notificationReadState.js';

const memory = () => {
  const values = new Map();
  return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
};

test('reading account A never marks account B as read and legacy ownerless state is ignored', () => {
  const storage = memory();
  storage.setItem('last_seen_point_log_id', '9000');
  const a = notificationReadKey('A@example.com'), b = notificationReadKey('b@example.com');
  assert.equal(readNotificationId(storage, a), 0);
  assert.equal(readNotificationId(storage, b), 0);
  saveNotificationId(storage, a, 100);
  assert.equal(readNotificationId(storage, b), 0);
  saveNotificationId(storage, b, 20);
  assert.equal(readNotificationId(storage, a), 100);
  assert.equal(readNotificationId(storage, b), 20);
});

test('identity is stable across case/whitespace and counts never move backwards', () => {
  const storage = memory(), key = notificationReadKey('a@example.com');
  assert.equal(notificationReadKey(' A@EXAMPLE.COM '), key);
  assert.equal(saveNotificationId(storage, key, 100), 100);
  assert.equal(saveNotificationId(storage, key, 3), 100);
});

test('missing accounts, invalid storage values and unavailable storage fail safely', () => {
  const storage = memory(), key = notificationReadKey('a@example.com');
  assert.equal(notificationReadKey(undefined), null);
  for (const value of ['NaN', '-1', '1.5', 'Infinity', '9007199254740992']) {
    storage.setItem(key, value);
    assert.equal(readNotificationId(storage, key), 0);
  }
  assert.equal(saveNotificationId(storage, null, 5), 0);
  const unavailable = { getItem() { throw Error('disabled'); }, setItem() { throw Error('disabled'); } };
  assert.equal(readNotificationId(unavailable, key), 0);
  assert.equal(saveNotificationId(unavailable, key, 5), 5);
});
