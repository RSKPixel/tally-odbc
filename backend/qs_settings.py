from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.config import settings
from backend.db import get_db
from backend.models import (
    CompanyDatabase,
    get_company_database,
    get_or_create_qs_settings,
    get_or_create_settings,
)
from backend.mysql import MysqlError, list_databases, valid_database_name, verify_superuser

router = APIRouter(prefix="/api/qs", tags=["qs"])


class QsSettingsBody(BaseModel):
    company: str = Field(min_length=1, max_length=255)
    database: str = Field(min_length=1, max_length=64)
    days: int = Field(ge=1, le=366)
    auto_minutes: int = Field(ge=0, le=24 * 60)
    password: str = Field(min_length=1, max_length=255)


@router.get("/settings")
def read_qs_settings(_user: str = Depends(current_user), db: Session = Depends(get_db)):
    row = get_or_create_qs_settings(db)
    tally = get_or_create_settings(db)
    return {
        "company": row.company,
        "database": row.mysql_database,
        "days": max(1, int(row.days or 1)),
        "auto_minutes": max(0, int(getattr(row, "auto_minutes", 0) or 0)),
        "tally_host": tally.tally_host,
        "tally_port": tally.tally_port,
        "mysql_host": settings.mysql_host,
    }


@router.put("/settings")
def write_qs_settings(
    body: QsSettingsBody,
    _user: str = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        verify_superuser(body.password)
    except MysqlError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    company = body.company.strip()
    database = body.database.strip()
    if not company:
        raise HTTPException(status_code=400, detail="Company name is required")
    if not valid_database_name(database):
        raise HTTPException(status_code=400, detail="Invalid database name")
    try:
        databases = list_databases()
    except MysqlError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    if database not in databases:
        raise HTTPException(status_code=400, detail="Database is not on the MySQL server")

    row = get_or_create_qs_settings(db)
    row.company = company
    row.mysql_database = database
    row.days = body.days
    row.auto_minutes = body.auto_minutes

    binding = get_company_database(db, company)
    if binding is None:
        db.add(CompanyDatabase(company=company, mysql_database=database))
    else:
        binding.mysql_database = database
    db.commit()
    db.refresh(row)
    return {
        "company": row.company,
        "database": row.mysql_database,
        "days": row.days,
        "auto_minutes": row.auto_minutes,
    }
