-- Align the schema with the PostgreSQL model used by the current Backend.
-- Run after migrations 001-019, in a maintenance window. This migration does
-- not repair or delete rows: known violations stop at preflight; any later
-- validation error rolls back the entire transaction.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $$
BEGIN
    IF to_regclass('public.registration_otps') IS NULL
       OR to_regclass('public.password_reset_otps') IS NULL
       OR to_regclass('public.otp_ip_rate_limits') IS NULL
       OR to_regclass('public.gatekeeper_scan_logs') IS NULL
       OR to_regclass('public.ticket_replies') IS NULL THEN
        RAISE EXCEPTION 'Schema alignment stopped: run migrations 014-019 first.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM public.users
        WHERE first_name IS NULL OR btrim(first_name) = ''
           OR last_name IS NULL OR btrim(last_name) = ''
           OR email IS NULL OR email <> lower(btrim(email)) OR btrim(email) = ''
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: users contain missing names or noncanonical emails.';
    END IF;
    IF EXISTS (
        SELECT lower(btrim(email)) FROM public.users
        GROUP BY lower(btrim(email)) HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: canonical user emails are duplicated.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.students WHERE user_id IS NULL)
       OR EXISTS (
            SELECT user_id FROM public.students
            GROUP BY user_id HAVING count(*) > 1
       ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: student profiles have missing or duplicate owners.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.user_passport WHERE user_id IS NULL)
       OR EXISTS (
            SELECT user_id FROM public.user_passport
            GROUP BY user_id HAVING count(*) > 1
       ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: guest profiles have missing or duplicate owners.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.bookings
        WHERE user_id IS NULL OR total_participants IS NULL OR total_participants <= 0
           OR start_time >= end_time
           OR status NOT IN ('reserved', 'attended', 'completed', 'cancelled', 'no_show')
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: bookings contain invalid owner, participant, time, or status values.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.lab_access_logs
        WHERE entry_time IS NULL OR access_type IS NULL OR access_type NOT IN ('entry', 'manual')
           OR status IS NULL OR status NOT IN ('success', 'denied')
           OR session_status NOT IN ('active', 'completed', 'abandoned')
           OR (exit_time IS NOT NULL AND exit_time < entry_time)
           OR (session_status = 'active' AND exit_time IS NOT NULL)
           OR (session_status IN ('completed', 'abandoned') AND exit_time IS NULL)
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: access logs contain invalid lifecycle or status values.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.program_usage_logs
        WHERE usage_start_time IS NULL OR usage_end_time IS NULL
           OR duration_seconds IS NULL OR duration_seconds < 0
           OR usage_end_time < usage_start_time
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: program usage logs contain invalid times or durations.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.class_schedules
        WHERE course_code IS NULL OR btrim(course_code) = ''
           OR start_time IS NULL OR end_time IS NULL OR start_time >= end_time
           OR day_of_week IS NULL OR semester IS NULL OR academic_year IS NULL
           OR valid_from IS NULL OR valid_until IS NULL OR valid_from > valid_until
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: class schedules contain incomplete or invalid ranges.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.registration_otps
        WHERE failed_attempts NOT BETWEEN 0 AND 5 OR window_attempts NOT BETWEEN 0 AND 5
    ) OR EXISTS (
        SELECT 1 FROM public.password_reset_otps
        WHERE failed_attempts NOT BETWEEN 0 AND 5 OR window_attempts NOT BETWEEN 0 AND 5
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: OTP attempt counters are outside the allowed range.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.registration_otps
        WHERE email IS NULL OR email <> lower(btrim(email)) OR btrim(email) = ''
    ) OR EXISTS (
        SELECT 1 FROM public.password_reset_otps
        WHERE email IS NULL OR email <> lower(btrim(email)) OR btrim(email) = ''
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: OTP tables contain noncanonical emails.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.point_policies
        WHERE daily_bonus NOT BETWEEN 0 AND 10
           OR complete_session NOT BETWEEN 0 AND 20
           OR no_show NOT BETWEEN -100 AND 0
           OR forbidden_app NOT BETWEEN -100 AND 0
           OR late_cancel NOT BETWEEN -100 AND 0
           OR point_request_amount NOT BETWEEN 1 AND 100
           OR warning_threshold NOT BETWEEN 0 AND 100
           OR ban_level_1_below NOT BETWEEN 1 AND 100
           OR ban_level_1_days NOT BETWEEN 0 AND 365
           OR ban_level_2_below NOT BETWEEN 1 AND 100
           OR ban_level_2_days NOT BETWEEN 0 AND 365
           OR ban_level_3_below NOT BETWEEN 1 AND 100
           OR ban_level_3_days NOT BETWEEN 0 AND 365
           OR ban_level_4_below NOT BETWEEN 1 AND 100
           OR ban_level_4_days NOT BETWEEN 0 AND 365
           OR NOT (ban_level_1_below < ban_level_2_below
               AND ban_level_2_below < ban_level_3_below
               AND ban_level_3_below < ban_level_4_below)
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: point policy values need review.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.blacklisted_apps
        WHERE match_type NOT IN ('process_name', 'process_name_or_title', 'exe_path', 'window_title', 'website_domain')
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: blacklist contains an unsupported match type.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.labs
        WHERE (capacity IS NOT NULL AND capacity < 0)
           OR (status IS NOT NULL AND status NOT IN ('active', 'inactive', 'maintenance'))
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: lab capacity or status needs review.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.lab_devices WHERE status NOT IN ('active', 'maintenance', 'revoked')) THEN
        RAISE EXCEPTION 'Schema alignment stopped: lab devices contain an unsupported status.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.otp_ip_rate_limits WHERE length(ip_hash) <> 64 OR request_count < 0) THEN
        RAISE EXCEPTION 'Schema alignment stopped: OTP IP rate-limit rows are malformed.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.point_policies WHERE id <> 1) THEN
        RAISE EXCEPTION 'Schema alignment stopped: point_policies contains a non-singleton ID.';
    END IF;
    IF EXISTS (SELECT 1 FROM public.user_points WHERE points NOT BETWEEN 0 AND 100)
       OR EXISTS (SELECT 1 FROM public.user_daily_scores WHERE score NOT BETWEEN 0 AND 100) THEN
        RAISE EXCEPTION 'Schema alignment stopped: points or daily scores are outside 0-100.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.point_requests
        WHERE requested_points NOT BETWEEN 1 AND 100
           OR status NOT IN ('pending', 'approved', 'rejected')
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: point requests contain invalid values.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.gatekeeper_scan_logs
        WHERE decision NOT IN ('granted', 'denied')
           OR (liveness_score IS NOT NULL AND (liveness_score < 0 OR liveness_score > 1))
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: Gatekeeper scan logs contain invalid decisions or scores.';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.ticket_replies
        WHERE message IS NULL OR length(btrim(message)) NOT BETWEEN 1 AND 5000
           OR status NOT IN ('received', 'in_progress', 'resolved')
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: ticket replies contain invalid messages or statuses.';
    END IF;

    IF EXISTS (
        SELECT client_session_id FROM public.lab_access_logs
        WHERE client_session_id IS NOT NULL AND btrim(client_session_id) <> ''
        GROUP BY client_session_id HAVING count(*) > 1
    ) OR EXISTS (
        SELECT user_id FROM public.lab_access_logs
        WHERE session_status = 'active' AND exit_time IS NULL
        GROUP BY user_id HAVING count(*) > 1
    ) OR EXISTS (
        SELECT lab_device_id FROM public.lab_access_logs
        WHERE lab_device_id IS NOT NULL
          AND session_status = 'active' AND exit_time IS NULL
        GROUP BY lab_device_id HAVING count(*) > 1
    ) OR EXISTS (
        SELECT lower(btrim(device_mac)) FROM public.lab_access_logs
        WHERE session_status = 'active' AND exit_time IS NULL
          AND device_mac IS NOT NULL AND btrim(device_mac) <> ''
        GROUP BY lower(btrim(device_mac)) HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: active session keys are duplicated.';
    END IF;
    IF EXISTS (
        SELECT event_id FROM public.program_usage_logs
        WHERE event_id IS NOT NULL AND btrim(event_id) <> ''
        GROUP BY event_id HAVING count(*) > 1
    ) OR EXISTS (
        SELECT event_id FROM public.usage_violations
        WHERE event_id IS NOT NULL AND btrim(event_id) <> ''
        GROUP BY event_id HAVING count(*) > 1
    ) OR EXISTS (
        SELECT event_id FROM public.point_logs
        WHERE event_id IS NOT NULL AND btrim(event_id) <> ''
        GROUP BY event_id HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: idempotency event keys are duplicated.';
    END IF;
    IF EXISTS (
        SELECT user_id FROM public.point_requests WHERE status = 'pending'
        GROUP BY user_id HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'Schema alignment stopped: a user has multiple pending point requests.';
    END IF;
END;
$$;

-- Widen child keys to match the BIGINT user/lab primary keys. Existing values
-- are range-safe; constraints are replaced transactionally and validated below.
ALTER TABLE public.lab_devices DROP CONSTRAINT IF EXISTS lab_devices_lab_id_fkey;
ALTER TABLE public.lab_device_enrollments
    DROP CONSTRAINT IF EXISTS lab_device_enrollments_lab_id_fkey,
    DROP CONSTRAINT IF EXISTS lab_device_enrollments_created_by_fkey;
ALTER TABLE public.user_points DROP CONSTRAINT IF EXISTS user_points_user_id_fkey;
ALTER TABLE public.point_logs DROP CONSTRAINT IF EXISTS point_logs_user_id_fkey;
ALTER TABLE public.ban_records DROP CONSTRAINT IF EXISTS ban_records_user_id_fkey;
ALTER TABLE public.user_daily_scores DROP CONSTRAINT IF EXISTS user_daily_scores_user_id_fkey;
ALTER TABLE public.point_requests
    DROP CONSTRAINT IF EXISTS point_requests_user_id_fkey,
    DROP CONSTRAINT IF EXISTS point_requests_reviewed_by_fkey;
ALTER TABLE public.point_policies DROP CONSTRAINT IF EXISTS point_policies_updated_by_fkey;
ALTER TABLE public.gatekeeper_scan_logs
    DROP CONSTRAINT IF EXISTS gatekeeper_scan_logs_lab_id_fkey,
    DROP CONSTRAINT IF EXISTS gatekeeper_scan_logs_user_id_fkey,
    DROP CONSTRAINT IF EXISTS gatekeeper_scan_logs_booking_id_fkey;
ALTER TABLE public.password_reset_otps DROP CONSTRAINT IF EXISTS password_reset_otps_user_id_fkey;
ALTER TABLE public.ticket_replies
    DROP CONSTRAINT IF EXISTS ticket_replies_ticket_id_fkey,
    DROP CONSTRAINT IF EXISTS ticket_replies_admin_id_fkey;

ALTER TABLE public.lab_devices
    ALTER COLUMN lab_id TYPE bigint USING lab_id::bigint;
ALTER TABLE public.lab_device_enrollments
    ALTER COLUMN lab_id TYPE bigint USING lab_id::bigint,
    ALTER COLUMN created_by TYPE bigint USING created_by::bigint;
ALTER TABLE public.user_points
    ALTER COLUMN user_id TYPE bigint USING user_id::bigint;
ALTER TABLE public.point_logs
    ALTER COLUMN user_id TYPE bigint USING user_id::bigint;
ALTER TABLE public.ban_records
    ALTER COLUMN user_id TYPE bigint USING user_id::bigint;
ALTER TABLE public.user_daily_scores
    ALTER COLUMN user_id TYPE bigint USING user_id::bigint;
ALTER TABLE public.point_requests
    ALTER COLUMN user_id TYPE bigint USING user_id::bigint,
    ALTER COLUMN reviewed_by TYPE bigint USING reviewed_by::bigint;
ALTER TABLE public.point_policies
    ALTER COLUMN updated_by TYPE bigint USING updated_by::bigint;
ALTER TABLE public.gatekeeper_scan_logs
    ALTER COLUMN lab_id TYPE bigint USING lab_id::bigint,
    ALTER COLUMN user_id TYPE bigint USING user_id::bigint;
ALTER TABLE public.ticket_replies
    ALTER COLUMN admin_id TYPE bigint USING admin_id::bigint;

ALTER TABLE public.lab_devices
    ADD CONSTRAINT lab_devices_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) NOT VALID;
ALTER TABLE public.lab_device_enrollments
    ADD CONSTRAINT lab_device_enrollments_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) NOT VALID,
    ADD CONSTRAINT lab_device_enrollments_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) NOT VALID;
