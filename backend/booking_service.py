import os
from datetime import datetime, time, timedelta, timezone

import psycopg
from fastapi import HTTPException
from psycopg.errors import ExclusionViolation
from psycopg.rows import dict_row

BANGKOK_TIME = timezone(timedelta(hours=7))
OPENING_TIME = time(9, 0)
CLOSING_TIME = time(18, 0)


def validate_booking_time(start_at: datetime, end_at: datetime) -> None:
    if start_at >= end_at:
        raise HTTPException(status_code=422, detail="End time must be after start time")

    if start_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="Start time must be in the future")

    local_start = start_at.astimezone(BANGKOK_TIME)
    local_end = end_at.astimezone(BANGKOK_TIME)

    if (
        local_start.date() != local_end.date()
        or local_start.weekday() >= 5
        or local_start.time() < OPENING_TIME
        or local_end.time() > CLOSING_TIME
    ):
        raise HTTPException(
            status_code=422,
            detail="Book within one weekday, 09:00–18:00 Bangkok time",
        )


def insert_booking(conn, user_id, resource_id, start_at, end_at) -> dict:
    validate_booking_time(start_at, end_at)

    resource = conn.execute(
        """
        SELECT id
        FROM resources
        WHERE id = %s AND is_active = TRUE
        FOR SHARE
        """,
        (resource_id,),
    ).fetchone()

    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    try:
        return conn.execute(
            """
            INSERT INTO bookings (user_id, resource_id, start_at, end_at, status)
            VALUES (%s, %s, %s, %s, 'confirmed')
            RETURNING id, user_id, resource_id, start_at, end_at, status
            """,
            (user_id, resource_id, start_at, end_at),
        ).fetchone()
    except ExclusionViolation as exc:
        if exc.diag.constraint_name != "booking_no_overlap":
            raise
        raise HTTPException(
            status_code=409,
            detail="This resource is already booked during the requested time",
        ) from exc


def create_booking(
    user_id: int,
    resource_id: int,
    start_at: datetime,
    end_at: datetime,
) -> dict:
    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as conn:
        return insert_booking(conn, user_id, resource_id, start_at, end_at)

def list_bookings(user_id: int) -> list[dict]:
    with psycopg.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
        row_factory=dict_row,
    ) as conn:
        return conn.execute(
            """
            SELECT b.id, b.user_id, b.resource_id, r.name AS resource_name,
                   b.start_at, b.end_at, b.status
            FROM bookings AS b
            JOIN resources AS r ON r.id = b.resource_id
            WHERE b.user_id = %s
            ORDER BY b.start_at, b.id
            """,
            (user_id,),
        ).fetchall()


def cancel_booking_in_transaction(
    conn,
    user_id: int,
    booking_id: int,
    expected_slot: tuple[int, datetime, datetime] | None = None,
) -> dict:
    booking = conn.execute(
        """
        SELECT id, user_id, resource_id, start_at, end_at, status
        FROM bookings
        WHERE id = %s AND user_id = %s
        FOR UPDATE
        """,
        (booking_id, user_id),
    ).fetchone()

    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    current_slot = (
        booking["resource_id"],
        booking["start_at"],
        booking["end_at"],
    )
    if expected_slot is not None and current_slot != expected_slot:
        raise HTTPException(
            status_code=409,
            detail="รายการจองถูกแก้ไขแล้ว กรุณาสร้างคำขอยกเลิกใหม่",
        )

    if booking["status"] == "cancelled":
        return booking

    if (
        booking["status"] not in ("requested", "confirmed")
        or booking["start_at"] <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=409,
            detail="This booking can no longer be cancelled",
        )

    return conn.execute(
        """
        UPDATE bookings
        SET status = 'cancelled'
        WHERE id = %s AND user_id = %s
        RETURNING id, user_id, resource_id, start_at, end_at, status
        """,
        (booking_id, user_id),
    ).fetchone()

def cancel_booking(user_id: int, booking_id: int) -> dict:
    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as conn:
        return cancel_booking_in_transaction(conn, user_id, booking_id)

def update_booking_in_transaction(
    conn,
    user_id: int,
    booking_id: int,
    resource_id: int | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    expected_slot: tuple[int, datetime, datetime] | None = None,
) -> dict:
    booking = conn.execute(
        """
        SELECT resource_id, start_at, end_at, status
        FROM bookings
        WHERE id = %s AND user_id = %s
        FOR UPDATE
        """,
        (booking_id, user_id),
    ).fetchone()

    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")

    if (
        booking["status"] not in ("requested", "confirmed")
        or booking["start_at"] <= datetime.now(timezone.utc)
    ):
        raise HTTPException(
            status_code=409,
            detail="This booking can no longer be edited",
        )

    current_slot = (
        booking["resource_id"],
        booking["start_at"],
        booking["end_at"],
    )
    if expected_slot is not None and current_slot != expected_slot:
        raise HTTPException(
            status_code=409,
            detail="รายการจองถูกแก้ไขแล้ว กรุณาสร้างคำขอใหม่",
        )

    new_resource_id = booking["resource_id"] if resource_id is None else resource_id
    new_start_at = booking["start_at"] if start_at is None else start_at
    new_end_at = booking["end_at"] if end_at is None else end_at

    validate_booking_time(new_start_at, new_end_at)

    resource = conn.execute(
        """
        SELECT id FROM resources
        WHERE id = %s AND is_active = TRUE
        FOR SHARE
        """,
        (new_resource_id,),
    ).fetchone()
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    try:
        return conn.execute(
            """
            UPDATE bookings
            SET resource_id = %s, start_at = %s, end_at = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, user_id, resource_id, start_at, end_at, status
            """,
            (new_resource_id, new_start_at, new_end_at, booking_id, user_id),
        ).fetchone()
    except ExclusionViolation as exc:
        if exc.diag.constraint_name != "booking_no_overlap":
            raise
        raise HTTPException(
            status_code=409,
            detail="This resource is already booked during the requested time",
        ) from exc


def update_booking(
    user_id: int,
    booking_id: int,
    resource_id: int | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> dict:
    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as conn:
        return update_booking_in_transaction(
            conn, user_id, booking_id, resource_id, start_at, end_at
        )

def check_availability(
    resource_id: int,
    start_at: datetime,
    end_at: datetime,
) -> bool:
    validate_booking_time(start_at, end_at)

    with psycopg.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
        row_factory=dict_row,
    ) as conn:
        result = conn.execute(
            """
            SELECT NOT EXISTS (
                SELECT 1
                FROM bookings AS b
                WHERE b.resource_id = r.id
                  AND b.status IN ('requested', 'confirmed')
                  AND tstzrange(b.start_at, b.end_at, '[)')
                      && tstzrange(%s, %s, '[)')
            ) AS available
            FROM resources AS r
            WHERE r.id = %s AND r.is_active = TRUE
            """,
            (start_at, end_at, resource_id),
        ).fetchone()

    if result is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    return result["available"]