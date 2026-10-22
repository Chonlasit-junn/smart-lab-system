# Registration OTP rollout

## Deployment order — operator action required

1. Back up the database normally. Review and manually run
   `backend/migrations/014_registration_otp_security.sql` in the Supabase SQL
   Editor. Do not execute it against production as part of automated tests.
2. Configure a stable, random `OTP_SECRET_KEY` of at least 32 bytes in the Backend
   deployment's secret store. The code can use the environment's `SECRET_KEY`
   if it is at least 32 bytes, but never uses the legacy source-code fallback.
   Do not put either secret in the Frontend or Git. Rotating this key invalidates
   outstanding codes; users must request new ones.
3. Confirm `BREVO_API_KEY` and `SENDER_EMAIL` are configured for the existing mail
   service. Missing configuration now correctly returns an unavailable response
   rather than claiming a code was delivered. The mail text says 10 minutes.
4. Deploy Backend, then Frontend. Stop using the old Backend when switching:
   old versions still accept legacy plaintext OTPs. Existing login/account data
   is unaffected. Users partway through registration must request a fresh code.
5. Test a new student and guest registration, both languages, resend, expiry,
   attempt exhaustion, and an email delivery failure in a test environment.

The new `registration_otps` table is deliberately excluded from the application's
startup `create_all()`. Deploying code does not replace the manual migration.
Migration 014 creates its primary key, checks and RLS together. It does not edit,
delete, import or validate legacy `user_otps` rows. No existing users, scores,
roles or sessions are changed. The table is Backend-only and has no client RLS
policies; the Backend must use an appropriately authorized database role.

## Behaviour

- One current challenge per canonical email; raw codes are sent only by email,
  never returned by the API, persisted in this table, or logged by the mail helper.
- Six-digit cryptographically random codes; HMAC-SHA256 binds each code to its
  email, issuance ID, and a server-side key.
- Ten-minute lifetime; sixty-second resend cooldown.
- Five wrong attempts per issuance, plus five wrong attempts per ten-minute
  window across resends. Both verify and register share those counters.
- Exhaustion restricts OTP verification/issuance, not login to an existing account.
- Verifying does not consume the code. Direct registration with a valid delivered
  code also remains supported. Consumption is committed with successful account
  creation; a failed account transaction does not consume the code.
- Registration rechecks the exact issuance after face processing and storage,
  immediately before commit. Expired/replaced/used codes cannot authorize a user.
- A delivery reservation invalidates the previous code. Pending or failed mail
  cannot authorize registration. A failed send keeps cooldown/budget; the user can
  request another code after the wait. Late delivery callbacks cannot change a
  newer issuance. No database row lock is held while awaiting the mail provider.
- String `detail` errors are retained for existing clients. The Frontend translates
  known errors, reads `Retry-After`, and preserves profile/image data when it
  returns to the OTP step. Client timers are informational; Backend enforces rules.

Rate limits are database-backed per email, not per worker memory. This change
does not add a site-wide/IP mail quota, CAPTCHA, or an external rate-limit service.
IP/global abuse controls can be configured separately at the hosting boundary.

## Local verification (no production DB/mail)

```powershell
.\backend\venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p test_registration_otp.py -q
.\backend\venv\Scripts\python.exe -B -m unittest discover -s backend/tests -q
cd frontend
npm test
npx --no-install eslint src/pages/Register.jsx src/utils/registrationOtp.js src/utils/locales.js tests/registrationOtp.test.js
npm run build
```

SQLite tests use synthetic data and mocked mail, face processing and storage.
They establish API/lifecycle behaviour, but not PostgreSQL lock scheduling.
Migration SQL and concurrent PostgreSQL scenarios must also be exercised on an
isolated local/test PostgreSQL database before production rollout.

`backend/tests/test_registration_otp_postgres.py` supplies opt-in migration/locking
tests. Set `SMART_LAB_TEST_POSTGRES_URL` to a disposable PostgreSQL database on
`localhost`, `127.0.0.1` or `::1`, named with the prefix `smartlab_test`, then run:

```powershell
.\backend\venv\Scripts\python.exe -B -m unittest discover -s backend/tests -p test_registration_otp_postgres.py -v
```

Never use `SQLALCHEMY_DATABASE_URL` or a production connection for these tests.
They reject non-loopback URLs and connection query overrides, apply the actual
migration only to a generated `otp_test_<uuid>` schema, and remove only that test
schema afterwards. Without the explicit test URL these five tests are skipped.
