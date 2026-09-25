-- Normalize application timestamps to timezone-aware UTC storage.
-- Run after 011_lab_device_registration.sql.
-- Existing naive values are treated as UTC because the previous Backend and
-- PostgreSQL defaults recorded them using the server's UTC clock.
-- Review this assumption before running if the database was written by a
-- server configured with a non-UTC timezone.

DO $$
DECLARE
    column_spec text;
    target_table text;
    target_column text;
    target_type text;
    target_default text;
    columns_to_normalize text[] := ARRAY[
        'users.created_at',
        'users.updated_at',
        'roles.created_at',
        'roles.updated_at',
        'labs.created_at',
        'labs.updated_at',
        'students.created_at',
        'students.updated_at',
        'user_passport.created_at',
        'user_passport.updated_at',
        'lab_access_logs.entry_time',
        'lab_access_logs.exit_time',
        'lab_access_logs.created_at',
        'lab_access_logs.updated_at',
        'program_usage_logs.usage_start_time',
        'program_usage_logs.usage_end_time',
        'program_usage_logs.created_at',
        'class_schedules.created_at',
        'class_schedules.updated_at',
        'bookings.created_at',
        'bookings.updated_at',
        'usage_violations.detected_at'
    ];
BEGIN
    FOREACH column_spec IN ARRAY columns_to_normalize LOOP
        target_table := split_part(column_spec, '.', 1);
        target_column := split_part(column_spec, '.', 2);

        IF to_regclass(format('public.%I', target_table)) IS NULL THEN
            CONTINUE;
        END IF;

        SELECT c.data_type, c.column_default
        INTO target_type, target_default
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.table_name = target_table
          AND c.column_name = target_column;

        IF target_type = 'timestamp without time zone' THEN
            EXECUTE format(
                'ALTER TABLE public.%I ALTER COLUMN %I DROP DEFAULT',
                target_table,
                target_column
            );
            EXECUTE format(
                'ALTER TABLE public.%I ALTER COLUMN %I TYPE timestamptz USING %I AT TIME ZONE ''UTC''',
                target_table,
                target_column,
                target_column
            );
            IF target_default IS NOT NULL THEN
                EXECUTE format(
                    'ALTER TABLE public.%I ALTER COLUMN %I SET DEFAULT now()',
                    target_table,
                    target_column
                );
            END IF;
        END IF;
    END LOOP;
END $$;
