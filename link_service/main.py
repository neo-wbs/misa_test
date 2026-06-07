from typing import Optional

import httpx
import json
import os
import time
from fastapi import Depends
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from link_service.auth import get_current_user, require_admin
from link_service.database import get_db, Event, LinkView

LINKS_COUNTER = Counter(
    "links_saved_total",
    "Anzahl gespeicherter Links"
)
LINK_DURATION = Histogram(
    "link_save_duration_seconds",
    "Dauer des Link-Speicherns",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0]
)

# root_path="/links" — Traefik leitet /links/* weiter, App sieht /*
# Swagger läuft unter http://localhost/links/docs
# Routen ohne /links-Prefix — sonst doppelter Prefix: /links/links
app = FastAPI(title="link-service", root_path="/links")
Instrumentator().instrument(app).expose(app)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")

# --- Auth-Helper ---
def _require_auth(authorization: str) -> dict:
    token = authorization.replace("Bearer ", "")
    try:
        resp = httpx.get(f"{AUTH_SERVICE_URL}/validate",
                         params={"token": token}, timeout=3.0)
    except httpx.ConnectError:
        raise HTTPException(503, "auth_service unavailable")
    if resp.status_code != 200:
        raise HTTPException(401, "Invalid token")
    return resp.json()

# --- Event-Store-Helper (append-only!) ---
def _append_event(db: Session, aggregate_id: str,
                  event_type: str, payload: dict, version: int):
    event = Event(aggregate_id=aggregate_id, event_type=event_type,
                  payload=json.dumps(payload), version=version)
    db.add(event)

# --- PROJEKTION: Read-Model nach Event aktualisieren ---
def _project(db: Session, event_type: str, payload: dict):
    if event_type == "LinkGespeichert":
        view = LinkView(id=payload["id"], url=payload["url"],
                        title=payload["title"], user_id=payload["user_id"],
                        tags=json.dumps(payload.get("tags", [])))
        db.add(view)
    elif event_type == "LinkAktualisiert":
        view = db.get(LinkView, payload["id"])
        if view:
            if "title" in payload:
                view.title = payload["title"]
            if "tags" in payload:
                view.tags = json.dumps(payload["tags"])
    elif event_type == "LinkGelöscht":
        view = db.get(LinkView, payload["id"])
        if view:
            db.delete(view)

# --- Schemas ---
class SaveLinkRequest(BaseModel):
    url: str
    title: str
    tags: list[str] = []

class PatchLinkRequest(BaseModel):
    title: Optional[str] = None
    tags: Optional[list[str]] = None

# --- Endpoints ---
# WICHTIG: statische Routen immer VOR Wildcard-Routen (/{link_id})!
# FastAPI matcht in Definitionsreihenfolge — /health nach /{link_id}
# würde "health" als link_id interpretieren.

@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "error"
    status = "ok" if db_status == "ok" else "degraded"
    code   = 200  if db_status == "ok" else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=code,
        content={"status": status, "db": db_status, "service": app.title}
    )

# Admin-Endpoint — alle Links aller User (vor /{link_id}!)
@app.get("/admin/links")
def all_links(auth: dict = Depends(require_admin),
              db: Session = Depends(get_db)):
    views = db.query(LinkView).all()
    return [{"id": v.id, "url": v.url, "title": v.title,
             "user_id": v.user_id} for v in views]

# POST /  — Command: schreibt in Event Store + aktualisiert Read-Model
@app.post("/", status_code=201)
def save_link(body: SaveLinkRequest,
              auth: dict = Depends(get_current_user),
              db: Session = Depends(get_db)):
    start = time.time()
    count = db.query(LinkView).count()
    link_id = count + 1
    version = 1
    payload = {"id": link_id, "url": body.url, "title": body.title,
               "user_id": auth["user_id"], "tags": body.tags}
    _append_event(db, f"link_{link_id}", "LinkGespeichert", payload, version)
    _project(db, "LinkGespeichert", payload)
    db.commit()
    LINKS_COUNTER.inc()
    LINK_DURATION.observe(time.time() - start)
    return {"id": link_id, "url": body.url, "title": body.title, "tags": body.tags}

# GET /  — Query: liest nur aus Read-Model (kein Event Store!)
@app.get("/")
def list_links(auth: dict = Depends(get_current_user),
               db: Session = Depends(get_db)):
    views = db.query(LinkView).filter(LinkView.user_id == auth["user_id"]).all()
    return [{"id": v.id, "url": v.url, "title": v.title,
             "tags": json.loads(v.tags)} for v in views]

# GET /{id}/history — vor /{link_id}! sonst matcht history als link_id
@app.get("/{link_id}/history")
def link_history(link_id: int,
                 auth: dict = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    events = (db.query(Event)
                .filter(Event.aggregate_id == f"link_{link_id}")
                .order_by(Event.version).all())
    return [{"version": e.version, "type": e.event_type,
             "payload": json.loads(e.payload),
             "timestamp": e.timestamp} for e in events]

# GET /{id}  — Query: Read-Model
@app.get("/{link_id}")
def get_link(link_id: int,
             auth: dict = Depends(get_current_user),
             db: Session = Depends(get_db)):
    view = db.get(LinkView, link_id)
    if not view:
        raise HTTPException(404, "Link not found")
    if view.user_id != auth["user_id"]:
        raise HTTPException(403, "Not your link")
    return {"id": view.id, "url": view.url, "title": view.title,
            "tags": json.loads(view.tags)}

# PATCH /{id}  — Command: Event Store + Projektion
@app.patch("/{link_id}")
def patch_link(link_id: int, body: PatchLinkRequest,
               auth: dict = Depends(get_current_user),
               db: Session = Depends(get_db)):
    view = db.get(LinkView, link_id)
    if not view:
        raise HTTPException(404, "Link not found")
    if view.user_id != auth["user_id"]:
        raise HTTPException(403, "Not your link")
    last = (db.query(Event)
              .filter(Event.aggregate_id == f"link_{link_id}")
              .order_by(Event.version.desc()).first())
    version = (last.version + 1) if last else 1
    payload = {"id": link_id}
    if body.title is not None:
        payload["title"] = body.title
    if body.tags is not None:
        payload["tags"] = body.tags
    _append_event(db, f"link_{link_id}", "LinkAktualisiert", payload, version)
    _project(db, "LinkAktualisiert", payload)
    db.commit()
    db.refresh(view)
    return {"id": view.id, "url": view.url, "title": view.title,
            "tags": json.loads(view.tags)}

# DELETE /{id}  — Command: Event Store + Projektion
@app.delete("/{link_id}", status_code=204)
def delete_link(link_id: int,
                auth: dict = Depends(get_current_user),
                db: Session = Depends(get_db)):
    view = db.get(LinkView, link_id)
    if not view:
        raise HTTPException(404, "Link not found")
    if view.user_id != auth["user_id"]:
        raise HTTPException(403, "Not your link")
    last = (db.query(Event)
              .filter(Event.aggregate_id == f"link_{link_id}")
              .order_by(Event.version.desc()).first())
    version = (last.version + 1) if last else 1
    _append_event(db, f"link_{link_id}", "LinkGelöscht", {"id": link_id}, version)
    _project(db, "LinkGelöscht", {"id": link_id})
    db.commit()