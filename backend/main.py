import os

import psycopg
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from auth import get_current_user
from booking_service import check_availability
from llm_client import interpret_availability
from psycopg.rows import dict_row

from auth import router as auth_router
from booking_routes import router as booking_router
from pending_routes import router as pending_router
from booking_routes import BookingCreate
from pending_routes import (
    CancelBookingRequest,
    EditBookingRequest,
    prepare_booking,
    prepare_cancellation,
    prepare_edit,
)

app = FastAPI()
app.include_router(auth_router)
app.include_router(booking_router)
app.include_router(pending_router)

@app.get("/health")
def health():
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    return {"status": "ok", "database": "connected"}

@app.get("/resources")
def list_resources():
    with psycopg.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
        row_factory=dict_row,
    ) as conn:
        return conn.execute(
            """
            SELECT id, name, type
            FROM resources
            WHERE is_active = TRUE
            ORDER BY id
            """
        ).fetchall()

@app.get("/availability", tags=["bookings"])
def get_availability(
    resource_id: Annotated[int, Query(gt=0, le=9_223_372_036_854_775_807)],
    start_at: Annotated[AwareDatetime, Query()],
    end_at: Annotated[AwareDatetime, Query()],
    user: Annotated[dict, Depends(get_current_user)],
):
    return {"available": check_availability(resource_id, start_at, end_at)}

class AIMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1000)


class AvailabilityArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: int = Field(strict=True, gt=0, le=9_223_372_036_854_775_807)
    start_at: AwareDatetime
    end_at: AwareDatetime

@app.post("/ai/message", tags=["ai"])
def ai_message(
    body: AIMessage,
    user: Annotated[dict, Depends(get_current_user)],
):
    resources = list_resources()
    tool_call = interpret_availability(body.message, resources)

    if tool_call is None:
        return {
            "kind": "clarification",
            "message": "ระบุชื่อห้องหรืออุปกรณ์ วันที่ เวลาเริ่ม และเวลาสิ้นสุดเพื่อเช็กเวลาว่าง",
        }

    tool_name, arguments_json = tool_call

    if tool_name == "prepare_edit":
        try:
            edit_request = EditBookingRequest.model_validate_json(arguments_json)
        except ValidationError as exc:
            raise HTTPException(
                status_code=502,
                detail="ระบุเลขรายการ ห้อง หรือเวลาใหม่ไม่ถูกต้อง",
            ) from exc

        return prepare_edit(body=edit_request, user=user)

    if tool_name == "prepare_cancellation":
        try:
            cancellation = CancelBookingRequest.model_validate_json(arguments_json)
        except ValidationError as exc:
            raise HTTPException(
                status_code=502,
                detail="ระบุเลขรายการจองไม่ถูกต้อง",
            ) from exc

        return prepare_cancellation(body=cancellation, user=user)

    try:
        arguments = AvailabilityArguments.model_validate_json(arguments_json)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail="AI ระบุห้องหรือเวลาไม่ถูกต้อง กรุณาระบุรายละเอียดอีกครั้ง",
        ) from exc

    resource = next(
        (row for row in resources if row["id"] == arguments.resource_id),
        None,
    )
    if resource is None:
        raise HTTPException(status_code=404, detail="Resource not found")

    if tool_name == "prepare_booking":
        draft = prepare_booking(
            body=BookingCreate(
                resource_id=arguments.resource_id,
                start_at=arguments.start_at,
                end_at=arguments.end_at,
            ),
            user=user,
        )
        return {**draft, "resource_name": resource["name"]}

    available = check_availability(
        arguments.resource_id,
        arguments.start_at,
        arguments.end_at,
    )
    return {
        "kind": "availability",
        "resource_name": resource["name"],
        "start_at": arguments.start_at,
        "end_at": arguments.end_at,
        "available": available,
    }