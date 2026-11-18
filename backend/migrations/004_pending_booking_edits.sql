ALTER TABLE pending_actions
    ADD COLUMN original_resource_id BIGINT REFERENCES resources (id),
    ADD COLUMN original_start_at TIMESTAMPTZ,
    ADD COLUMN original_end_at TIMESTAMPTZ,
    DROP CONSTRAINT pending_actions_valid_target,
    ADD CONSTRAINT pending_actions_valid_target CHECK (
        (action_type = 'create' AND target_booking_id IS NULL)
        OR
        (action_type IN ('cancel', 'edit') AND target_booking_id IS NOT NULL)
    ),
    ADD CONSTRAINT pending_actions_valid_original_slot CHECK (
        (
            action_type = 'edit'
            AND original_resource_id IS NOT NULL
            AND original_start_at IS NOT NULL
            AND original_end_at IS NOT NULL
            AND original_start_at < original_end_at
        )
        OR
        (
            action_type IN ('create', 'cancel')
            AND original_resource_id IS NULL
            AND original_start_at IS NULL
            AND original_end_at IS NULL
        )
    );