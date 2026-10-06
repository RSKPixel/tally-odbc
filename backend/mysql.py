from __future__ import annotations

import hmac
import re

import pymysql
from pymysql.cursors import DictCursor

from backend.config import settings

_SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}
_DB_NAME = re.compile(r"^[A-Za-z0-9_]+$")


class MysqlError(RuntimeError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def mysql_connect(database: str | None = None):
    try:
        return pymysql.connect(
            host=settings.mysql_host,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=database or None,
            port=settings.mysql_port,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )
    except pymysql.Error as exc:
        raise MysqlError(f"MySQL not reachable: {exc}") from exc


def valid_database_name(name: str) -> bool:
    return bool(_DB_NAME.fullmatch(name or ""))


def list_databases() -> list[str]:
    conn = mysql_connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW DATABASES")
            names = [list(row.values())[0] for row in cur.fetchall()]
    finally:
        conn.close()
    return [name for name in names if name not in _SYSTEM_DATABASES]


def verify_superuser(password: str) -> None:
    expected = (settings.superuser_password or settings.mysql_password).strip()
    given = (password or "").strip()
    if not expected:
        raise MysqlError("Super user password is not set", status=500)
    try:
        matched = hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8"))
    except (TypeError, ValueError):
        matched = False
    if not given or not matched:
        raise MysqlError("Invalid super user password", status=403)
