# RBAC-Dependency
from fastapi import HTTPException, Header
from shared.jwt_utils import verify_token   # gleiche Datei wie in auth_service

def get_current_user(authorization: str = Header(...)) -> dict:
    """JWT selbst verifizieren — kein Netzwerkaufruf an auth_service!"""
    token = authorization.replace("Bearer ", "")
    return verify_token(token)

def require_admin(authorization: str = Header(...)) -> dict:
    user = get_current_user(authorization)
    if user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return user