from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth_service.database import get_db, UserDB
from shared.jwt_utils import create_access_token, create_refresh_token, verify_token
from shared.logging_config import setup_logging, logger

setup_logging()

# Eigene Business-Metriken (Klassen aus Prometheus Package)
LOGIN_COUNTER = Counter(
    "auth_logins_total",
    "Anzahl Login-Versuche",
    ["status"]   # Label: success / failure
)

app = FastAPI(title="auth-service", root_path="/auth")
# /metrics Endpoint automatisch einrichten
Instrumentator().instrument(app).expose(app)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

class RegisterRequest(BaseModel):
    email: str
    password: str

# POST /users — Registrierung mit bcrypt-Passwort-Hash
@app.post("/users", status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(UserDB).filter(UserDB.email == body.email).first():
        raise HTTPException(409, "Email already registered")
    user = UserDB(email=body.email,
                  password_hash=pwd.hash(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "role": user.role}

# POST /token — Login → echte JWTs
@app.post("/token")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == form.username).first()
    if not user or not pwd.verify(form.password, user.password_hash):
        logger.warning("login_failed", email=form.username)    # ← strukturiert
        LOGIN_COUNTER.labels(status="failure").inc()
        raise HTTPException(401, "Invalid credentials")
    logger.info("login_success", user_id=user.id, role=user.role)
    LOGIN_COUNTER.labels(status="success").inc()
    return {
        "access_token":  create_access_token(user.id, user.role),
        "refresh_token": create_refresh_token(user.id),
        "token_type":    "bearer",
    }

# POST /refresh — Refresh Token → neuer Access Token
@app.post("/refresh")
def refresh(refresh_token: str, db: Session = Depends(get_db)):
    data = verify_token(refresh_token, expected_type="refresh")
    user = db.get(UserDB, data["user_id"])
    if not user:
        raise HTTPException(401, "User not found")
    return {"access_token": create_access_token(user.id, user.role),
            "token_type": "bearer"}

# GET /validate — für andere Services (optional, JWT reicht allein)
@app.get("/validate")
def validate(token: str):
    return verify_token(token)

# PATCH /users/{id}/role — Admin macht jemanden zum Admin
@app.patch("/users/{user_id}/role")
def set_role(user_id: int, role: str, token: str,
             db: Session = Depends(get_db)):
    caller = verify_token(token)
    if caller["role"] != "admin":
        raise HTTPException(403, "Admin only")
    user = db.get(UserDB, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.role = role
    db.commit()
    return {"id": user.id, "role": user.role}

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))   # DB wirklich prüfen
        db_status = "ok"
    except Exception:
        db_status = "error"

    status = "ok" if db_status == "ok" else "degraded"
    code   = 200  if db_status == "ok" else 503

    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=code,
        content={"status": status, "db": db_status,
                 "service": app.title}
    )