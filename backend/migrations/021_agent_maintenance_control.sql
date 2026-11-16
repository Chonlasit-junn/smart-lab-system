-- Add an acknowledged, time-limited maintenance lease for registered Agents.
-- Run after 020_schema_integrity_alignment.sql.
BEGIN;

ALTER TABLE public.lab_devices
    ADD COLUMN IF NOT EXISTS maintenance_until timestamptz,
    ADD COLUMN IF NOT EXISTS control_requested_at timestamptz,
    ADD COLUMN IF NOT EXISTS control_requested_by integer
        REFERENCES public.users(id),
    ADD COLUMN IF NOT EXISTS agent_control_status varchar(32) NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS agent_control_ack_at timestamptz,
    ADD COLUMN IF NOT EXISTS agent_control_version integer NOT NULL DEFAULT 0;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'lab_devices_agent_control_status_check'
          AND conrelid = 'public.lab_devices'::regclass
    ) THEN
        ALTER TABLE public.lab_devices
            ADD CONSTRAINT lab_devices_agent_control_status_check
            CHECK (agent_control_status IN ('active', 'maintenance')) NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'lab_devices_agent_control_version_check'
          AND conrelid = 'public.lab_devices'::regclass
    ) THEN
        ALTER TABLE public.lab_devices
            ADD CONSTRAINT lab_devices_agent_control_version_check
            CHECK (agent_control_version >= 0) NOT VALID;
    END IF;
END
$$;

ALTER TABLE public.lab_devices
    VALIDATE CONSTRAINT lab_devices_agent_control_status_check;
ALTER TABLE public.lab_devices
    VALIDATE CONSTRAINT lab_devices_agent_control_version_check;

CREATE INDEX IF NOT EXISTS idx_lab_devices_maintenance_until
    ON public.lab_devices (maintenance_until)
    WHERE status = 'maintenance';

COMMIT;
