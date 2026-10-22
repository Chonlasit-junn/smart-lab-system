# Password recovery with OTP

## Operator rollout (no automatic production migration)

1. Review and run `backend/migrations/015_password_reset_otp.sql` manually, with
   a normal database backup. It creates `password_reset_otps`, its PK/checks/RLS,
   revokes client grants, and adds `users.auth_version` (default 0). Existing
   passwords, roles, profiles, approvals and registration OTPs are unchanged.
   Run once; `CREATE TABLE` intentionally fails if the table already exists
   rather than silently accepting an incompatible schema. The transaction rolls
   back on failure. On lock timeout, retry during a quiet period.
2. Keep the existing stable Backend `OTP_SECRET_KEY`, `SECRET_KEY`,
   `BREVO_API_KEY`, and verified `SENDER_EMAIL`. No new Frontend secret is needed.
3. Deploy Backend, then Frontend. Stop all old Backend versions: old versions
   cannot enforce `auth_version` revocation. Deploying new code before migration
   will fail when querying users; do not rely on startup `create_all()` to alter
   existing tables. The new OTP table is excluded from startup DDL.
4. QA on disposable accounts: request, immediate resend (429 + Retry-After),
   resend after 60 seconds, old code rejection, incorrect guesses (5 / 10-minute
   window, not reset by resend), expiry after 10 minutes, success, replay,
   old/new password login, and old web token rejection. Check student, guest
   pending approval, and admin without changing their roles/approval states.

## Contract and isolation

- `POST /password-reset/request-otp`: JSON `{email}`. Same success body and
  advertised durations whether the account exists or not. Mail failures also
  keep the generic response; no account existence or provider details returned.
  Both known and unknown emails have persistent per-email cooldown/budgets.
  This is not constant-time across SMTP/network paths; configure gateway-level
  request/IP rate limiting before exposing to high-volume hostile traffic.
- `POST /password-reset/verify-otp`: JSON `{email, otp}`. Does not consume or
  create a separate reusable reset token.
- `POST /password-reset/confirm`: JSON `{email, otp, new_password}`. Rechecks the
  original OTP under a row lock after hashing, then locks the user. Password
  update, `auth_version` increment and OTP consumption commit together.
- New passwords: at least 8 characters, non-whitespace, maximum 72 UTF-8 bytes
  to avoid bcrypt truncation. Backend validates independently of the UI.
- Separate table and HMAC purpose namespace from registration. An OTP is bound
  to the account ID and HMAC fingerprint of its password hash at issuance;
  changing/deleting the account invalidates outstanding recovery challenges.
- Pending/failed delivery cannot authorize a reset. No plaintext code stored
  or logged. Only a successful final reset consumes it. No automatic login.
- Existing legacy web tokens remain valid while `auth_version=0`; resetting
  invalidates old legacy/versioned web tokens for that account. Newly issued
  login tokens contain the current version. Device credentials and offline
  signed policy snapshots are not web login tokens and are not revoked here.
- RLS has no client policies and client grants are revoked. Backend needs an
  appropriately authorized database role. Do not add Frontend access policies.
- UI `/forgot-password` is lazy loaded, supports Thai/English and theme tokens,
  prevents overlapping requests, cancels requests when leaving the page, and
  keeps passwords/OTP only in component memory (never URLs/localStorage).

## Verification

All automated API tests use in-memory SQLite and mocked mail. No production
database, SMTP account or real user is required. SQLite does not prove
PostgreSQL row-lock concurrency semantics. Run optional PostgreSQL integration
tests only against an explicitly isolated local test database; never the app URL.
