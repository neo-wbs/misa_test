from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
import os

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
ALGORITHM  = "HS256"

def create_access_token(user_id: int, role: str) -> str:
    payload = {
        "sub":  str(user_id),
        "role": role,
        "type": "access",
        "iat":  datetime.now(timezone.utc),
        "exp":  datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user_id: int) -> str:
    payload = {
        "sub":  str(user_id),
        "type": "refresh",
        "iat":  datetime.now(timezone.utc),
        "exp":  datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str, expected_type: str = "access") -> dict:
    """Verifiziert JWT — kein DB-Lookup nötig!"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(401, "Invalid or expired token")

    if payload.get("type") != expected_type:
        raise HTTPException(401, f"Expected {expected_type} token")

    return {"user_id": int(payload["sub"]), "role": payload.get("role", "user")}