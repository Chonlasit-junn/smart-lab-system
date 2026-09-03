-- Store the device identity on the session instead of relying on duplicated
-- values in program_usage_logs.

ALTER TABLE public.lab_access_logs
    ADD COLUMN IF NOT EXISTS device_mac text;

CREATE INDEX IF NOT EXISTS idx_lab_access_logs_device_mac
    ON public.lab_access_logs (device_mac);

CREATE INDEX IF NOT EXISTS idx_program_usage_logs_session
    ON public.program_usage_logs (lab_access_log_id);

-- Backfill only when every non-empty MAC in a session agrees. Conflicting
-- historical rows are left untouched for manual review.
WITH session_macs AS (
    SELECT
        lab_access_log_id,
        MIN(BTRIM(device_mac)) AS device_mac
    FROM public.program_usage_logs
    WHERE device_mac IS NOT NULL
      AND BTRIM(device_mac) <> ''
      AND LOWER(BTRIM(device_mac)) <> 'null'
    GROUP BY lab_access_log_id
    HAVING COUNT(DISTINCT LOWER(BTRIM(device_mac))) = 1
)
UPDATE public.lab_access_logs AS access_log
SET device_mac = session_macs.device_mac
FROM session_macs
WHERE access_log.id = session_macs.lab_access_log_id
  AND access_log.device_mac IS NULL;
