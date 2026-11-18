CREATE TABLE pending_actions (
    id UUID PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id),
    resource_id BIGINT NOT NULL REFERENCES resources (id),
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '10 minutes'),
    confirmed_booking_id BIGINT UNIQUE REFERENCES bookings (id),

    CHECK (start_at < end_at)
);