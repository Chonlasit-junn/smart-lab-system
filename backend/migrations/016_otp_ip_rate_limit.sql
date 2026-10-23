-- Operator-run only, BEFORE deploying Backend. No user or OTP rows are changed.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE TABLE IF NOT EXISTS public.otp_ip_rate_limits (
    ip_hash varchar(64) PRIMARY KEY,
    window_started_at timestamptz NOT NULL,
    request_count integer NOT NULL DEFAULT 0,
    CONSTRAINT otp_ip_rate_limits_request_count_check CHECK (request_count >= 0)
);
CREATE INDEX IF NOT EXISTS idx_otp_ip_rate_limits_window_started_at
    ON public.otp_ip_rate_limits (window_started_at);

ALTER TABLE public.otp_ip_rate_limits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.otp_ip_rate_limits FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.otp_ip_rate_limits FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.otp_ip_rate_limits FROM authenticated;
    END IF;
END;
$$;
COMMIT;
