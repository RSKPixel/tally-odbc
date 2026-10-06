from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.config import BACKEND_DIR, settings
from backend.models import Base

engine = None
SessionLocal = None


def sqlite_path() -> Path:
    path = Path(settings.sqlite_path)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path.resolve()


def sqlite_url() -> str:
    return "sqlite:///" + sqlite_path().as_posix()


def init_engine() -> None:
    global engine, SessionLocal
    path = sqlite_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(sqlite_url(), connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    print(f"SQLite: {path}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
