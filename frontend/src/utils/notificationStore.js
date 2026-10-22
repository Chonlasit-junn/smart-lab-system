export const NOTIFICATION_POLL_MS = 15_000;
const EMPTY = Object.freeze({ logs: [], loading: false, ready: false, error: false });

export const isUserPointLog = log =>
  log.source_type !== 'admin_test' && !String(log.reason || '').startsWith('admin_');

// One in-memory feed per browser tab, scoped to both account and credential.
// Dependencies are injected so races and polling can be tested without an API.
export function createNotificationStore({ fetchLogs, readToken, isVisible, listen,
  now = Date.now, delay = setTimeout, cancelDelay = clearTimeout }) {
  const subscribers = new Set();
  let session = null, snapshot = EMPTY, request = null, timer = null;
  let idleTimer = null, unlisten = null, nextFetchAt = 0;
  const emit = () => subscribers.forEach(subscriber => subscriber.notify());
  const publish = value => { snapshot = value; emit(); };
  const same = (email, token) => session?.email === email && session?.token === token;
  const active = () => session && readToken() === session.token &&
    [...subscribers].some(subscriber => same(subscriber.email, subscriber.token));
  const clearTimer = () => { if (timer !== null) cancelDelay(timer); timer = null; };
  function pause() {
    clearTimer();
    const previous = request;
    request = null; // Invalidate before abort: even an uncancellable response is ignored.
    previous?.controller.abort();
    if (snapshot.loading) publish({ ...snapshot, loading: false });
  }
  function stop() {
    pause();
    unlisten?.(); unlisten = null;
  }
  function schedule() {
    clearTimer();
    if (active() && isVisible() && !request) {
      timer = delay(() => { timer = null; refresh(); }, Math.max(0, nextFetchAt - now()));
    }
  }
  function reset() {
    stop();
    if (idleTimer !== null) cancelDelay(idleTimer);
    idleTimer = null;
    session = null; nextFetchAt = 0;
    publish(EMPTY);
  }
  function refresh(force = false) {
    if (!active() || !isVisible()) return Promise.resolve();
    if (request) return request.promise;
    if (!force && now() < nextFetchAt) { schedule(); return Promise.resolve(); }
    clearTimer();
    const identity = session;
    const job = { controller: new AbortController(), promise: null };
    request = job;
    const current = () => request === job && session === identity && readToken() === identity.token;
    publish({ ...snapshot, loading: true, error: false });
    job.promise = Promise.resolve().then(() => {
      if (!current() || job.controller.signal.aborted) return undefined;
      return fetchLogs(identity.token, job.controller.signal);
    }).then(logs => {
      if (current() && isVisible()) {
        if (!Array.isArray(logs)) throw new Error('Invalid notification response');
        publish({ logs: logs.filter(isUserPointLog).slice(0, 20), ready: true, loading: false, error: false });
      }
    }).catch(error => {
      if (current() && !job.controller.signal.aborted) {
        const unauthorized = [401, 403].includes(error.response?.status);
        publish({ ...(unauthorized ? EMPTY : snapshot), loading: false, error: true });
      }
    }).finally(() => {
      if (request !== job) return;
      request = null;
      nextFetchAt = now() + NOTIFICATION_POLL_MS;
      if (readToken() !== identity.token) reset();
      else schedule();
    });
    return job.promise;
  }
  function wake() {
    if (!active()) { reset(); return; }
    if (!isVisible()) { pause(); return; }
    refresh();
  }
  return {
    reset,
    refresh,
    getSnapshot(email, token) {
      return same(email, token) && readToken() === token ? snapshot : EMPTY;
    },
    subscribe(email, token, notify) {
      if (!email || !token || readToken() !== token) return () => {};
      if (idleTimer !== null) cancelDelay(idleTimer);
      idleTimer = null;
      if (!same(email, token)) {
        stop(); session = { email, token }; snapshot = EMPTY; nextFetchAt = 0;
        emit();
      }
      const subscriber = { email, token, notify };
      subscribers.add(subscriber);
      if (!unlisten) unlisten = listen(wake);
      refresh();
      return () => {
        subscribers.delete(subscriber);
        if (subscribers.size === 0) {
          // React StrictMode and same-commit navigation may resubscribe. Reuse
          // their in-flight request instead of aborting and immediately retrying.
          idleTimer = delay(() => { idleTimer = null; stop(); }, 0);
        }
      };
    },
  };
}
