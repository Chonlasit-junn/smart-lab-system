// Local-only API fixtures and virtual time. Never reaches production services.
import assert from 'node:assert/strict';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const base = new URL(process.env.SMART_LAB_E2E_URL || 'http://127.0.0.1:5180');
if (!['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)) throw Error('Local frontend required');
const installed = process.env.SMART_LAB_PLAYWRIGHT_MODULE;
const { chromium } = await import(installed ? pathToFileURL(installed).href : 'playwright');
const browser = await chromium.launch({ headless: true,
  ...(process.env.SMART_LAB_BROWSER_EXECUTABLE ? { executablePath: process.env.SMART_LAB_BROWSER_EXECUTABLE } : {}),
});
const a = 'account.a@example.com', b = 'account.b@example.com';
const token = email => 'qa.' + Buffer.from(JSON.stringify({ sub: email, role: email.startsWith('admin') ? 'admin' : 'student', exp: 4000000000 })).toString('base64url') + '.qa';
const logs = (email, latest = email === a ? 20 : 10) => [
  { id: 9999, reason: 'admin_future_action', change: 10, note: 'SECRET_ADMIN', created_at: '2026-10-22T00:00:00Z' },
  { id: 9998, reason: 'other', source_type: 'admin_test', change: -10, note: 'SECRET_ADMIN' },
  ...Array.from({ length: Math.min(20, latest) }, (_, index) => ({ id: latest - index, reason: 'complete_session', change: 2,
    note: `NOTE-${email === a ? 'A' : 'B'}-${latest - index}`, created_at: '2026-10-22T00:00:00Z' })),
];
const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' };
const shots = [];

async function fixture(language, { hidden = false, mode = 'data' } = {}) {
  const context = await browser.newContext({ viewport: { width: language === 'en' ? 1280 : 390, height: 844 } });
  await context.addInitScript(({ language, token, hidden }) => {
    if (!localStorage.getItem('qa-notification-seeded')) {
      localStorage.clear(); localStorage.setItem('qa-notification-seeded', '1');
      localStorage.setItem('access_token', token);
      localStorage.setItem('smart-lab-language', language);
      localStorage.setItem('smart-lab-theme', language === 'en' ? 'light' : 'dark');
    }
    let visibility = hidden ? 'hidden' : 'visible', online = true;
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility });
    Object.defineProperty(navigator, 'onLine', { configurable: true, get: () => online });
    window.qaVisibility = value => { visibility = value; document.dispatchEvent(new Event('visibilitychange')); };
    window.qaOnline = value => { online = value; window.dispatchEvent(new Event(value ? 'online' : 'offline')); };
  }, { language, token: token(a), hidden });
  const state = { mode, latest: 20, calls: [], pageErrors: [], consoleIssues: [], unexpected: [] };
  const page = await context.newPage();
  page.on('pageerror', error => state.pageErrors.push(error.message));
  page.on('console', message => {
    if (!['error', 'warning'].includes(message.type())) return;
    if (/Failed to load resource|GridLegacy/.test(message.text())) return;
    state.consoleIssues.push(message.text());
  });
  await page.clock.install({ time: new Date('2026-10-23T03:00:00Z') });
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    const reply = (json, status = 200) => route.fulfill({ json, status, headers });
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    let email = a;
    const auth = request.headers().authorization;
    if (auth) email = JSON.parse(Buffer.from(auth.split('.')[1], 'base64url').toString()).sub;
    if (url.pathname === '/login' && request.method() === 'POST') {
      const email = new URLSearchParams(request.postData()).get('username');
      return reply({ access_token: token(email) });
    }
    if (url.pathname === '/users/me') return reply({ id: email === a ? 1 : 2, email,
      first_name: email === a ? 'Account A' : 'Account B', last_name: 'QA',
      role: email.startsWith('admin') ? 'admin' : 'student', created_at: '2026-10-20T00:00:00Z', stats: {} });
    if (url.pathname === '/users/me/points') return reply({ points: 100, daily_score: 100, booking_allowed: true });
    if (url.pathname === '/users/me/points/logs') {
      state.calls.push({ email, limit: url.searchParams.get('limit'), filtered: url.searchParams.get('notifications_only') });
      if (state.mode === 'error') return reply({ detail: 'Synthetic outage' }, 500);
      return reply({ data: state.mode === 'empty' ? [] : logs(email, email === a ? state.latest : 10) });
    }
    if (url.pathname === '/labs') return reply({ data: [] });
    if (url.pathname.startsWith('/bookings/user/')) return reply({ data: [], total: 0 });
    if (url.pathname === '/admin/dashboard') return reply({ data: { total_requests: 0, active_users: 0, pending_approvals: 0, recent_reservations: [] } });
    if (url.origin === base.origin) return route.continue();
    if (!url.hostname.endsWith('googleapis.com') && !url.hostname.endsWith('gstatic.com')) state.unexpected.push(url.pathname);
    return route.abort();
  });
  const bell = () => page.getByRole('button', { name: language === 'en' ? 'Notifications' : 'การแจ้งเตือน', exact: true });
  const popup = () => page.locator('.MuiPopover-paper');
  const readKey = email => `last_seen_point_log_id:${encodeURIComponent(email)}`;
  async function openBell() { await bell().click(); await popup().waitFor(); await page.clock.runFor(250); }
  async function closeBell() {
    // A successful retry unmounts the focused Alert button. Give keyboard
    // focus to the dialog before exercising Escape with the virtual clock.
    await popup().focus();
    await page.keyboard.press('Escape');
    await page.waitForFunction(() => !document.querySelector('button[aria-haspopup=true][aria-expanded=true]'));
    await page.clock.runFor(500);
    await popup().waitFor({ state: 'detached' });
  }
  async function navigate(pathname) {
    await page.evaluate(pathname => { history.pushState({}, '', pathname); dispatchEvent(new PopStateEvent('popstate')); }, pathname);
    await bell().waitFor();
  }
  async function waitCalls(count) { await page.waitForFunction(() => true); assert.equal(state.calls.length, count); }
  async function logout() {
    await page.locator('button').filter({ has: page.locator('.MuiAvatar-root') }).first().click();
    await page.getByText(language === 'en' ? 'Log out' : 'ออกจากระบบ', { exact: true }).click();
    await page.locator('.login-form-content input').first().waitFor();
  }
  async function login(email) {
    await page.locator('.login-form-content input').first().fill(email);
    await page.locator('input[type=password]').fill('Synthetic-only-password');
    await page.locator('button[type=submit]').click(); await bell().waitFor();
  }
  return { context, page, state, bell, popup, openBell, closeBell, navigate, readKey, waitCalls, logout, login };
}

