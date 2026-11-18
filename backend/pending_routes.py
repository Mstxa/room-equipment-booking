import os
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from auth import get_current_user
from booking_routes import BookingCreate
from booking_service import (
    cancel_booking_in_transaction,
    check_availability,
    insert_booking,
    update_booking_in_transaction,
    validate_booking_time,
)

router = APIRouter(prefix="/ai", tags=["ai"])


class CancelBookingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booking_id: int = Field(gt=0, le=9_223_372_036_854_775_807)


@router.post("/prepare-booking")
def prepare_booking(
    body: BookingCreate,
    user: Annotated[dict, Depends(get_current_user)],
):
    if not check_availability(body.resource_id, body.start_at, body.end_at):
        raise HTTPException(status_code=409, detail="ช่วงเวลานี้ถูกจองแล้ว")

    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as conn:
        action = conn.execute(
            """
            INSERT INTO pending_actions (id, user_id, resource_id, start_at, end_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, resource_id, start_at, end_at, expires_at
            """,
            (uuid4(), user["id"], body.resource_id, body.start_at, body.end_at),
        ).fetchone()

    return {
        "kind": "pending_confirmation",
        "action_id": action["id"],
        "resource_id": action["resource_id"],
        "start_at": action["start_at"],
        "end_at": action["end_at"],
        "expires_at": action["expires_at"],
    }


@router.post("/prepare-cancellation")
def prepare_cancellation(
    body: CancelBookingRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as conn:
        booking = conn.execute(
            """
            SELECT b.resource_id, b.start_at, b.end_at, b.status,
                   r.name AS resource_name
            FROM bookings AS b
            JOIN resources AS r ON r.id = b.resource_id
            WHERE b.id = %s AND b.user_id = %s
            """,
            (body.booking_id, user["id"]),
        ).fetchone()

        if booking is None:
            raise HTTPException(status_code=404, detail="Booking not found")

        if (
            booking["status"] not in ("requested", "confirmed")
            or booking["start_at"] <= datetime.now(timezone.utc)
        ):
            raise HTTPException(status_code=409, detail="รายการนี้ยกเลิกไม่ได้แล้ว")

        action = conn.execute(
            """
            INSERT INTO pending_actions (
                id, user_id, resource_id, start_at, end_at,
                action_type, target_booking_id
            )
            VALUES (%s, %s, %s, %s, %s, 'cancel', %s)
            RETURNING id, expires_at
            """,
            (
                uuid4(),
                user["id"],
                booking["resource_id"],
                booking["start_at"],
                booking["end_at"],
                body.booking_id,
            ),
        ).fetchone()

    return {
        "kind": "pending_confirmation",
        "action_type": "cancel",
        "action_id": action["id"],
        "booking_id": body.booking_id,
        "resource_name": booking["resource_name"],
        "start_at": booking["start_at"],
        "end_at": booking["end_at"],
        "expires_at": action["expires_at"],
    }

class EditBookingRequest(BookingCreate):
    booking_id: int = Field(strict=True, gt=0, le=9_223_372_036_854_775_807)


@router.post("/prepare-edit")
def prepare_edit(
    body: EditBookingRequest,
    user: Annotated[dict, Depends(get_current_user)],
):
    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as conn:
        original = conn.execute(
            """
            SELECT b.resource_id, b.start_at, b.end_at, b.status,
                   r.name AS resource_name
            FROM bookings AS b
            JOIN resources AS r ON r.id = b.resource_id
            WHERE b.id = %s AND b.user_id = %s
            """,
            (body.booking_id, user["id"]),
        ).fetchone()

        if original is None:
            raise HTTPException(status_code=404, detail="Booking not found")

        if (
            original["status"] not in ("requested", "confirmed")
            or original["start_at"] <= datetime.now(timezone.utc)
        ):
            raise HTTPException(status_code=409, detail="รายการนี้แก้ไขไม่ได้แล้ว")

        validate_booking_time(body.start_at, body.end_at)

        resource = conn.execute(
            "SELECT name FROM resources WHERE id = %s AND is_active = TRUE",
            (body.resource_id,),
        ).fetchone()
        if resource is None:
            raise HTTPException(status_code=404, detail="Resource not found")

        action = conn.execute(
            """
            INSERT INTO pending_actions (
                id, user_id, resource_id, start_at, end_at,
                action_type, target_booking_id,
                original_resource_id, original_start_at, original_end_at
            )
            VALUES (%s, %s, %s, %s, %s, 'edit', %s, %s, %s, %s)
            RETURNING id, expires_at
            """,
            (
                uuid4(),
                user["id"],
                body.resource_id,
                body.start_at,
                body.end_at,
                body.booking_id,
                original["resource_id"],
                original["start_at"],
                original["end_at"],
            ),
        ).fetchone()

    return {
        "kind": "pending_confirmation",
        "action_type": "edit",
        "action_id": action["id"],
        "booking_id": body.booking_id,
        "resource_name": resource["name"],
        "start_at": body.start_at,
        "end_at": body.end_at,
        "original_resource_name": original["resource_name"],
        "original_start_at": original["start_at"],
        "original_end_at": original["end_at"],
        "expires_at": action["expires_at"],
    }

@router.post("/confirm/{action_id}")
def confirm_booking(
    action_id: UUID,
    user: Annotated[dict, Depends(get_current_user)],
):
    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as conn:
        action = conn.execute(
            """
            SELECT resource_id, start_at, end_at, expires_at,
                   confirmed_booking_id, action_type, target_booking_id,
                   original_resource_id, original_start_at, original_end_at
            FROM pending_actions
            WHERE id = %s AND user_id = %s
            FOR UPDATE
            """,
            (action_id, user["id"]),
        ).fetchone()

        if action is None:
            raise HTTPException(status_code=404, detail="ไม่พบคำขอจอง")

        action_type = action["action_type"]
        booking_id = action["confirmed_booking_id"]

        if booking_id is None:
            if action["expires_at"] <= datetime.now(timezone.utc):
                raise HTTPException(status_code=409, detail="คำขอหมดอายุแล้ว")

            if action_type == "cancel":
                booking = cancel_booking_in_transaction(
                    conn,
                    user["id"],
                    action["target_booking_id"],
                    expected_slot=(
                        action["resource_id"],
                        action["start_at"],
                        action["end_at"],
                    ),
                )
            elif action_type == "edit":
                booking = update_booking_in_transaction(
                    conn,
                    user["id"],
                    action["target_booking_id"],
                    resource_id=action["resource_id"],
                    start_at=action["start_at"],
                    end_at=action["end_at"],
                    expected_slot=(
                        action["original_resource_id"],
                        action["original_start_at"],
                        action["original_end_at"],
                    ),
                )    
            else:
                booking = insert_booking(
                    conn,
                    user["id"],
                    action["resource_id"],
                    action["start_at"],
                    action["end_at"],
                )

            booking_id = booking["id"]
            conn.execute(
                """
                UPDATE pending_actions
                SET confirmed_booking_id = %s
                WHERE id = %s
                """,
                (booking_id, action_id),
            )

    return {
        "kind": "confirmed",
        "action_type": action_type,
        "booking_id": booking_id,
    }