-- Run manually with operator approval BEFORE deploying the new Backend.
-- Additive: no existing accounts or public.user_otps rows are changed/deleted.
-- Old plaintext OTPs are intentionally NOT imported; users request a fresh code.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE TABLE IF NOT EXISTS public.registration_otps (
    email text PRIMARY KEY,
    challenge_id varchar(32),
    code_hash varchar(64),
    expires_at timestamptz,
    delivered_at timestamptz,
    consumed_at timestamptz,
    last_sent_at timestamptz,
    failed_attempts integer NOT NULL DEFAULT 0,
    window_attempts integer NOT NULL DEFAULT 0,
    attempt_window_started_at timestamptz,
    CONSTRAINT registration_otps_email_check CHECK (
        email = lower(btrim(email)) AND email <> ''
    ),
    CONSTRAINT registration_otps_attempts_check CHECK (
        failed_attempts BETWEEN 0 AND 5 AND window_attempts BETWEEN 0 AND 5
    )
);

-- Backend-only state. No anon/authenticated policies or public read access.
ALTER TABLE public.registration_otps ENABLE ROW LEVEL SECURITY;
COMMIT;