async function healthy(f, pathname) {
  assert.equal(new URL(f.page.url()).pathname, pathname);
  assert.ok((await f.page.title()).length > 0);
  assert.ok((await f.page.locator('body').innerText()).length > 30);
  assert.equal(await f.page.locator('vite-error-overlay').count(), 0);
  assert.deepEqual(f.state.pageErrors, []); assert.deepEqual(f.state.consoleIssues, []);
  assert.deepEqual(f.state.unexpected, []);
}

try {
  for (const language of ['en', 'th']) {
    const f = await fixture(language);
    await f.page.goto(new URL('/booking', base).href); await f.openBell();
    await f.popup().getByText('NOTE-A-20', { exact: true }).waitFor();
    assert.equal(await f.popup().getByText(/^NOTE-A-/).count(), 10);
    assert.equal(await f.page.getByText('SECRET_ADMIN').count(), 0);
    await f.page.waitForFunction(key => localStorage.getItem(key) === '20', f.readKey(a));
    await f.waitCalls(1); await f.closeBell();
    await f.navigate('/history'); await f.openBell();
    await f.popup().getByText('NOTE-A-20', { exact: true }).waitFor(); await f.waitCalls(1); await f.closeBell();
    await f.navigate('/profile'); await f.page.locator('.profile-point-history-item').first().waitFor();
    assert.equal(await f.page.locator('.profile-point-history-item').count(), 20);
    await f.openBell(); assert.equal(await f.popup().getByText(/^NOTE-A-/).count(), 10); await f.waitCalls(1);
    assert.ok((await f.popup().evaluate(element => getComputedStyle(element).transitionProperty)).includes('opacity'));
    const scrollable = f.popup().locator(':scope > div').last();
    assert.equal(await scrollable.evaluate(element => element.scrollHeight > element.clientHeight), true);
    await f.popup().getByText('NOTE-A-11', { exact: true }).scrollIntoViewIfNeeded();
    await f.popup().getByText('NOTE-A-20', { exact: true }).scrollIntoViewIfNeeded();
    const screenshot = path.join(tmpdir(), `smartlab-notifications-${language}.png`);
    await f.page.screenshot({ path: screenshot, animations: 'disabled' }); shots.push(screenshot); await f.closeBell();
    f.state.latest = 21; await f.page.clock.runFor(15_000);
    await f.page.getByText('NOTE-A-21', { exact: false }).waitFor(); await f.waitCalls(2);
    assert.equal(await f.bell().locator('.MuiBadge-badge:not(.MuiBadge-invisible)').count(), 1);
    await f.page.evaluate(() => window.qaVisibility('hidden')); await f.page.clock.runFor(60_000); await f.waitCalls(2);
    f.state.latest = 22; await f.page.evaluate(() => { window.qaVisibility('visible'); window.qaVisibility('visible'); });
    await f.page.getByText('NOTE-A-22', { exact: false }).waitFor(); await f.waitCalls(3);
    await f.page.evaluate(() => window.qaOnline(false)); await f.page.clock.runFor(60_000); await f.waitCalls(3);
    f.state.latest = 23; await f.page.evaluate(() => window.qaOnline(true));
    await f.page.getByText('NOTE-A-23', { exact: false }).waitFor(); await f.waitCalls(4);
    await f.page.evaluate(() => window.dispatchEvent(new Event('pagehide'))); await f.page.clock.runFor(60_000); await f.waitCalls(4);
    f.state.latest = 24; await f.page.evaluate(() => window.dispatchEvent(new Event('pageshow')));
    await f.page.getByText('NOTE-A-24', { exact: false }).waitFor(); await f.waitCalls(5);
    await f.logout(); const count = f.state.calls.length; await f.page.clock.runFor(60_000); await f.waitCalls(count);
    await f.login(b); await f.openBell(); await f.popup().getByText('NOTE-B-10', { exact: true }).waitFor();
    assert.equal(await f.page.getByText(/NOTE-A-/).count(), 0);
    await f.page.waitForFunction(key => localStorage.getItem(key) === '10', f.readKey(b));
    assert.equal(await f.page.evaluate(key => localStorage.getItem(key), f.readKey(a)), '20');
    assert.ok(f.state.calls.every(call => call.limit === '20' && call.filtered === 'true'));
    await f.closeBell(); await f.logout(); const beforeAdmin = f.state.calls.length;
    await f.login('admin.qa@example.com'); await f.page.clock.runFor(60_000); await f.waitCalls(beforeAdmin);
    await f.openBell(); await f.popup().getByText(language === 'en' ? 'No notifications yet' : 'ยังไม่มีการแจ้งเตือน', { exact: true }).waitFor();
    await healthy(f, '/admin'); await f.context.close();
    console.log(`PASS ${language}: one feed across Booking/History/Profile, polling/visibility/offline/page lifecycle, logout/login ownership, Admin disabled`);

    const hidden = await fixture(language, { hidden: true });
    await hidden.page.goto(new URL('/history', base).href); await hidden.openBell();
    await hidden.popup().getByRole('status').waitFor(); await hidden.page.clock.runFor(60_000); await hidden.waitCalls(0);
    await hidden.page.evaluate(() => window.qaVisibility('visible'));
    await hidden.popup().getByText('NOTE-A-20', { exact: true }).waitFor(); await hidden.waitCalls(1);
    await hidden.closeBell(); await healthy(hidden, '/history'); await hidden.context.close();
    console.log(`PASS ${language}: initially hidden tab waits until visible`);

    const failure = await fixture(language, { mode: 'error' });
    await failure.page.goto(new URL('/history', base).href); await failure.openBell();
    const alert = failure.popup().getByRole('alert'); await alert.waitFor();
    assert.equal(await failure.popup().getByText(language === 'en' ? 'No notifications yet' : 'ยังไม่มีการแจ้งเตือน').count(), 0);
    failure.state.mode = 'empty'; await alert.getByRole('button', { name: language === 'en' ? 'Retry' : 'ลองใหม่', exact: true }).click();
    await alert.waitFor({ state: 'detached' }); await failure.popup().getByText(language === 'en' ? 'No notifications yet' : 'ยังไม่มีการแจ้งเตือน', { exact: true }).waitFor();
    await failure.waitCalls(2); await failure.closeBell(); await healthy(failure, '/history'); await failure.context.close();
    console.log(`PASS ${language}: initial outage -> error (not empty) -> explicit retry -> empty success`);

    const switched = await fixture(language);
    await switched.page.goto(new URL('/history', base).href); await switched.openBell();
    await switched.popup().getByText('NOTE-A-20', { exact: true }).waitFor();
    await switched.page.evaluate(value => {
      localStorage.setItem('access_token', value);
      dispatchEvent(new StorageEvent('storage', { key: 'access_token', newValue: value }));
    }, token(b));
    await switched.popup().getByText('NOTE-A-20', { exact: true }).waitFor({ state: 'detached' });
    await switched.page.clock.runFor(60_000); await switched.waitCalls(1);
    assert.equal(await switched.popup().getByText(/NOTE-B-/).count(), 0);
    await healthy(switched, '/history'); await switched.context.close();
    console.log(`PASS ${language}: another tab's token cannot populate the old account's feed`);
  }
  console.log(JSON.stringify({ passed: true, screenshots: shots }));
} finally { await browser.close(); }
