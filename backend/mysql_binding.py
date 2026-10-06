from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db
from backend.models import CompanyDatabase, get_company_database, get_or_create_settings
from backend.mysql import MysqlError, list_databases, valid_database_name, verify_superuser
from tallysync.tallylib import TallyError, loaded_company_info

router = APIRouter(prefix="/api/mysql", tags=["mysql"])


class BindingBody(BaseModel):
    database: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=255)


def _current_company(db: Session) -> str:
    row = get_or_create_settings(db)
    url = f"http://{row.tally_host}:{row.tally_port}"
    try:
        info = loaded_company_info(url, timeout=15)
    except TallyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    names = info["companies"]
    if len(names) > 1:
        raise HTTPException(status_code=400, detail="Keep only one company open in Tally")
    return info["company"]


@router.get("/databases")
def mysql_databases(_user: str = Depends(current_user)):
    try:
        return {"databases": list_databases()}
    except MysqlError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.get("/binding")
def read_binding(_user: str = Depends(current_user), db: Session = Depends(get_db)):
    try:
        company = _current_company(db)
    except HTTPException as exc:
        if exc.status_code == 502:
            return {"company": "", "database": ""}
        raise
    row = get_company_database(db, company)
    return {"company": company, "database": row.mysql_database if row else ""}


@router.put("/binding")
def write_binding(
    body: BindingBody,
    _user: str = Depends(current_user),
    db: Session = Depends(get_db),
):
    try:
        verify_superuser(body.password)
    except MysqlError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    name = body.database.strip()
    if not valid_database_name(name):
        raise HTTPException(status_code=400, detail="Invalid database name")
    try:
        databases = list_databases()
    except MysqlError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    if name not in databases:
        raise HTTPException(status_code=400, detail="Database is not on the MySQL server")
    company = _current_company(db)
    row = get_company_database(db, company)
    if row is None:
        row = CompanyDatabase(company=company, mysql_database=name)
        db.add(row)
    else:
        row.mysql_database = name
    db.commit()
    db.refresh(row)
    return {"company": row.company, "database": row.mysql_database}