ALTER TABLE public.user_points
    ADD CONSTRAINT user_points_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) NOT VALID;
ALTER TABLE public.point_logs
    ADD CONSTRAINT point_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) NOT VALID;
ALTER TABLE public.ban_records
    ADD CONSTRAINT ban_records_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) NOT VALID;
ALTER TABLE public.user_daily_scores
    ADD CONSTRAINT user_daily_scores_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) NOT VALID;
ALTER TABLE public.point_requests
    ADD CONSTRAINT point_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) NOT VALID,
    ADD CONSTRAINT point_requests_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id) NOT VALID;
ALTER TABLE public.point_policies
    ADD CONSTRAINT point_policies_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id) NOT VALID;
ALTER TABLE public.gatekeeper_scan_logs
    ADD CONSTRAINT gatekeeper_scan_logs_lab_id_fkey FOREIGN KEY (lab_id) REFERENCES public.labs(id) ON DELETE SET NULL NOT VALID,
    ADD CONSTRAINT gatekeeper_scan_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL NOT VALID,
    ADD CONSTRAINT gatekeeper_scan_logs_booking_id_fkey FOREIGN KEY (booking_id) REFERENCES public.bookings(id) ON DELETE SET NULL NOT VALID;
ALTER TABLE public.password_reset_otps
    ADD CONSTRAINT password_reset_otps_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE NOT VALID;
