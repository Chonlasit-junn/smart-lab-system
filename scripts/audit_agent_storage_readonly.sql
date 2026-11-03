-- Agent storage audit: metadata and aggregate counts only; no personal data.
-- Run against the existing production schema, not as a migration.
-- Recent checks cover 90 Asia/Bangkok calendar days including the partial today.
-- Daily row counts use segment START date; they do not allocate cross-midnight
-- durations. PDF reporting must split those intervals before totaling by day.
-- Estimated rows/dead tuples and index scans are statistics, not exact counts
-- or proof that an index is redundant. Exact totals are reported separately.
-- A timeout aborts this read-only transaction; issue ROLLBACK if the client
-- leaves it open. There is no VACUUM, ANALYZE, DDL, or data cleanup here.

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '20s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
SET LOCAL TIME ZONE 'UTC';

WITH
bounds AS (
    SELECT
        now() AS snapshot_at,
        (now() AT TIME ZONE 'Asia/Bangkok')::date AS today,
        (((now() AT TIME ZONE 'Asia/Bangkok')::date - 89)::timestamp
            AT TIME ZONE 'Asia/Bangkok') AS recent_start,
        (((now() AT TIME ZONE 'Asia/Bangkok')::date + 1)::timestamp
            AT TIME ZONE 'Asia/Bangkok') AS recent_end
),
table_sizes AS (
    SELECT
        c.relname AS table_name,
        c.relkind = 'p' AS partitioned_parent,
        pg_table_size(c.oid) AS data_and_toast_bytes,
        pg_indexes_size(c.oid) AS index_bytes,
        pg_total_relation_size(c.oid) AS total_bytes,
        c.reltuples::bigint AS estimated_rows,
        c.relrowsecurity AS rls_enabled,
        c.relforcerowsecurity AS rls_forced,
        c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user) AS current_role_is_owner,
        has_table_privilege(c.oid, 'SELECT') AS current_role_can_select,
        s.n_dead_tup AS estimated_dead_rows,
        s.last_autovacuum,
        s.last_autoanalyze
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
),
agent_indexes AS (
    SELECT
        t.relname AS table_name,
        i.relname AS index_name,
        pg_relation_size(i.oid) AS index_bytes,
        x.indisunique AS is_unique,
        x.indisvalid AS is_valid,
        s.idx_scan AS scans_since_statistics_reset,
        pg_get_indexdef(i.oid) AS definition
    FROM pg_index x
    JOIN pg_class t ON t.oid = x.indrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    JOIN pg_class i ON i.oid = x.indexrelid
    LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = i.oid
    WHERE n.nspname = 'public'
      AND t.relname IN ('program_usage_logs', 'lab_access_logs',
                        'usage_violations', 'lab_devices')
),
timestamp_columns AS (
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name IN ('program_usage_logs', 'lab_access_logs', 'usage_violations')
      AND (data_type LIKE 'timestamp%')
),
agent_constraints AS (
    SELECT
        t.relname AS table_name,
        c.conname AS constraint_name,
        c.contype AS constraint_type,
        c.convalidated AS validated,
        pg_get_constraintdef(c.oid) AS definition
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'public'
      AND t.relname IN ('program_usage_logs', 'lab_access_logs',
                        'usage_violations', 'lab_devices')
),
usage_quality AS (
    SELECT
        count(*) AS total_rows,
        min(p.usage_start_time) AS earliest_start,
        max(p.usage_end_time) AS latest_end,
        count(DISTINCT p.lab_access_log_id) AS sessions_with_usage,
        count(DISTINCT p.program_name) AS distinct_stored_program_names,
        count(DISTINCT lower(btrim(p.program_name))) AS distinct_normalized_program_names,
        count(*) FILTER (WHERE p.program_name IS NULL OR btrim(p.program_name) = '') AS missing_program_name,
        count(*) FILTER (WHERE p.event_id IS NULL OR btrim(p.event_id) = '') AS missing_event_id,
        count(*) FILTER (WHERE p.created_at IS NULL) AS missing_received_timestamp,
        count(*) FILTER (WHERE p.usage_start_time IS NULL OR p.usage_end_time IS NULL) AS missing_usage_timestamp,
        count(*) FILTER (WHERE p.usage_end_time < p.usage_start_time) AS end_before_start,
        count(*) FILTER (WHERE p.duration_seconds IS NULL OR p.duration_seconds < 0) AS invalid_duration,
        count(*) FILTER (
            WHERE p.usage_end_time >= p.usage_start_time
              AND abs(p.duration_seconds - extract(epoch FROM (p.usage_end_time - p.usage_start_time))) > 2
        ) AS reported_duration_differs_from_interval_gt_2s,
        count(*) FILTER (
            WHERE p.usage_end_time = p.usage_start_time AND p.duration_seconds > 0
        ) AS legacy_duration_without_time_interval,
        count(*) FILTER (
            WHERE p.usage_start_time > b.snapshot_at + interval '5 minutes'
               OR p.usage_end_time > b.snapshot_at + interval '5 minutes'
        ) AS future_usage_gt_5m,
        count(*) FILTER (
            WHERE p.usage_end_time - p.usage_start_time > interval '24 hours'
        ) AS intervals_longer_than_24h_to_review,
        count(*) FILTER (
            WHERE (p.usage_start_time AT TIME ZONE 'Asia/Bangkok')::date
               <> (p.usage_end_time AT TIME ZONE 'Asia/Bangkok')::date
        ) AS cross_midnight_segments,
        count(*) FILTER (WHERE p.created_at - p.usage_end_time > interval '1 hour') AS received_over_1h_after_usage,
        count(*) FILTER (WHERE p.created_at - p.usage_end_time > interval '1 day') AS received_over_1d_after_usage,
        count(*) FILTER (WHERE p.created_at - p.usage_end_time > interval '7 days') AS received_over_7d_after_usage,
        count(*) FILTER (WHERE p.usage_end_time - p.created_at > interval '5 minutes') AS usage_after_receipt_gt_5m,
        count(*) FILTER (WHERE p.usage_end_time < b.snapshot_at - interval '30 days') AS rows_ended_over_30d_ago,
        count(*) FILTER (WHERE p.usage_end_time < b.snapshot_at - interval '90 days') AS rows_ended_over_90d_ago,
        max(extract(epoch FROM (p.created_at - p.usage_end_time))) AS max_receipt_delay_seconds,
        max(p.duration_seconds) AS max_reported_segment_seconds
    FROM public.program_usage_logs p
    CROSS JOIN bounds b
),
usage_links AS (
    SELECT
        count(*) FILTER (WHERE a.id IS NULL) AS rows_without_parent_session,
        count(DISTINCT a.id) FILTER (WHERE a.lab_device_id IS NULL) AS usage_sessions_without_device_id,
        count(*) FILTER (WHERE a.lab_device_id IS NOT NULL AND d.id IS NULL) AS rows_with_missing_device_record,
        count(*) FILTER (WHERE a.access_type = 'entry') AS rows_linked_to_gatekeeper_scan,
        count(*) FILTER (
            WHERE p.usage_start_time < a.entry_time - interval '5 minutes'
        ) AS usage_before_session_gt_5m,
        count(*) FILTER (
            WHERE p.usage_end_time > a.exit_time + interval '5 minutes'
        ) AS usage_after_recorded_session_end_gt_5m
    FROM public.program_usage_logs p
    LEFT JOIN public.lab_access_logs a ON a.id = p.lab_access_log_id
    LEFT JOIN public.lab_devices d ON d.id = a.lab_device_id
),
session_quality AS (
    SELECT
        count(*) AS total_rows_including_gatekeeper,
        count(*) FILTER (WHERE a.access_type = 'manual') AS agent_session_rows,
        count(*) FILTER (WHERE a.access_type = 'entry') AS gatekeeper_scan_rows,
        count(*) FILTER (
            WHERE a.access_type IS NULL OR a.access_type NOT IN ('manual', 'entry')
        ) AS other_access_type_rows,
        count(*) FILTER (
            WHERE a.entry_time IS NULL OR a.exit_time < a.entry_time
        ) AS missing_start_or_reversed_times,
        count(*) FILTER (WHERE a.entry_time > b.snapshot_at + interval '5 minutes') AS future_entry_gt_5m,
        count(*) FILTER (
            WHERE (a.session_status = 'active' AND a.exit_time IS NOT NULL)
               OR (a.session_status IN ('completed', 'abandoned') AND a.exit_time IS NULL)
        ) AS inconsistent_session_state,
        count(*) FILTER (
            WHERE a.access_type = 'manual' AND a.session_status = 'active' AND a.exit_time IS NULL
        ) AS active_agent_sessions,
        count(*) FILTER (
            WHERE a.access_type = 'manual' AND a.session_status = 'active' AND a.exit_time IS NULL
              AND coalesce(a.last_heartbeat_at, a.entry_time) < b.snapshot_at - interval '2 minutes'
        ) AS active_agent_sessions_with_stale_heartbeat,
        count(*) FILTER (
            WHERE a.access_type = 'manual' AND a.lab_device_id IS NULL
        ) AS agent_sessions_without_device_id,
        count(*) FILTER (
            WHERE a.access_type = 'manual' AND (a.device_used IS NULL OR btrim(a.device_used) = '')
        ) AS agent_sessions_without_device_name_snapshot
    FROM public.lab_access_logs a
    CROSS JOIN bounds b
),
violation_quality AS (
    SELECT
        count(*) AS total_rows,
        min(v.detected_at) AS earliest_detection,
        max(v.detected_at) AS latest_detection,
        count(*) FILTER (WHERE a.id IS NULL) AS rows_without_parent_session,
        count(*) FILTER (WHERE v.detected_at IS NULL) AS missing_detection_time,
        count(*) FILTER (WHERE v.detected_at > b.snapshot_at + interval '5 minutes') AS future_detection_gt_5m,
        count(*) FILTER (WHERE v.event_id IS NULL OR btrim(v.event_id) = '') AS missing_event_id,
        count(*) FILTER (WHERE v.program_usage_log_id IS NOT NULL) AS rows_linked_to_raw_usage,
        count(*) FILTER (
            WHERE v.program_usage_log_id IS NOT NULL AND p.id IS NULL
        ) AS broken_raw_usage_references
    FROM public.usage_violations v
    LEFT JOIN public.lab_access_logs a ON a.id = v.lab_access_log_id
    LEFT JOIN public.program_usage_logs p ON p.id = v.program_usage_log_id
    CROSS JOIN bounds b
),
duplicate_usage_events AS (
    SELECT count(*) AS occurrences
    FROM public.program_usage_logs
    WHERE event_id IS NOT NULL AND btrim(event_id) <> ''
    GROUP BY event_id HAVING count(*) > 1
),
duplicate_violation_events AS (
    SELECT count(*) AS occurrences
    FROM public.usage_violations
    WHERE event_id IS NOT NULL AND btrim(event_id) <> ''
    GROUP BY event_id HAVING count(*) > 1
),
overlap_candidates AS (
    SELECT
        p.usage_start_time,
        max(p.usage_end_time) OVER (
            PARTITION BY p.lab_access_log_id
            ORDER BY p.usage_start_time, p.usage_end_time, p.id
            ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
        ) AS previous_max_end
    FROM public.program_usage_logs p
    CROSS JOIN bounds b
    WHERE p.usage_start_time >= b.recent_start AND p.usage_start_time < b.recent_end
      AND p.lab_access_log_id IS NOT NULL AND p.usage_end_time > p.usage_start_time
),
daily_program_groups AS (
    SELECT
        (p.usage_start_time AT TIME ZONE 'Asia/Bangkok')::date AS report_date,
        p.lab_access_log_id,
        lower(btrim(p.program_name)) AS program_key,
        count(*) AS raw_rows,
        sum(p.duration_seconds::bigint) AS reported_duration_seconds,
        count(*) FILTER (
            WHERE (p.usage_start_time AT TIME ZONE 'Asia/Bangkok')::date
               <> (p.usage_end_time AT TIME ZONE 'Asia/Bangkok')::date
        ) AS cross_midnight_rows
    FROM public.program_usage_logs p
    CROSS JOIN bounds b
    WHERE p.usage_start_time >= b.recent_start AND p.usage_start_time < b.recent_end
    GROUP BY 1, 2, 3
),
daily_usage AS (
    SELECT report_date, sum(raw_rows) AS usage_rows,
        count(DISTINCT lab_access_log_id) AS sessions_with_usage,
        count(*) AS approximate_summary_rows_using_current_names,
        sum(reported_duration_seconds) AS reported_seconds_grouped_by_start_date,
        sum(cross_midnight_rows) AS cross_midnight_rows
    FROM daily_program_groups GROUP BY report_date
),
daily_people_devices AS (
    SELECT
        (p.usage_start_time AT TIME ZONE 'Asia/Bangkok')::date AS report_date,
        count(DISTINCT a.user_id) AS users_with_usage,
        count(DISTINCT a.lab_device_id) AS registered_devices_with_usage
    FROM public.program_usage_logs p
    LEFT JOIN public.lab_access_logs a ON a.id = p.lab_access_log_id
    CROSS JOIN bounds b
    WHERE p.usage_start_time >= b.recent_start AND p.usage_start_time < b.recent_end
    GROUP BY 1
),
daily_ingestion AS (
    SELECT (p.created_at AT TIME ZONE 'Asia/Bangkok')::date AS report_date,
        count(*) AS usage_rows_received
    FROM public.program_usage_logs p CROSS JOIN bounds b
    WHERE p.created_at >= b.recent_start AND p.created_at < b.recent_end
    GROUP BY 1
),
daily_access AS (
    SELECT
        (a.entry_time AT TIME ZONE 'Asia/Bangkok')::date AS report_date,
        count(*) FILTER (WHERE a.access_type = 'manual') AS agent_sessions_started,
        count(*) FILTER (WHERE a.access_type = 'entry') AS gatekeeper_scans
    FROM public.lab_access_logs a CROSS JOIN bounds b
    WHERE a.entry_time >= b.recent_start AND a.entry_time < b.recent_end
    GROUP BY 1
),
daily_violations AS (
    SELECT (v.detected_at AT TIME ZONE 'Asia/Bangkok')::date AS report_date,
        count(*) AS violations
    FROM public.usage_violations v CROSS JOIN bounds b
    WHERE v.detected_at >= b.recent_start AND v.detected_at < b.recent_end
    GROUP BY 1
),
calendar AS (
    SELECT b.today - d.day_offset AS report_date
    FROM bounds b CROSS JOIN generate_series(0, 89) AS d(day_offset)
),
daily_report AS (
    SELECT
        c.report_date, c.report_date = b.today AS partial_day,
        coalesce(u.usage_rows, 0) AS usage_rows,
        coalesce(r.usage_rows_received, 0) AS usage_rows_received,
        coalesce(u.sessions_with_usage, 0) AS sessions_with_usage,
        coalesce(d.users_with_usage, 0) AS users_with_usage,
        coalesce(d.registered_devices_with_usage, 0) AS registered_devices_with_usage,
        coalesce(a.agent_sessions_started, 0) AS agent_sessions_started,
        coalesce(a.gatekeeper_scans, 0) AS gatekeeper_scans,
        coalesce(v.violations, 0) AS violations,
        coalesce(u.reported_seconds_grouped_by_start_date, 0) AS reported_seconds_grouped_by_start_date,
        coalesce(u.cross_midnight_rows, 0) AS cross_midnight_rows,
        coalesce(u.approximate_summary_rows_using_current_names, 0) AS approximate_summary_rows_using_current_names
    FROM calendar c CROSS JOIN bounds b
    LEFT JOIN daily_usage u USING (report_date)
    LEFT JOIN daily_people_devices d USING (report_date)
    LEFT JOIN daily_ingestion r USING (report_date)
    LEFT JOIN daily_access a USING (report_date)
    LEFT JOIN daily_violations v USING (report_date)
)
SELECT jsonb_build_object(
    'scope', jsonb_build_object(
        'snapshot_at_utc', b.snapshot_at,
        'transaction_read_only', current_setting('transaction_read_only'),
        'transaction_isolation', current_setting('transaction_isolation'),
        'server_version', current_setting('server_version'),
        'current_role_superuser', (SELECT rolsuper FROM pg_roles WHERE rolname = current_user),
        'current_role_bypasses_rls', (SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user),
        'report_timezone', 'Asia/Bangkok',
        'daily_window_start', b.today - 89,
        'daily_window_end_including_partial_today', b.today,
        'anomaly_totals_scope', 'all stored rows except overlap check (recent 90 days)',
        'daily_duration_rule', 'reported seconds grouped by segment START date; not midnight-split',
        'rollup_estimate_rule', 'date/session/lower-trimmed current program name; not verified executable identity',
        'index_statistics_reset_at', (SELECT stats_reset FROM pg_stat_database WHERE datname = current_database())
    ),
    'table_sizes', (SELECT jsonb_agg(to_jsonb(t) ORDER BY t.total_bytes DESC, t.table_name) FROM table_sizes t),
    'agent_indexes', (SELECT jsonb_agg(to_jsonb(i) ORDER BY i.table_name, i.index_bytes DESC, i.index_name) FROM agent_indexes i),
    'timestamp_columns', (SELECT jsonb_agg(to_jsonb(t) ORDER BY t.table_name, t.column_name) FROM timestamp_columns t),
    'agent_constraints', (SELECT jsonb_agg(to_jsonb(c) ORDER BY c.table_name, c.constraint_name) FROM agent_constraints c),
    'usage_quality_all_time', (SELECT to_jsonb(u) FROM usage_quality u),
    'usage_links_all_time', (SELECT to_jsonb(l) FROM usage_links l),
    'session_quality_all_time', (SELECT to_jsonb(s) FROM session_quality s),
    'violation_quality_all_time', (SELECT to_jsonb(v) FROM violation_quality v),
    'duplicate_events_all_time', jsonb_build_object(
        'usage_duplicate_groups', (SELECT count(*) FROM duplicate_usage_events),
        'usage_extra_rows', (SELECT coalesce(sum(occurrences - 1), 0) FROM duplicate_usage_events),
        'violation_duplicate_groups', (SELECT count(*) FROM duplicate_violation_events),
        'violation_extra_rows', (SELECT coalesce(sum(occurrences - 1), 0) FROM duplicate_violation_events)
    ),
    'overlap_check_recent_90d', jsonb_build_object(
        'segments_overlapping_prior_segment_gt_2s', (
            SELECT count(*) FROM overlap_candidates
            WHERE usage_start_time < previous_max_end - interval '2 seconds'
        )
    ),
    'daily_counts_recent_90d', (SELECT jsonb_agg(to_jsonb(d) ORDER BY d.report_date DESC) FROM daily_report d)
) AS agent_storage_report
FROM bounds b;

ROLLBACK;
