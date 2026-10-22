// Opt-in rendered regressions. Every API request is mocked; localhost only.
import assert from 'node:assert/strict';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const base = new URL(process.env.SMART_LAB_E2E_URL || 'http://127.0.0.1:5180');
if (!['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname)) throw Error('Only a local frontend is allowed');
const installed = process.env.SMART_LAB_PLAYWRIGHT_MODULE;
const { chromium } = await import(installed ? pathToFileURL(installed).href : 'playwright');
const browser = await chromium.launch({ headless: true,
  ...(process.env.SMART_LAB_BROWSER_EXECUTABLE ? { executablePath: process.env.SMART_LAB_BROWSER_EXECUTABLE } : {}),
});
const a = 'account.a@example.com', b = 'account.b@example.com';
const token = (email, role = 'student') => 'test.' + Buffer.from(JSON.stringify({ sub: email, role, exp: 4000000000 })).toString('base64url') + '.test';
const readKey = email => `last_seen_point_log_id:${encodeURIComponent(email)}`;
const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' };
const shots = [];

async function fixture(language, role = 'student') {
  const context = await browser.newContext({ viewport: { width: language === 'en' ? 1280 : 390, height: 844 } });
  await context.addInitScript(({ language, token }) => {
    if (localStorage.getItem('smart-lab-qa-seeded')) return;
    localStorage.clear();
    localStorage.setItem('smart-lab-qa-seeded', 'true');
    localStorage.setItem('smart-lab-language', language);
    localStorage.setItem('smart-lab-theme', language === 'en' ? 'light' : 'dark');
    localStorage.setItem('access_token', token);
    localStorage.setItem('last_seen_point_log_id', '90000');
  }, { language, token: token(a, role) });
  const state = { mode: 'error', calls: 0, pageErrors: [], unexpected: [], expectedHttpErrors: 0 };
  const page = await context.newPage();
  page.on('pageerror', error => state.pageErrors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error' && /500|Bad Request/.test(message.text())) state.expectedHttpErrors++;
  });
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    const reply = (json, status = 200) => route.fulfill({ status, headers, json });
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    const auth = request.headers().authorization;
    let email = a;
    if (auth) email = JSON.parse(Buffer.from(auth.split('.')[1], 'base64url').toString()).sub;
    if (url.pathname.endsWith('/users/me')) return reply({ id: email === a ? 1 : 2, email,
      first_name: email === a ? 'Account A' : 'Account B', last_name: 'QA', role, profile_pic: null });
    if (url.pathname.endsWith('/users/me/points/logs')) return reply({ data: [{ id: email === a ? 100 : 10,
      reason: 'daily_bonus', change: 1, note: 'Synthetic notification', created_at: '2026-10-22T00:00:00Z' }] });
    if (url.pathname.endsWith('/users/me/points')) return reply({ points: 100, daily_score: 100, booking_allowed: true });
    if (url.pathname.endsWith('/labs')) return reply({ data: [] });
    if (url.pathname.endsWith('/request-otp')) return reply({ account_type: 'general', expires_in_seconds: 600, retry_after_seconds: 60 });
    if (url.pathname.endsWith('/verify-otp')) return reply({ message: 'OTP Verified Successfully!' });
    if (url.pathname.endsWith('/register') && request.method() === 'POST') throw Error('UI policy test must never submit a registration');
    if (url.pathname.startsWith('/bookings/') && request.method() === 'DELETE') return reply({ message: 'Synthetic cancellation' });
    if (url.pathname.startsWith('/admin/tickets/') && request.method() === 'PATCH') return reply({ message: 'Synthetic close' });
    if (url.pathname.includes('/bookings/user/') || ['/tickets/me', '/tickets'].includes(url.pathname)) {
      state.calls++;
      if (state.mode === 'error') return reply({ detail: 'Synthetic outage' }, 500);
      const pageNumber = Number(url.searchParams.get('page') || 1);
      const data = state.mode === 'empty' ? [] : [{ id: pageNumber, lab_code: `QA-ROW-${pageNumber}`,
        lab_name: 'Synthetic Lab', booking_date: '2026-10-20', start_time: '08:40', end_time: '11:00',
        status: url.pathname.includes('tickets') ? 'open' : 'reserved', subject: `QA-ROW-${pageNumber}`, message: 'Synthetic ticket', user_id: 1, created_at: '2026-10-20T00:00:00Z' }];
      return reply({ data, total: data.length ? 40 : 0, page: pageNumber, page_size: 20 });
    }
    if (url.origin === base.origin) return route.continue();
    // External fonts and any unanticipated API must never reach production.
    if (!url.hostname.endsWith('googleapis.com') && !url.hostname.endsWith('gstatic.com')) state.unexpected.push(url.pathname);
    return route.abort();
  });
  return { context, page, state };
}

async function assertHealthy(page, state) {
  assert.equal(await page.locator('vite-error-overlay').count(), 0);
  assert.deepEqual(state.pageErrors, []);
  assert.deepEqual(state.unexpected, []);
  assert.ok((await page.locator('body').innerText()).trim().length > 30);
}

