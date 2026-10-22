import test from 'node:test';
import assert from 'node:assert/strict';
import { createNotificationStore, NOTIFICATION_POLL_MS } from '../src/utils/notificationStore.js';

const flush = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
const log = (id, reason = 'daily_bonus', source_type = null) => ({ id, reason, source_type, change: 1 });
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function fixture() {
  let time = 0, id = 0;
  const timers = new Map(), calls = [];
  const state = { token: 'token-a', visible: true, listener: null, listenCount: 0, unlistenCount: 0 };
  const store = createNotificationStore({
    readToken: () => state.token,
    isVisible: () => state.visible,
    now: () => time,
    delay: (callback, ms) => { timers.set(++id, { at: time + ms, callback }); return id; },
    cancelDelay: timer => timers.delete(timer),
    listen: callback => {
      state.listener = callback; state.listenCount++;
      return () => { state.listener = null; state.unlistenCount++; };
    },
    fetchLogs: (token, signal) => {
      const pending = deferred(); calls.push({ token, signal, ...pending }); return pending.promise;
    },
  });
  async function tick(ms) {
    const end = time + ms;
    for (let count = 0; ; count++) {
      assert.ok(count < 200, 'No spinning timers');
      const next = [...timers].filter(([, timer]) => timer.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!next) break;
      time = next[1].at; timers.delete(next[0]); next[1].callback(); await flush();
    }
    time = end; await flush();
  }
  const subscribe = (email = 'a@example.com', token = state.token) => store.subscribe(email, token, () => {});
  const snapshot = (email = 'a@example.com', token = state.token) => store.getSnapshot(email, token);
  const visibility = visible => { state.visible = visible; state.listener?.(); };
  return { store, state, calls, timers, tick, subscribe, snapshot, visibility };
}

test('multiple consumers and StrictMode remount share one request, listener and timer', async () => {
  const f = fixture();
  const detach = f.subscribe(); detach(); f.subscribe(); f.subscribe();
  await flush();
  assert.equal(f.calls.length, 1); assert.equal(f.state.listenCount, 1);
  assert.equal(f.calls[0].signal.aborted, false);
  f.calls[0].resolve([log(10)]); await flush();
  assert.deepEqual(f.snapshot().logs, [log(10)]);
  assert.equal(f.timers.size, 1);
});

test('fresh cache survives navigation; zero consumers stop polling and listeners', async () => {
  const f = fixture(); let detach = f.subscribe(); await flush();
  f.calls[0].resolve([log(10)]); await flush(); detach(); await f.tick(0);
  assert.equal(f.timers.size, 0); assert.equal(f.state.listener, null);
  await f.tick(5_000); detach = f.subscribe(); await flush();
  assert.equal(f.calls.length, 1); assert.equal(f.snapshot().logs[0].id, 10);
  detach(); await f.tick(60_000); f.subscribe(); await flush();
  assert.equal(f.calls.length, 2);
});

test('slow requests never overlap even after multiple polling periods', async () => {
  const f = fixture(); f.subscribe(); await flush(); await f.tick(60_000);
  assert.equal(f.calls.length, 1);
  assert.equal(f.store.refresh(true), f.store.refresh(true));
  f.calls[0].resolve([]); await flush(); await f.tick(NOTIFICATION_POLL_MS - 1);
  assert.equal(f.calls.length, 1); await f.tick(1); assert.equal(f.calls.length, 2);
});

test('initially hidden tabs do not fetch; becoming visible starts once', async () => {
  const f = fixture(); f.state.visible = false; f.subscribe(); await flush(); await f.tick(60_000);
  assert.equal(f.calls.length, 0); assert.equal(f.timers.size, 0);
  f.visibility(true); f.visibility(true); await flush(); assert.equal(f.calls.length, 1);
});

test('hiding aborts pending work and ignores its late response before resuming', async () => {
  const f = fixture(); f.subscribe(); await flush(); f.visibility(false);
  assert.equal(f.calls[0].signal.aborted, true);
  f.calls[0].resolve([log(999)]); await flush(); await f.tick(60_000);
  assert.deepEqual(f.snapshot().logs, []); assert.equal(f.calls.length, 1);
  f.visibility(true); await flush(); f.calls[1].resolve([log(20)]); await flush();
  assert.deepEqual(f.snapshot().logs, [log(20)]);
});

