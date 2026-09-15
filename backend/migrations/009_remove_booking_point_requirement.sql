-- Remove the booking-score requirement while retaining the legacy policy
-- column for compatibility with older clients and existing databases.
-- Booking permission is now based on an active Ban only.

ALTER TABLE public.point_policies
    DROP CONSTRAINT IF EXISTS point_policies_threshold_order_check;

ALTER TABLE public.point_policies
    ADD CONSTRAINT point_policies_threshold_order_check
    CHECK (
        ban_level_1_below < ban_level_2_below
        AND ban_level_2_below < ban_level_3_below
        AND ban_level_3_below < ban_level_4_below
    )
    NOT VALID;

COMMENT ON COLUMN public.point_policies.booking_min_points IS
    'Deprecated compatibility field. Booking permission depends on active Ban only.';
