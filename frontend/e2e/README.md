# Opt-in local rendered regressions

`bugfix-regressions.mjs` verifies the actual pages with Playwright. All API calls
are intercepted with synthetic responses; the target must be loopback. It never
sends mail, registers an account, changes a real credential, or accesses the app
database. Screenshots go to the OS temporary directory, not the repository.

Start the existing frontend with `npm run dev -- --host 127.0.0.1 --port 5180 --strictPort`.
Then run `node e2e/bugfix-regressions.mjs` from frontend using an existing Playwright
installation. If it is not a project dependency, set
`SMART_LAB_PLAYWRIGHT_MODULE` to that installation's absolute `index.mjs` path.
Optionally set `SMART_LAB_BROWSER_EXECUTABLE` to an installed Chromium/Edge
executable. No package installation or lockfile changes are required.

`SMART_LAB_E2E_URL` defaults to `http://127.0.0.1:5180`; non-loopback URLs are rejected.
Default `npm test` runs fast pure-function tests without requiring a browser.

Using the same local server and environment variables, run
`node e2e/admin-resilience.mjs` for all nine Admin routes in Thai/mobile/dark
and English/desktop/light. It covers loading, failed reads, retry, empty and
populated responses, failed Points pagination, nested detail/schedule retries,
save failures preserving policy inputs, render failures and failed lazy imports
with manual reload recovery and back navigation. All API
responses are synthetic, including errors; no production database is accessed.

To check the compiled chunks too, run `npm run build`, start
`npm run preview -- --host 127.0.0.1 --port 5181 --strictPort`, set
`SMART_LAB_E2E_URL=http://127.0.0.1:5181`, then run the same script.
