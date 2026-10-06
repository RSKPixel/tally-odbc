from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mysql_host: str = "homeserver"
    mysql_user: str = "sysadmin"
    mysql_password: str = ""
    mysql_database: str = "tallysync"
    mysql_port: int = 3306
    sqlite_path: str = "app.sqlite"
    superuser_password: str = ""

    admin_user: str = "admin"
    admin_password: str = "admin"
    session_secret: str = "change-me"

    tally_host: str = "officehq"
    tally_port: int = 9000


settings = Settings()
