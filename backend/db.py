from __future__ import annotations

from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.config import settings
from backend.models import Base, get_or_create_profile, get_or_create_settings
from backend.mysql import MysqlError, mysql_connect, valid_database_name

engine = None
SessionLocal = None


def app_database() -> str:
    name = (settings.mysql_database or "").strip()
    if not valid_database_name(name):
        raise MysqlError(
            "MYSQL_DATABASE must be a simple name (letters, digits, underscore)",
            status=500,
        )
    return name


def mysql_url() -> str:
    user = quote_plus(settings.mysql_user)
    password = quote_plus(settings.mysql_password)
    host = settings.mysql_host
    port = settings.mysql_port
    database = app_database()
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"


def ensure_app_database() -> None:
    name = app_database()
    conn = mysql_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


def init_engine() -> None:
    global engine, SessionLocal
    ensure_app_database()
    engine = create_engine(
        mysql_url(),
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        get_or_create_settings(db)
        get_or_create_profile(db)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    print(f"App DB (MySQL): {settings.mysql_host}:{settings.mysql_port}/{app_database()}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
