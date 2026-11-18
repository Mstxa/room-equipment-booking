CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL
);

CREATE TABLE resources (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL CHECK (type IN ('room', 'equipment')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE bookings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id),
    resource_id BIGINT NOT NULL REFERENCES resources (id),
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed',

    CONSTRAINT booking_start_before_end
        CHECK (start_at < end_at),

    CONSTRAINT booking_valid_status
        CHECK (status IN ('requested', 'confirmed', 'cancelled', 'completed')),

    CONSTRAINT booking_no_overlap
        EXCLUDE USING gist (
            resource_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
        )
        WHERE (status IN ('requested', 'confirmed'))
);