// Local-only rendered regressions; no request may reach a real API.
import assert from 'node:assert/strict';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { DEFAULT_POINT_POLICY } from '../src/pages/adminPointPolicyUtils.js';

const base = new URL(process.env.SMART_LAB_E2E_URL || 'http://127.0.0.1:5180');
if (!['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)) throw Error('Local frontend required');
const modulePath = process.env.SMART_LAB_PLAYWRIGHT_MODULE;
const { chromium } = await import(modulePath ? pathToFileURL(modulePath).href : 'playwright');
const browser = await chromium.launch({ headless: true,
  ...(process.env.SMART_LAB_BROWSER_EXECUTABLE ? { executablePath: process.env.SMART_LAB_BROWSER_EXECUTABLE } : {}),
});
const routes = ['/admin', '/admin/points', '/admin/points/policy', '/admin/roles', '/admin/devices', '/manage-labs', '/verify-users', '/blacklist', '/ticket'];
const email = 'admin.qa@example.com';
const tokenForRole = role => 'qa.' + Buffer.from(JSON.stringify({ sub: email, role, exp: 4000000000 })).toString('base64url') + '.qa';
const token = tokenForRole('admin');
const lab = { id: 1, code: 'QA-LAB', name: 'Synthetic Lab', capacity: 30, location: 'QA location', status: 'active' };
const user = { id: 2, user_id: 2, first_name: 'Synthetic', last_name: 'User', name: 'Synthetic User', email: 'user.qa@example.com', role: 'student', roles: [{ id: 1, name: 'student' }], points: 90, daily_score: 100, booking_allowed: true };
const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' };
const retryName = language => language === 'en' ? 'Retry' : 'ลองใหม่';
const failureText = language => language === 'en' ? 'Unable to load data' : 'โหลดข้อมูลไม่สำเร็จ';
const shots = [];

async function fixture(language, roleName = 'admin') {
  const context = await browser.newContext({ viewport: { width: language === 'en' ? 1280 : 390, height: 844 } });
  const sessionToken = tokenForRole(roleName);
  await context.addInitScript(({ language, token }) => {
    if (localStorage.getItem('qa-seeded')) return;
    localStorage.clear(); localStorage.setItem('qa-seeded', '1');
    localStorage.setItem('access_token', token);
    localStorage.setItem('smart-lab-language', language);
    localStorage.setItem('smart-lab-theme', language === 'en' ? 'light' : 'dark');
  }, { language, token: sessionToken });
  const state = { mode: 'loading', waiting: [], errors: [], consoleIssues: [], unexpected: [], writes: [], schedule: 'error', detail: 'error', crash: false, chunk: false, writeFailure: false, rejectCommitted: false, expectedBoundary: false };
  const page = await context.newPage();
  page.on('pageerror', error => state.errors.push(error.message));
  page.on('console', message => {
    const text = message.text();
    if (!['error', 'warning'].includes(message.type())) return;
    if (/Failed to load resource|GridLegacy|MUI Grid/.test(text)) return;
    if (state.expectedBoundary && /above error occurred|React will try to recreate|Objects are not valid|Minified React error #31;|Failed to fetch dynamically imported/.test(text)) return;
    state.consoleIssues.push(text);
  });
  await context.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url()), pathname = url.pathname;
    const reply = (json, status = 200) => route.fulfill({ json, status, headers });
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    if (url.origin === base.origin && (pathname === '/src/pages/Admin.jsx' || /^\/assets\/Admin-[^/]+\.js$/.test(pathname)) && state.chunk) {
      state.chunk = false;
      return route.fulfill({ status: 503, contentType: 'text/javascript', body: '' });
    }
    if (pathname.endsWith('/users/me')) return reply({ id: 1, email, first_name: 'QA', last_name: 'Admin', role: roleName });
    if (pathname.endsWith('/users/me/points/logs')) return reply({ data: [] });
    const isApi = pathname === '/labs' || pathname === '/tickets' || pathname.startsWith('/admin/') || /^\/labs\/\d+\/schedules$/.test(pathname);
    // Frontend routes on the same origin must still be served by Vite.
    if (isApi && !(url.origin === base.origin && request.isNavigationRequest())) {
      if (request.method() !== 'GET') {
        state.writes.push({ method: request.method(), pathname });
        if (request.method() === 'PUT' && /^\/admin\/users\/\d+\/verify$/.test(pathname)) {
          state.rejectCommitted = true;
          return reply({ detail: 'Synthetic response lost after commit' }, 503);
        }
        if (state.writeFailure) return reply({ detail: 'Synthetic save failure' }, 500);
        return reply({ data: DEFAULT_POINT_POLICY, message: 'Synthetic success' });
      }
      if (state.mode === 'loading') await new Promise(resolve => state.waiting.push(resolve));
      if (/\/schedules$/.test(pathname)) return state.schedule === 'error' ? reply({}, 500) : reply({ data: [] });
      if (/\/details$/.test(pathname)) return state.detail === 'error' ? reply({}, 500) : reply({ profile: user, points: { points: 90 }, summary: {}, bookings: [], sessions: [], point_logs: [] });
      if (state.mode === 'error') return reply({ detail: [{ msg: 'PRIVATE-ERROR' }] }, 500);
      const data = state.mode === 'data';
      if (pathname === '/admin/dashboard') return reply({ data: state.crash ? { total_requests: { private: 'PRIVATE-ERROR' } } : data ? { total_requests: 1, active_users: 1, pending_approvals: 0, recent_reservations: [{ id: 1, user, lab, booking_date: '2026-10-20', start_time: '08:40' }] } : {} });
      if (pathname === '/admin/points/policy') return reply({ data: data ? DEFAULT_POINT_POLICY : null });
      if (pathname === '/labs') return reply({ data: data ? [lab] : [] });
      if (pathname === '/admin/roles') return reply({ data: data ? [{ id: 1, name: 'student', display_name: 'QA Role', user_count: 1, is_system: true, assignable: true }] : [] });
      if (pathname === '/admin/roles/users') return reply({ data: data ? [user] : [] });
      if (pathname === '/admin/users/pending') return reply({ data: data && !state.rejectCommitted ? [{ ...user, role: 'guest' }] : [] });
      if (pathname === '/admin/points') return reply({ data: data ? [user] : [], total: data ? 40 : 0, point_requests: [], score_date: '2026-10-22' });
      if (pathname === '/admin/lab-devices') return reply({ data: data ? [{ id: 1, device_id: 'qa-device', device_name: 'QA Device', status: 'active', lab, agent_version: 'QA' }] : [] });
      if (pathname === '/admin/blacklist') return reply({ data: data ? [{ id: 1, app_name: 'QA Rule', match_type: 'process_name', match_value: 'qa.exe', description: 'Synthetic rule' }] : [] });
      if (pathname === '/tickets') return reply({ data: data ? [{ id: 1, user_id: 2, subject: 'QA Ticket', message: 'Synthetic ticket', status: 'open', created_at: '2026-10-20T00:00:00Z' }] : [], total: data ? 1 : 0 });
      state.unexpected.push(pathname); return reply({}, 404);
    }
    if (url.origin === base.origin) return route.continue();
    if (!url.hostname.endsWith('googleapis.com') && !url.hostname.endsWith('gstatic.com')) state.unexpected.push(pathname);
    return route.abort();
  });
  return { context, page, state };
}

