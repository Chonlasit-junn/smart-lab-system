# Admin usage export

Open **Admin → Usage reports** (`/admin/reports`). Select an inclusive Bangkok
date range of at most 31 days, optionally choose a Lab, registered device and
user, then download Excel. User lookup searches names/emails remotely after
two characters; refine searches that match more than 20 accounts. UI labels
and workbook headings follow Thai/English; account names and record values
are never translated.

## Workbook

1. **Summary**: selected filters, generation time, distinct users/devices/sessions,
   session seconds, foreground-program seconds, recorded violations and daily totals.
2. **Program usage**: checkpoints combined by Bangkok day, session and stored
   program name. Start/end show the first/last observed bounds, not continuous
   activity between them. The seconds/duration columns contain the actual sum.
3. **Sessions**: account identifiers/contact details, Lab, registered device ID,
   device name captured when the session started, entry/exit, status, end reason
   and time clipped to the report period. Active sessions stop at generation time.
4. **Violations**: detected time (not delivery time), program/domain, reason,
   action and detection source. These are recorded violations, not a count of
   every on-screen warning.

Only successful Agent (`access_type=manual`) sessions are included, not Gatekeeper
face scans. Intervals crossing Bangkok midnight are split between dates. Duration
seconds are apportioned by interval overlap with cumulative rounding, preserving
the total across all daily pieces. Legacy program labels are kept as stored;
they are not guessed or rewritten to match new EXE-based labels. Names, student
IDs and phone numbers reflect current account data. Unknown registered devices
are not counted as identified devices. Invalid time intervals are excluded from
time totals and their count is shown on Summary.

The workbook is a snapshot, not a live connection. Delayed Agent deliveries can
change subsequent downloads. Today/future periods include only data before the
generation instant. A session is included if its time, usage or violation overlaps
the requested period. Multiple violations never multiply usage durations.

Dates are real Excel dates shown as `dd/mm/yyyy`; timestamps are Bangkok wall
time, explicitly labeled UTC+7. IDs/phone numbers remain text where appropriate.
Durations use `[h]:mm:ss` and have numeric seconds alongside them. All externally
supplied strings are literal text, never formulas or automatic hyperlinks.

## Implementation and limits

- `GET /admin/reports/options`: safe Lab/device selectors, including inactive or
  revoked devices for historical reporting. Device filters are not restricted to
  their current Lab because devices may have moved since an old session.
- `GET /admin/reports/users?q=...`: bounded name/email search (20 results).
- `GET /admin/reports/usage.xlsx?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`
  accepts optional positive integer `lab_id`, `device_id` (LabDevice primary key),
  `user_id`, and `language=th|en`.
- Every endpoint validates a logged-in Admin on the server. No passwords, token
  hashes, face data, EXE paths or window titles are exported.
- Dedicated SELECT-only queries; no point bonus, session cleanup, booking
  mutation, schema change or migration. The shared user-details API is not used.
- Up to 50,000 source rows across sessions, usage and violations and up to 50,000
  grouped usage rows. Oversized exports return `413 REPORT_TOO_LARGE`, never a
  silently truncated workbook. Narrow the range/filters and retry.
- Two simultaneous workbook builds per API process; additional builds receive
  `429 REPORT_BUSY` with `Retry-After: 10`. This is a local concurrency guard, not
  a distributed rate limiter.
- Reads are batched; workbook XML is write-only, download spool spills to a
  temporary file above 8 MiB. Resources are released after success/failure or
  download cancellation. Excel files are not stored permanently or in Database.
- Additive backend dependency: `openpyxl==3.1.5` in `backend/requirements.txt`.
  Existing deployments need a normal backend dependency rebuild. No Agent/MSI
  change or new environment variable is required.

## Regression checks

```powershell
.\backend\venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p test_usage_reports.py
cd frontend
node --test tests/usageReport.test.js
npm test
npm run build
```

Backend tests use synthetic in-memory SQLite and an isolated FastAPI application,
never the production database or the main application's startup/schema creation.
QA should additionally check the workbook in the organization's Excel version,
especially Thai fonts, long names/reasons and large filtered exports.
