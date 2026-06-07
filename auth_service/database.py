from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import DeclarativeBase, Session

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "auth.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False}
)

class Base(DeclarativeBase):
    pass

class UserDB(Base):
    __tablename__ = "users"
    id            = Column(Integer, primary_key=True, index=True)
    email         = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role          = Column(String, default="user")

Base.metadata.create_all(bind=engine)

def get_db():
    db = Session(engine)
    try:
        yield db
    finally:
        db.close()