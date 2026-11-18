from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from auth import get_current_user
from booking_service import (
    cancel_booking,
    create_booking,
    list_bookings,
    update_booking,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])


class BookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    start_at: AwareDatetime
    end_at: AwareDatetime


@router.post("", status_code=status.HTTP_201_CREATED)
def add_booking(
    body: BookingCreate,
    user: Annotated[dict, Depends(get_current_user)],
):
    return create_booking(
        user_id=user["id"],
        resource_id=body.resource_id,
        start_at=body.start_at,
        end_at=body.end_at,
    )

@router.get("")
def get_bookings(
    user: Annotated[dict, Depends(get_current_user)],
):
    return list_bookings(user_id=user["id"])

@router.post("/{booking_id}/cancel")
def cancel_my_booking(
    booking_id: Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)],
    user: Annotated[dict, Depends(get_current_user)],
):
    return cancel_booking(user_id=user["id"], booking_id=booking_id)

class BookingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: int | None = Field(
        default=None, gt=0, le=9_223_372_036_854_775_807
    )
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def require_changes(self):
        changes = self.model_dump(exclude_unset=True)
        if not changes or any(value is None for value in changes.values()):
            raise ValueError("Provide at least one field to update, with no null values")
        return self

@router.patch("/{booking_id}")
def edit_my_booking(
    booking_id: Annotated[int, Path(gt=0, le=9_223_372_036_854_775_807)],
    body: BookingUpdate,
    user: Annotated[dict, Depends(get_current_user)],
):
    return update_booking(
        user_id=user["id"],
        booking_id=booking_id,
        resource_id=body.resource_id,
        start_at=body.start_at,
        end_at=body.end_at,
    )