ALTER TABLE public.ticket_replies
    ADD CONSTRAINT ticket_replies_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.tickets(id) ON DELETE CASCADE NOT VALID,
    ADD CONSTRAINT ticket_replies_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES public.users(id) ON DELETE SET NULL NOT VALID;

ALTER TABLE public.users
    ALTER COLUMN first_name SET NOT NULL,
    ALTER COLUMN last_name SET NOT NULL;
ALTER TABLE public.students ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.user_passport ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.bookings
    ALTER COLUMN user_id SET NOT NULL,
    ALTER COLUMN total_participants SET NOT NULL;
ALTER TABLE public.lab_access_logs
    ALTER COLUMN entry_time SET NOT NULL,
    ALTER COLUMN access_type SET NOT NULL,
    ALTER COLUMN status SET NOT NULL;
ALTER TABLE public.program_usage_logs
    ALTER COLUMN usage_start_time SET NOT NULL,
    ALTER COLUMN usage_end_time SET NOT NULL,
    ALTER COLUMN duration_seconds SET NOT NULL;
ALTER TABLE public.class_schedules
    ALTER COLUMN course_code SET NOT NULL,
    ALTER COLUMN start_time SET NOT NULL,
    ALTER COLUMN end_time SET NOT NULL,
    ALTER COLUMN day_of_week SET NOT NULL,
    ALTER COLUMN semester SET NOT NULL,
    ALTER COLUMN academic_year SET NOT NULL,
    ALTER COLUMN valid_from SET NOT NULL,
    ALTER COLUMN valid_until SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.users'::regclass AND conname='users_email_canonical_check') THEN
        ALTER TABLE public.users ADD CONSTRAINT users_email_canonical_check
            CHECK (email = lower(btrim(email)) AND btrim(email) <> '') NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.users'::regclass AND conname='users_names_nonblank_check') THEN
        ALTER TABLE public.users ADD CONSTRAINT users_names_nonblank_check
            CHECK (btrim(first_name) <> '' AND btrim(last_name) <> '') NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.labs'::regclass AND conname='labs_capacity_nonnegative_check') THEN
        ALTER TABLE public.labs ADD CONSTRAINT labs_capacity_nonnegative_check
            CHECK (capacity IS NULL OR capacity >= 0) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.labs'::regclass AND conname='labs_status_check') THEN
        ALTER TABLE public.labs ADD CONSTRAINT labs_status_check
            CHECK (status IS NULL OR status IN ('active', 'inactive', 'maintenance')) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.lab_access_logs'::regclass AND conname='lab_access_logs_access_type_check') THEN
        ALTER TABLE public.lab_access_logs ADD CONSTRAINT lab_access_logs_access_type_check
            CHECK (access_type IN ('entry', 'manual')) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.lab_access_logs'::regclass AND conname='lab_access_logs_status_check') THEN
        ALTER TABLE public.lab_access_logs ADD CONSTRAINT lab_access_logs_status_check
            CHECK (status IN ('success', 'denied')) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.lab_access_logs'::regclass AND conname='lab_access_logs_session_status_check') THEN
        ALTER TABLE public.lab_access_logs ADD CONSTRAINT lab_access_logs_session_status_check
            CHECK (session_status IN ('active', 'completed', 'abandoned')) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.lab_access_logs'::regclass AND conname='lab_access_logs_session_time_check') THEN
        ALTER TABLE public.lab_access_logs ADD CONSTRAINT lab_access_logs_session_time_check
            CHECK ((session_status = 'active' AND exit_time IS NULL) OR
                   (session_status IN ('completed', 'abandoned') AND exit_time IS NOT NULL)) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.lab_access_logs'::regclass AND conname='lab_access_logs_time_order_check') THEN
        ALTER TABLE public.lab_access_logs ADD CONSTRAINT lab_access_logs_time_order_check
            CHECK (exit_time IS NULL OR exit_time >= entry_time) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.program_usage_logs'::regclass AND conname='program_usage_logs_time_order_check') THEN
        ALTER TABLE public.program_usage_logs ADD CONSTRAINT program_usage_logs_time_order_check
            CHECK (usage_end_time >= usage_start_time) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.class_schedules'::regclass AND conname='class_schedules_time_order_check') THEN
        ALTER TABLE public.class_schedules ADD CONSTRAINT class_schedules_time_order_check
            CHECK (start_time < end_time) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.class_schedules'::regclass AND conname='class_schedules_date_order_check') THEN
        ALTER TABLE public.class_schedules ADD CONSTRAINT class_schedules_date_order_check
            CHECK (valid_from <= valid_until) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.bookings'::regclass AND conname='bookings_participants_positive_check') THEN
        ALTER TABLE public.bookings ADD CONSTRAINT bookings_participants_positive_check
            CHECK (total_participants > 0) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.bookings'::regclass AND conname='bookings_time_order_check') THEN
        ALTER TABLE public.bookings ADD CONSTRAINT bookings_time_order_check
            CHECK (start_time < end_time) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.registration_otps'::regclass AND conname='registration_otps_attempts_check') THEN
        ALTER TABLE public.registration_otps ADD CONSTRAINT registration_otps_attempts_check
            CHECK (failed_attempts BETWEEN 0 AND 5 AND window_attempts BETWEEN 0 AND 5) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.registration_otps'::regclass AND conname='registration_otps_email_check') THEN
        ALTER TABLE public.registration_otps ADD CONSTRAINT registration_otps_email_check
            CHECK (email = lower(btrim(email)) AND btrim(email) <> '') NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.password_reset_otps'::regclass AND conname='password_reset_otps_attempts_check') THEN
        ALTER TABLE public.password_reset_otps ADD CONSTRAINT password_reset_otps_attempts_check
            CHECK (failed_attempts BETWEEN 0 AND 5 AND window_attempts BETWEEN 0 AND 5) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.password_reset_otps'::regclass AND conname='password_reset_otps_email_check') THEN
        ALTER TABLE public.password_reset_otps ADD CONSTRAINT password_reset_otps_email_check
            CHECK (email = lower(btrim(email)) AND btrim(email) <> '') NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.otp_ip_rate_limits'::regclass AND conname='otp_ip_rate_limits_hash_length_check') THEN
        ALTER TABLE public.otp_ip_rate_limits ADD CONSTRAINT otp_ip_rate_limits_hash_length_check
            CHECK (length(ip_hash) = 64) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.point_policies'::regclass AND conname='point_policies_singleton_check') THEN
        ALTER TABLE public.point_policies ADD CONSTRAINT point_policies_singleton_check
            CHECK (id = 1) NOT VALID;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.program_usage_logs'::regclass AND conname='program_usage_logs_duration_nonnegative_check') THEN
        ALTER TABLE public.program_usage_logs ADD CONSTRAINT program_usage_logs_duration_nonnegative_check
            CHECK (duration_seconds >= 0) NOT VALID;
    END IF;