test('fresh visible resumes reuse cache; stale resumes refresh once without catch-up bursts', async () => {
  const f = fixture(); f.subscribe(); await flush(); f.calls[0].resolve([log(1)]); await flush();
  f.visibility(false); await f.tick(5_000); f.visibility(true); await flush();
  assert.equal(f.calls.length, 1); await f.tick(9_999); assert.equal(f.calls.length, 1);
  f.visibility(false); await f.tick(100_000); assert.equal(f.timers.size, 0);
  f.visibility(true); f.visibility(true); await flush(); assert.equal(f.calls.length, 2);
});

test('account switches abort old requests and never expose a previous identity', async () => {
  const f = fixture(); const detachA = f.subscribe(); await flush();
  f.state.token = 'token-b'; const detachB = f.subscribe('b@example.com'); await flush();
  assert.equal(f.calls[0].signal.aborted, true);
  f.calls[1].resolve([log(2)]); f.calls[0].resolve([log(999)]); await flush();
  assert.deepEqual(f.snapshot('b@example.com').logs, [log(2)]);
  assert.deepEqual(f.snapshot('a@example.com', 'token-a').logs, []);
  detachA(); detachB(); await f.tick(0); assert.equal(f.timers.size, 0);
});

test('same account with a new credential cannot reuse the old session cache', async () => {
  const f = fixture(); f.subscribe(); await flush(); f.calls[0].resolve([log(999)]); await flush();
  f.state.token = 'new-token-a'; f.subscribe();
  assert.deepEqual(f.snapshot().logs, []); await flush(); assert.equal(f.calls.length, 2);
});

test('logout reset clears cache, cancels timers and rejects late responses', async () => {
  const f = fixture(); f.subscribe(); await flush(); f.state.token = null; f.store.reset();
  f.calls[0].resolve([log(999)]); await flush(); await f.tick(60_000);
  assert.deepEqual(f.snapshot('a@example.com', 'token-a').logs, []);
  assert.equal(f.timers.size, 0); assert.equal(f.state.listener, null);
  f.state.token = 'token-a'; f.subscribe(); await flush(); assert.equal(f.calls.length, 2);
});

test('token changes before a response is received are rejected even before React rerenders', async () => {
  const f = fixture(); f.subscribe(); await flush(); f.state.token = 'token-b';
  f.calls[0].resolve([log(999)]); await flush();
  assert.deepEqual(f.snapshot('a@example.com', 'token-a').logs, []);
  assert.equal(f.state.listener, null); assert.equal(f.timers.size, 0);
});

test('background errors preserve cached logs and back off; explicit retry is deduplicated', async () => {
  const f = fixture(); f.subscribe(); await flush(); f.calls[0].resolve([log(1)]); await flush();
  await f.tick(15_000); f.calls[1].reject(new Error('offline')); await flush();
  assert.equal(f.snapshot().error, true); assert.deepEqual(f.snapshot().logs, [log(1)]);
  f.subscribe(); await flush(); assert.equal(f.calls.length, 2);
  f.store.refresh(true); f.store.refresh(true); await flush(); assert.equal(f.calls.length, 3);
  f.calls[2].resolve([log(2)]); await flush(); assert.equal(f.snapshot().error, false);
});

test('initial errors are distinct from empty success; unauthorized errors clear cached logs', async () => {
  const f = fixture(); f.subscribe(); await flush(); f.calls[0].reject(new Error('outage')); await flush();
  assert.equal(f.snapshot().ready, false); assert.equal(f.snapshot().error, true);
  f.store.refresh(true); await flush(); f.calls[1].resolve([]); await flush();
  assert.equal(f.snapshot().ready, true); assert.equal(f.snapshot().error, false);
  f.store.refresh(true); await flush(); f.calls[2].resolve([log(1)]); await flush();
  f.store.refresh(true); await flush(); f.calls[3].reject({ response: { status: 401 } }); await flush();
  assert.deepEqual(f.snapshot().logs, []); assert.equal(f.snapshot().error, true);
});

test('shared feed hides all internal Admin reasons and caps Profile history at 20', async () => {
  const f = fixture(); f.subscribe(); await flush();
  f.calls[0].resolve([log(999, 'admin_grant'), log(998, 'admin_test_deduction'), log(997, 'admin_test_reset'),
    log(996, 'admin_new_action'), log(995, 'other', 'admin_test'), ...Array.from({ length: 25 }, (_, i) => log(25 - i))]);
  await flush(); assert.equal(f.snapshot().logs.length, 20); assert.equal(f.snapshot().logs[0].id, 25);
});

test('unmount cancels pending work after the StrictMode grace turn', async () => {
  const f = fixture(); const detach = f.subscribe(); await flush(); detach(); await f.tick(0);
  assert.equal(f.calls[0].signal.aborted, true);
  f.calls[0].resolve([log(999)]); await flush(); assert.equal(f.snapshot().ready, false);
});
