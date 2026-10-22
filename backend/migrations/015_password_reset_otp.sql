-- Operator-run only, BEFORE deploying Backend. No passwords/accounts are deleted.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS auth_version integer NOT NULL DEFAULT 0;

CREATE TABLE public.password_reset_otps (
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
    user_id bigint REFERENCES public.users(id) ON DELETE CASCADE,
    credential_hash varchar(64),
    CONSTRAINT password_reset_otps_email_check CHECK (email = lower(btrim(email)) AND email <> ''),
    CONSTRAINT password_reset_otps_attempts_check CHECK (
        failed_attempts BETWEEN 0 AND 5 AND window_attempts BETWEEN 0 AND 5
    )
);
ALTER TABLE public.password_reset_otps ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.password_reset_otps FROM PUBLIC;
-- These client roles exist on Supabase, but need not exist on self-hosted PostgreSQL.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.password_reset_otps FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.password_reset_otps FROM authenticated;
    END IF;
END;
$$;
COMMIT;