END;
$$;

-- Replace these definitions so the final bounds no longer depend on the
-- removed booking_min_points setting.
ALTER TABLE public.point_policies
    DROP CONSTRAINT IF EXISTS point_policies_value_ranges_check,
    DROP CONSTRAINT IF EXISTS point_policies_threshold_order_check;
ALTER TABLE public.point_policies
    ADD CONSTRAINT point_policies_value_ranges_check CHECK (
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
    ) NOT VALID,
    ADD CONSTRAINT point_policies_threshold_order_check CHECK (
        ban_level_1_below < ban_level_2_below
        AND ban_level_2_below < ban_level_3_below
        AND ban_level_3_below < ban_level_4_below
    ) NOT VALID;

ALTER TABLE public.blacklisted_apps
    DROP CONSTRAINT IF EXISTS blacklisted_apps_match_type_check;
ALTER TABLE public.blacklisted_apps
    ADD CONSTRAINT blacklisted_apps_match_type_check CHECK (match_type IN (
        'process_name', 'process_name_or_title', 'exe_path', 'window_title', 'website_domain'
    )) NOT VALID;

-- Enforce one profile per user and idempotent retries at the database layer.
-- Migration 010 upgrades the earlier non-unique profile indexes to unique.
CREATE UNIQUE INDEX IF NOT EXISTS idx_students_user_id ON public.students (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_passport_user_id ON public.user_passport (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session_per_user
    ON public.lab_access_logs (user_id)
    WHERE session_status = 'active' AND exit_time IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session_per_lab_device
    ON public.lab_access_logs (lab_device_id)
    WHERE lab_device_id IS NOT NULL AND session_status = 'active' AND exit_time IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_session_per_mac
    ON public.lab_access_logs (lower(btrim(device_mac)))
    WHERE session_status = 'active' AND exit_time IS NULL
      AND device_mac IS NOT NULL AND btrim(device_mac) <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_lab_access_logs_client_session_id
    ON public.lab_access_logs (client_session_id)
    WHERE client_session_id IS NOT NULL AND btrim(client_session_id) <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_program_usage_logs_event_id
    ON public.program_usage_logs (event_id)
    WHERE event_id IS NOT NULL AND btrim(event_id) <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_usage_violations_event_id
    ON public.usage_violations (event_id)
    WHERE event_id IS NOT NULL AND btrim(event_id) <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_point_logs_event_id
    ON public.point_logs (event_id)
    WHERE event_id IS NOT NULL AND btrim(event_id) <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_point_requests_pending_user
    ON public.point_requests (user_id)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS ix_password_reset_otps_user_id
    ON public.password_reset_otps (user_id);
CREATE INDEX IF NOT EXISTS ix_lab_device_enrollments_created_by
    ON public.lab_device_enrollments (created_by);
CREATE INDEX IF NOT EXISTS ix_point_requests_reviewed_by
    ON public.point_requests (reviewed_by);
CREATE INDEX IF NOT EXISTS ix_ticket_replies_admin_id
    ON public.ticket_replies (admin_id);

ALTER TABLE public.users VALIDATE CONSTRAINT users_email_canonical_check;
ALTER TABLE public.users VALIDATE CONSTRAINT users_names_nonblank_check;
ALTER TABLE public.labs VALIDATE CONSTRAINT labs_capacity_nonnegative_check;
ALTER TABLE public.labs VALIDATE CONSTRAINT labs_status_check;
ALTER TABLE public.lab_access_logs VALIDATE CONSTRAINT lab_access_logs_access_type_check;
ALTER TABLE public.lab_access_logs VALIDATE CONSTRAINT lab_access_logs_status_check;
ALTER TABLE public.lab_access_logs VALIDATE CONSTRAINT lab_access_logs_session_status_check;
ALTER TABLE public.lab_access_logs VALIDATE CONSTRAINT lab_access_logs_session_time_check;
ALTER TABLE public.lab_access_logs VALIDATE CONSTRAINT lab_access_logs_time_order_check;
ALTER TABLE public.program_usage_logs VALIDATE CONSTRAINT program_usage_logs_time_order_check;
ALTER TABLE public.class_schedules VALIDATE CONSTRAINT class_schedules_time_order_check;
ALTER TABLE public.class_schedules VALIDATE CONSTRAINT class_schedules_date_order_check;
ALTER TABLE public.bookings VALIDATE CONSTRAINT bookings_participants_positive_check;
ALTER TABLE public.bookings VALIDATE CONSTRAINT bookings_time_order_check;
ALTER TABLE public.registration_otps VALIDATE CONSTRAINT registration_otps_attempts_check;
ALTER TABLE public.registration_otps VALIDATE CONSTRAINT registration_otps_email_check;
ALTER TABLE public.password_reset_otps VALIDATE CONSTRAINT password_reset_otps_attempts_check;
ALTER TABLE public.password_reset_otps VALIDATE CONSTRAINT password_reset_otps_email_check;
ALTER TABLE public.otp_ip_rate_limits VALIDATE CONSTRAINT otp_ip_rate_limits_hash_length_check;
ALTER TABLE public.point_policies VALIDATE CONSTRAINT point_policies_value_ranges_check;
ALTER TABLE public.point_policies VALIDATE CONSTRAINT point_policies_threshold_order_check;
ALTER TABLE public.point_policies VALIDATE CONSTRAINT point_policies_singleton_check;
ALTER TABLE public.blacklisted_apps VALIDATE CONSTRAINT blacklisted_apps_match_type_check;
ALTER TABLE public.program_usage_logs VALIDATE CONSTRAINT program_usage_logs_duration_nonnegative_check;
ALTER TABLE public.bookings VALIDATE CONSTRAINT bookings_status_check;
ALTER TABLE public.user_points VALIDATE CONSTRAINT user_points_range_check;
ALTER TABLE public.user_daily_scores VALIDATE CONSTRAINT user_daily_scores_range_check;
ALTER TABLE public.point_requests VALIDATE CONSTRAINT point_requests_status_check;
ALTER TABLE public.point_requests VALIDATE CONSTRAINT point_requests_amount_check;

ALTER TABLE public.lab_devices VALIDATE CONSTRAINT lab_devices_lab_id_fkey;
ALTER TABLE public.lab_device_enrollments VALIDATE CONSTRAINT lab_device_enrollments_lab_id_fkey;
ALTER TABLE public.lab_device_enrollments VALIDATE CONSTRAINT lab_device_enrollments_created_by_fkey;
ALTER TABLE public.user_points VALIDATE CONSTRAINT user_points_user_id_fkey;
ALTER TABLE public.point_logs VALIDATE CONSTRAINT point_logs_user_id_fkey;
ALTER TABLE public.ban_records VALIDATE CONSTRAINT ban_records_user_id_fkey;
ALTER TABLE public.user_daily_scores VALIDATE CONSTRAINT user_daily_scores_user_id_fkey;
ALTER TABLE public.point_requests VALIDATE CONSTRAINT point_requests_user_id_fkey;
ALTER TABLE public.point_requests VALIDATE CONSTRAINT point_requests_reviewed_by_fkey;
ALTER TABLE public.point_policies VALIDATE CONSTRAINT point_policies_updated_by_fkey;
ALTER TABLE public.gatekeeper_scan_logs VALIDATE CONSTRAINT gatekeeper_scan_logs_lab_id_fkey;
ALTER TABLE public.gatekeeper_scan_logs VALIDATE CONSTRAINT gatekeeper_scan_logs_user_id_fkey;
ALTER TABLE public.gatekeeper_scan_logs VALIDATE CONSTRAINT gatekeeper_scan_logs_booking_id_fkey;
ALTER TABLE public.password_reset_otps VALIDATE CONSTRAINT password_reset_otps_user_id_fkey;
ALTER TABLE public.ticket_replies VALIDATE CONSTRAINT ticket_replies_ticket_id_fkey;
ALTER TABLE public.ticket_replies VALIDATE CONSTRAINT ticket_replies_admin_id_fkey;

COMMIT;
