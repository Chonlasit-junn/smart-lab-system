-- Align the database with the current application model after the additive migrations.
-- Run after 009_remove_booking_point_requirement.sql.
--
-- This migration is intentionally guarded. It stops instead of dropping data when
-- the live database no longer matches the audit that preceded this migration.

DO $$
DECLARE
    has_risky_usage boolean;
    program_usage_column_count integer;
BEGIN
    SELECT count(*)
    INTO program_usage_column_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'program_usage_logs'
      AND column_name IN ('description', 'device_name', 'device_mac', 'updated_at');

    -- Skip this preflight on a rerun after the redundant columns were removed.
    IF program_usage_column_count = 4 THEN
        EXECUTE $sql$
            SELECT EXISTS (
                SELECT 1
                FROM public.program_usage_logs p
                LEFT JOIN public.lab_access_logs l
                    ON l.id = p.lab_access_log_id
                WHERE p.description IS NOT NULL
                   OR l.id IS NULL
                   OR p.device_name IS DISTINCT FROM l.device_used
                   OR lower(trim(p.device_mac)) IS DISTINCT FROM lower(trim(l.device_mac))
            )
        $sql$ INTO has_risky_usage;

        IF has_risky_usage THEN
            RAISE EXCEPTION
                'Database cleanup stopped: program usage data needs manual review before removing duplicate columns.';
        END IF;
    END IF;

    IF to_regclass('public.permissions') IS NOT NULL THEN
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM public.permissions)' INTO has_risky_usage;
        IF has_risky_usage THEN
            RAISE EXCEPTION
                'Database cleanup stopped: permissions table is not empty and needs manual review.';
        END IF;
    END IF;

    IF to_regclass('public.role_permissions') IS NOT NULL THEN
        EXECUTE 'SELECT EXISTS (SELECT 1 FROM public.role_permissions)' INTO has_risky_usage;
        IF has_risky_usage THEN
            RAISE EXCEPTION
                'Database cleanup stopped: role_permissions table is not empty and needs manual review.';
        END IF;
    END IF;
END $$;

-- Booking access is controlled by active Ban records. The old score threshold
-- is no longer part of the policy contract.
ALTER TABLE public.point_policies
    DROP CONSTRAINT IF EXISTS point_policies_value_ranges_check,
    DROP CONSTRAINT IF EXISTS point_policies_threshold_order_check;

ALTER TABLE public.point_policies
    DROP COLUMN IF EXISTS booking_min_points;

ALTER TABLE public.point_policies
    ADD CONSTRAINT point_policies_value_ranges_check
    CHECK (
        daily_bonus BETWEEN 0 AND 10
        AND complete_session BETWEEN 0 AND 20
        AND no_show BETWEEN -100 AND 0
        AND forbidden_app BETWEEN -100 AND 0
        AND late_cancel BETWEEN -100 AND 0
        AND point_request_amount BETWEEN 1 AND 100
        AND warning_threshold BETWEEN 0 AND 100
        AND ban_level_1_below BETWEEN 1 AND 100
        AND ban_level_1_days BETWEEN 0 AND 365
        AND ban_level_2_below BETWEEN 1 AND 100
        AND ban_level_2_days BETWEEN 0 AND 365
        AND ban_level_3_below BETWEEN 1 AND 100
        AND ban_level_3_days BETWEEN 0 AND 365
        AND ban_level_4_below BETWEEN 1 AND 100
        AND ban_level_4_days BETWEEN 0 AND 365
    ) NOT VALID;

ALTER TABLE public.point_policies
    ADD CONSTRAINT point_policies_threshold_order_check
    CHECK (
        ban_level_1_below < ban_level_2_below
        AND ban_level_2_below < ban_level_3_below
        AND ban_level_3_below < ban_level_4_below
    ) NOT VALID;

-- Device identity belongs to the parent session. Reports can still expose it by
-- joining program_usage_logs.lab_access_log_id to lab_access_logs.id.
ALTER TABLE public.program_usage_logs
    DROP COLUMN IF EXISTS description,
    DROP COLUMN IF EXISTS device_name,
    DROP COLUMN IF EXISTS device_mac,
    DROP COLUMN IF EXISTS updated_at;

-- These tables are present in the legacy schema but are not part of the current
-- application model and are empty in the audited database.
DROP TABLE IF EXISTS public.role_permissions;
DROP TABLE IF EXISTS public.permissions;

-- Enforce the one-profile-per-user rule represented by the application model.
DROP INDEX IF EXISTS public.idx_students_user_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_students_user_id
    ON public.students (user_id);

DROP INDEX IF EXISTS public.idx_user_passport_user_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_passport_user_id
    ON public.user_passport (user_id);

-- Match the users.id type before adding the missing ticket relationship.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'tickets'
          AND column_name = 'user_id'
          AND udt_name = 'int4'
    ) THEN
        ALTER TABLE public.tickets
            ALTER COLUMN user_id TYPE bigint
            USING user_id::bigint;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'tickets_user_id_fkey'
          AND conrelid = 'public.tickets'::regclass
    ) THEN
        ALTER TABLE public.tickets
            ADD CONSTRAINT tickets_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES public.users(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_tickets_user_id
    ON public.tickets (user_id);
