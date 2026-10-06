from sqlalchemy import Integer, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

from backend.config import settings
from backend.security import hash_password


class Base(DeclarativeBase):
    pass


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tally_host: Mapped[str] = mapped_column(String(255), default=settings.tally_host)
    tally_port: Mapped[int] = mapped_column(Integer, default=settings.tally_port)


class AppProfile(Base):
    __tablename__ = "app_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))


class CompanyDatabase(Base):
    __tablename__ = "company_database"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company: Mapped[str] = mapped_column(String(255), unique=True)
    mysql_database: Mapped[str] = mapped_column(String(64), default="")


def get_or_create_settings(db: Session) -> AppSettings:
    row = db.scalar(select(AppSettings).where(AppSettings.id == 1))
    if row is not None:
        return row
    row = AppSettings(id=1, tally_host=settings.tally_host, tally_port=settings.tally_port)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.scalar(select(AppSettings).where(AppSettings.id == 1))
        if row is None:
            raise
        return row
    db.refresh(row)
    return row


def get_or_create_profile(db: Session) -> AppProfile:
    row = db.scalar(select(AppProfile).where(AppProfile.id == 1))
    if row is not None:
        return row
    row = AppProfile(
        id=1,
        username=settings.admin_user,
        name="",
        password_hash=hash_password(settings.admin_password),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.scalar(select(AppProfile).where(AppProfile.id == 1))
        if row is None:
            raise
        return row
    db.refresh(row)
    return row


def get_company_database(db: Session, company: str) -> CompanyDatabase | None:
    name = (company or "").strip()
    if not name:
        return None
    return db.scalar(select(CompanyDatabase).where(CompanyDatabase.company == name))