try {
  for (const language of ['en', 'th']) {
    for (const pathname of ['/history', '/reserved', '/my-tickets', '/ticket']) {
      const { context, page, state } = await fixture(language, pathname === '/ticket' ? 'admin' : 'student');
      await page.goto(new URL(pathname, base).href);
      await page.getByRole('alert').waitFor();
      assert.equal(new URL(page.url()).pathname, pathname);
      assert.ok((await page.getByRole('alert').innerText()).includes(language === 'en' ? 'Unable to load data' : 'โหลดข้อมูลไม่สำเร็จ'));
      assert.equal(await page.locator('.history-empty-state, .reservation-empty-state').count(), 0);
      const retry = () => page.getByRole('button', { name: language === 'en' ? 'Retry' : 'ลองใหม่', exact: true });
      state.mode = 'empty'; await retry().click();
      await page.getByRole('alert').waitFor({ state: 'detached' });
      if (pathname !== '/ticket') await page.locator('.history-empty-state, .reservation-empty-state').waitFor();
      else await page.locator('tbody td[colspan="7"]').waitFor();
      state.mode = 'data'; await page.reload();
      await page.getByText('QA-ROW-1', { exact: true }).waitFor();
      state.mode = 'error';
      await page.getByRole('button', { name: /page 2/i }).click();
      await page.getByRole('alert').waitFor();
      assert.equal(await page.getByText('QA-ROW-1', { exact: true }).count(), 0);
      if (pathname === '/history') {
        const screenshot = path.join(tmpdir(), `smartlab-bugfix-history-${language}.png`);
        await page.screenshot({ path: screenshot, fullPage: true }); shots.push(screenshot);
      }
      state.mode = 'data'; await retry().click();
      await page.getByText('QA-ROW-2', { exact: true }).waitFor();
      assert.equal(await page.getByRole('alert').count(), 0);
      if (pathname === '/reserved') {
        await page.locator('tbody button').click();
        await page.getByRole('dialog').waitFor();
        state.mode = 'empty';
        await page.getByRole('button', { name: language === 'en' ? 'Yes, cancel' : 'ใช่ ยกเลิก', exact: true }).click();
        await page.getByRole('dialog').waitFor({ state: 'detached' });
        await page.locator('.reservation-empty-state').waitFor();
      }
      if (pathname === '/ticket') {
        await page.getByRole('button', { name: language === 'en' ? 'Close ticket' : 'ปิด Ticket', exact: true }).click();
        await page.getByText(language === 'en' ? 'Resolved' : 'ดำเนินการแล้ว', { exact: true }).waitFor();
      }
      await assertHealthy(page, state);
      console.log(`PASS ${language} ${pathname}: error -> retry -> empty -> data -> failed next page -> retry`);
      await context.close();
    }

    const { context, page, state } = await fixture(language);
    state.mode = 'empty';
    const bell = () => page.getByRole('button', { name: language === 'en' ? 'Notifications' : 'การแจ้งเตือน', exact: true });
    const unread = () => bell().locator('.MuiBadge-badge:not(.MuiBadge-invisible)');
    await page.goto(new URL('/booking', base).href);
    await unread().waitFor(); await bell().click();
    await page.waitForFunction(key => localStorage.getItem(key) === '100', readKey(a));
    await page.goto(new URL('/history', base).href);
    await bell().waitFor();
    assert.equal(await unread().count(), 0);
    await page.evaluate(value => localStorage.setItem('access_token', value), token(b));
    await page.reload(); await unread().waitFor();
    await bell().click();
    await page.waitForFunction(key => localStorage.getItem(key) === '10', readKey(b));
    await page.goto(new URL('/booking', base).href);
    await bell().waitFor(); assert.equal(await unread().count(), 0);
    assert.equal(await page.evaluate(key => localStorage.getItem(key), readKey(a)), '100');
    await assertHealthy(page, state);
    console.log(`PASS ${language} notification ownership and Booking/shared-bell consistency`);

    await page.goto(new URL('/register', base).href);
    await page.locator('input[name=email]').fill('registration.qa@example.com');
    await page.locator('button[type=submit]').click();
    await page.locator('input[name=otp]').fill('123456');
    await page.locator('button[type=submit]').click();
    await page.locator('input[name=first_name]').fill('Synthetic');
    await page.locator('input[name=last_name]').fill('QA');
    await page.locator('input[name=phone]').fill('0000000000');
    await page.locator('input[type=checkbox]').check();
    await page.locator('input[name=password]').fill('short');
    await page.locator('button[type=submit]').click();
    await page.getByRole('alert').filter({ hasText: language === 'en' ? 'at least 8' : 'อย่างน้อย 8' }).waitFor();
    await page.locator('input[name=password]').fill('ก'.repeat(25));
    await page.locator('button[type=submit]').click();
    assert.equal(await page.locator('input[name=password]').count(), 1);
    await page.locator('input[name=password]').fill('x'.repeat(72));
    assert.equal((await page.locator('input[name=password]').inputValue()).length, 72);
    await page.locator('button[type=submit]').click();
    await page.locator('input[type=file]').waitFor({ state: 'attached' });
    await assertHealthy(page, state);
    console.log(`PASS ${language} registration policy: short/multibyte rejection and 72-byte acceptance`);
    await context.close();
  }
  console.log(JSON.stringify({ passed: true, screenshots: shots }));
} finally {
  await browser.close();
}
