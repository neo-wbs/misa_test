from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import DeclarativeBase, Session

engine = create_engine("sqlite:///./auth.db", connect_args={"check_same_thread": False})

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