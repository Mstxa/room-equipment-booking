import os
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from pwdlib import PasswordHash
from pydantic import BaseModel, Field
from email_validator import EmailNotValidError, validate_email

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
password_hasher = PasswordHash.recommended()
dummy_hash = password_hasher.hash("unused-demo-password")


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)



class RegisterRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


@router.post("/register", status_code=201)
def register(body: RegisterRequest):
    if body.password != body.confirm_password:
        raise HTTPException(status_code=422, detail="รหัสผ่านทั้งสองช่องไม่ตรงกัน")

    try:
        email = validate_email(
            body.email.strip(), check_deliverability=False
        ).normalized.lower()
    except EmailNotValidError:
        raise HTTPException(status_code=422, detail="กรุณากรอกอีเมลให้ถูกต้อง") from None

    if len(email) > 254:
        raise HTTPException(status_code=422, detail="อีเมลยาวเกินไป")

    password_hash = password_hasher.hash(body.password)
    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as conn:
        user = conn.execute(
            """
            INSERT INTO users (email, password_hash)
            VALUES (%s, %s)
            ON CONFLICT (email) DO NOTHING
            RETURNING id, email
            """,
            (email, password_hash),
        ).fetchone()

    if user is None:
        raise HTTPException(status_code=409, detail="อีเมลนี้มีบัญชีอยู่แล้ว กรุณาเข้าสู่ระบบ")

    return user


def signing_key() -> str:
    key = os.environ.get("AUTH_SECRET", "")
    if len(key) < 32:
        raise HTTPException(status_code=503, detail="Authentication is not configured")
    return key


def unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login")
def login(body: LoginRequest):
    key = signing_key()
    email = body.email.strip().lower()

    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as conn:
        user = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = %s",
            (email,),
        ).fetchone()

    stored_hash = user["password_hash"] if user else dummy_hash
    password_matches = password_hasher.verify(body.password, stored_hash)

    if user is None or not password_matches:
        raise unauthorized("Invalid email or password")

    token = jwt.encode(
        {
            "sub": str(user["id"]),
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        key,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    if credentials is None:
        raise unauthorized("Bearer token required")

    key = signing_key()
    try:
        claims = jwt.decode(
            credentials.credentials,
            key,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized("Invalid or expired token") from None

    with psycopg.connect(
        os.environ["DATABASE_URL"], connect_timeout=5, row_factory=dict_row
    ) as conn:
        user = conn.execute(
            "SELECT id, email FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()

    if user is None:
        raise unauthorized("Invalid or expired token")

    return user


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user