async function healthy(page, state, pathname) {
  assert.equal(new URL(page.url()).pathname, pathname);
  assert.ok((await page.title()).includes('Smart Lab'));
  assert.ok((await page.locator('body').innerText()).length > 30);
  assert.equal(await page.locator('vite-error-overlay').count(), 0);
  assert.deepEqual(state.errors, []);
  assert.deepEqual(state.consoleIssues, []);
  assert.deepEqual(state.unexpected, []);
}

try {
  for (const language of ['en', 'th']) {
    for (const pathname of routes) {
      const { context, page, state } = await fixture(language);
      await page.goto(new URL(pathname, base).href);
      const content = page.locator('.admin-content-area');
      if (language === 'th') {
        if (pathname === '/ticket') {
          await page.locator('.admin-menu-toggle').click();
          await page.locator('.admin-sidebar.open').waitFor();
        } else {
          await page.locator('.admin-global-menu-toggle').click();
          await page.locator('.admin-mobile-drawer').waitFor();
        }
        await page.locator('.admin-navigation').waitFor();
        await page.locator('.sidebar-overlay').click({ position: { x: 300, y: 40 } });
        await page.locator('.admin-sidebar.open, .admin-mobile-drawer').waitFor({ state: 'detached' });
      }
      const emptyText = ({
        '/admin': ['No data available', 'ยังไม่มีข้อมูล'],
        '/admin/points': ['No users match the selected filters', 'ไม่พบข้อมูลผู้ใช้ตามเงื่อนไขที่เลือก'],
        '/admin/points/policy': ['No data available', 'ยังไม่มีข้อมูล'],
        '/admin/roles': ['No data available', 'ยังไม่มีข้อมูล'],
        '/admin/devices': ['No registered devices', 'ยังไม่มีเครื่องที่ลงทะเบียน'],
        '/manage-labs': ['No data available', 'ยังไม่มีข้อมูล'],
        '/verify-users': ['No pending verifications', 'ไม่มีผู้ใช้ที่รอตรวจสอบ'],
        '/blacklist': ['No blocked entries yet', 'ยังไม่มีรายการต้องห้าม'],
        '/ticket': ['No tickets yet', 'ยังไม่มี Ticket'],
      })[pathname][language === 'en' ? 0 : 1];
      await content.waitFor();
      await content.getByRole('progressbar').or(content.getByRole('status')).or(content.getByText(language === 'en' ? 'Loading...' : 'กำลังโหลด...', { exact: true })).first().waitFor();
      assert.equal(await content.getByRole('button', { name: retryName(language), exact: true }).count(), 0);
      state.mode = 'error'; state.waiting.splice(0).forEach(resolve => resolve());
      const alert = content.getByRole('alert').filter({ hasText: failureText(language) });
      await alert.waitFor();
      if (pathname === '/admin') {
        const screenshot = path.join(tmpdir(), `smartlab-admin-error-${language}.png`);
        await page.screenshot({ path: screenshot }); shots.push(screenshot);
      }
      assert.equal(await content.getByText(language === 'en' ? 'No data available' : 'ยังไม่มีข้อมูล', { exact: true }).count(), 0);
      assert.equal(await content.getByText(emptyText, { exact: true }).count(), 0);
      assert.ok(!(await content.innerText()).includes('PRIVATE-ERROR'));
      state.mode = 'empty';
      await alert.getByRole('button', { name: retryName(language), exact: true }).click();
      await alert.waitFor({ state: 'detached' });
      await content.getByRole('progressbar').waitFor({ state: 'detached' });
      await content.getByText(emptyText, { exact: true }).waitFor();
      assert.ok((await content.innerText()).trim().length > 0);
      // Empty policy must not expose editable defaults that were never loaded.
      if (pathname === '/admin/points/policy') assert.equal(await content.locator('input[type=number]').count(), 0);
      state.mode = 'data'; await page.reload();
      const marker = ({ '/admin': 'Synthetic User', '/admin/points': 'Synthetic User', '/admin/roles': 'QA Role', '/admin/devices': 'QA Device', '/manage-labs': 'QA-LAB', '/verify-users': 'Synthetic User', '/blacklist': 'QA Rule', '/ticket': 'QA Ticket' })[pathname];
      if (marker) await content.getByText(marker, { exact: true }).first().waitFor();
      else await content.locator('input[type=number]').first().waitFor();
      if (pathname === '/admin/points/policy') {
        const field = content.locator('input[type=number]').first();
        await field.fill('3'); state.writeFailure = true;
        await content.getByRole('button', { name: language === 'en' ? 'Save point criteria' : 'บันทึกเกณฑ์คะแนน', exact: true }).click();
        await content.getByRole('alert').filter({ hasText: 'Synthetic save failure' }).waitFor();
        assert.equal(await field.inputValue(), '3');
        assert.equal(await content.getByRole('button', { name: retryName(language), exact: true }).count(), 0);
        state.writeFailure = false;
        await content.getByRole('button', { name: language === 'en' ? 'Save point criteria' : 'บันทึกเกณฑ์คะแนน', exact: true }).click();
        await content.getByRole('alert').filter({ hasText: language === 'en' ? 'Point criteria saved' : 'บันทึกเกณฑ์คะแนนเรียบร้อย' }).waitFor();
        assert.equal(state.writes.length, 2);
      }
      if (pathname === '/manage-labs') {
        await content.locator('.lab-card').hover();
        await page.waitForFunction(() => getComputedStyle(document.querySelector('.lab-card')).transform !== 'none');
        await content.getByText('QA-LAB', { exact: true }).click();
        await alert.waitFor(); state.schedule = 'empty';
        await alert.getByRole('button', { name: retryName(language), exact: true }).click();
        await alert.waitFor({ state: 'detached' });
        await content.getByText(language === 'en' ? 'No data available' : 'ยังไม่มีข้อมูล', { exact: true }).waitFor();
      }
      if (pathname === '/admin/points') {
        state.mode = 'error'; await content.getByRole('button', { name: /page 2/i }).click();
        await alert.waitFor(); assert.equal(await content.getByText('Synthetic User', { exact: true }).count(), 0);
        state.mode = 'data'; await alert.getByRole('button', { name: retryName(language), exact: true }).click();
        await content.getByText('Synthetic User', { exact: true }).waitFor();
        await content.getByRole('button', { name: language === 'en' ? 'View details' : 'ดูข้อมูล', exact: true }).click();
        const dialog = page.getByRole('dialog');
        const detailError = dialog.getByRole('alert'); await detailError.waitFor();
        state.detail = 'data'; await detailError.getByRole('button', { name: retryName(language), exact: true }).click();
        await detailError.waitFor({ state: 'detached' }); await dialog.getByRole('tab').first().waitFor();
      }
      if (pathname === '/blacklist') {
        const screenshot = path.join(tmpdir(), `smartlab-admin-resilience-${language}.png`);
        await page.screenshot({ path: screenshot }); shots.push(screenshot);
      }
      await healthy(page, state, pathname);
      if (pathname !== '/admin/points/policy') assert.deepEqual(state.writes, []);
      console.log(`PASS ${language} ${pathname}: loading -> error -> retry -> empty -> data`);
      await context.close();
    }
    for (const failure of ['chunk', 'crash']) {
      const { context, page, state } = await fixture(language);
      state.mode = 'data'; state[failure] = true; state.expectedBoundary = true;
      await page.goto(new URL('/admin', base).href);
      const fallback = page.getByRole('alert').filter({ hasText: language === 'en' ? 'This page could not be opened' : 'เปิดหน้านี้ไม่สำเร็จ' });
      await fallback.waitFor();
      assert.ok(!(await fallback.innerText()).includes('PRIVATE-ERROR'));
      assert.equal(await page.evaluate(() => localStorage.getItem('access_token')), token);
      if (failure === 'crash') {
        const screenshot = path.join(tmpdir(), `smartlab-page-error-${language}.png`);
        await page.screenshot({ path: screenshot }); shots.push(screenshot);
        await page.evaluate(() => { history.pushState({}, '', '/ticket'); window.dispatchEvent(new PopStateEvent('popstate')); });
        await page.getByText('QA Ticket', { exact: true }).waitFor();
        await page.goBack(); await fallback.waitFor();
      }
      state.crash = false;
      await fallback.getByRole('button', { name: retryName(language), exact: true }).click();
      await page.getByText('Synthetic User', { exact: true }).waitFor();
      assert.equal(await fallback.count(), 0);
      await healthy(page, state, '/admin');
      console.log(`PASS ${language} ${failure}: localized fallback -> manual reload -> recovered, token retained`);
      await context.close();
    }
  }
  // Account links from both Admin layouts must keep the Admin navigation shell.
  for (const origin of ['/manage-labs', '/ticket']) {
    const { context, page, state } = await fixture('en');
    state.mode = 'data';
    await page.goto(new URL(origin, base).href);
    await page.locator('.admin-content-area').waitFor();
    if (origin === '/manage-labs') {
      await page.locator('.admin-top-header button').last().click();
      await page.getByRole('button', { name: 'Manage Account', exact: true }).click();
    } else {
      await page.getByRole('button', { name: 'Profile', exact: true }).click();
      await page.getByRole('button', { name: 'Settings', exact: true }).click();
    }
    await page.waitForURL(url => url.pathname === '/profile');
    await page.locator('.admin-layout .admin-content-area').waitFor();
    assert.equal(await page.locator('.app-layout:not(.admin-layout) .sidebar').count(), 0);
    await healthy(page, state, '/profile');
    console.log(`PASS ${origin} account entry keeps the Admin shell on /profile`);
    await context.close();
  }
  {
    const { context, page, state } = await fixture('en');
    state.mode = 'data';
    await page.goto(new URL('/ticket', base).href);
    await page.locator('.admin-content-area').waitFor();
    await page.getByRole('button', { name: 'Profile', exact: true }).click();
    await page.getByRole('button', { name: 'Open Lab Booking', exact: true }).click();
    await page.waitForURL(url => url.pathname === '/booking');
    await page.locator('.top-header').waitFor();
    await page.getByRole('button', { name: 'Open user menu', exact: true }).click();
    await page.getByRole('button', { name: 'Return to Admin', exact: true }).click();
    await page.waitForURL(url => url.pathname === '/ticket');
    console.log('PASS Admin profile menu switches to Lab Booking and returns to the originating Admin page');
    await context.close();
  }
  {
    const { context, page, state } = await fixture('en', 'student');
    state.mode = 'data';
    await page.goto(new URL('/booking', base).href);
    await page.getByRole('button', { name: 'Open user menu', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: 'Return to Admin', exact: true }).count(), 0,
      'non-admin accounts must not see the Admin mode switch');
    await context.close();
  }
  {
    const { context, page, state } = await fixture('en');
    state.mode = 'data';
    page.on('dialog', dialog => dialog.accept());
    await page.goto(new URL('/verify-users', base).href);
    await page.getByText('Synthetic User', { exact: true }).waitFor();
    await page.getByRole('button', { name: 'Reject', exact: true }).click();
    await page.getByText('No pending verifications', { exact: true }).waitFor();
    assert.equal(await page.getByRole('alert').count(), 0,
      'do not report a rejection failure if the authoritative pending list confirms deletion');
    await healthy(page, state, '/verify-users');
    console.log('PASS rejected Guest: post-commit HTTP error is reconciled against the pending list');
    await context.close();
  }
  console.log(JSON.stringify({ passed: true, screenshots: shots }));
} finally { await browser.close(); }
