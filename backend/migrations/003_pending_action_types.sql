ALTER TABLE pending_actions
    ADD COLUMN action_type TEXT NOT NULL DEFAULT 'create',
    ADD COLUMN target_booking_id BIGINT REFERENCES bookings (id),
    ADD CONSTRAINT pending_actions_valid_target CHECK (
        (action_type = 'create' AND target_booking_id IS NULL)
        OR
        (action_type = 'cancel' AND target_booking_id IS NOT NULL)
    ),
    DROP CONSTRAINT pending_actions_confirmed_booking_id_key;

CREATE UNIQUE INDEX pending_actions_created_booking_unique
    ON pending_actions (confirmed_booking_id)
    WHERE action_type = 'create';