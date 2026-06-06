from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Session

engine = create_engine("sqlite:///./links.db", connect_args={"check_same_thread": False})

class Base(DeclarativeBase):
    pass

# --- WRITE-MODELL: Event Store (append-only!) ---
class Event(Base):
    __tablename__ = "events"
    id           = Column(Integer, primary_key=True)
    aggregate_id = Column(String, index=True)   # z.B. "link_1"
    event_type   = Column(String)               # "LinkGespeichert"
    payload      = Column(Text)                 # JSON-String
    version      = Column(Integer)
    timestamp    = Column(DateTime, default=datetime.utcnow)

# --- READ-MODELL: Projektion (denormalisiert, für schnelle Abfragen) ---
class LinkView(Base):
    __tablename__ = "links_view"
    id      = Column(Integer, primary_key=True)
    url     = Column(String)
    title   = Column(String)
    tags    = Column(String)   # JSON-Array als String
    user_id = Column(Integer, index=True)

Base.metadata.create_all(bind=engine)

def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()