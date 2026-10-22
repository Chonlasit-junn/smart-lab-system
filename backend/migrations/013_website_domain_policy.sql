-- Review and run with operator approval before enabling website rules.
-- No data is deleted; older Agent versions ignore the new rule type.
BEGIN;
ALTER TABLE public.blacklisted_apps
    DROP CONSTRAINT IF EXISTS blacklisted_apps_match_type_check;
ALTER TABLE public.blacklisted_apps
    ADD CONSTRAINT blacklisted_apps_match_type_check CHECK (match_type IN (
        'process_name', 'process_name_or_title', 'exe_path', 'window_title', 'website_domain'
    )) NOT VALID;
COMMIT;
