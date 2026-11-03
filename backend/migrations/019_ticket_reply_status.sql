-- Operator-run only, AFTER migration 018 and BEFORE deploying the Backend
-- that writes reply statuses. Existing replies are retained and backfilled.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

ALTER TABLE public.ticket_replies
    ADD COLUMN IF NOT EXISTS status varchar(24);

UPDATE public.ticket_replies
SET status = CASE WHEN is_resolved THEN 'resolved' ELSE 'in_progress' END
WHERE status IS NULL;

ALTER TABLE public.ticket_replies
    ALTER COLUMN status SET DEFAULT 'in_progress',
    ALTER COLUMN status SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ticket_replies_status_check'
          AND conrelid = 'public.ticket_replies'::regclass
    ) THEN
        ALTER TABLE public.ticket_replies
            ADD CONSTRAINT ticket_replies_status_check
            CHECK (status IN ('received', 'in_progress', 'resolved')) NOT VALID;
    END IF;
END;
$$;

ALTER TABLE public.ticket_replies
    VALIDATE CONSTRAINT ticket_replies_status_check;

COMMIT;
