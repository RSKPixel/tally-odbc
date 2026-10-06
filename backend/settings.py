from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db
from backend.models import get_or_create_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsBody(BaseModel):
    tally_host: str = Field(min_length=1, max_length=255)
    tally_port: int = Field(ge=1, le=65535)


@router.get("")
def read_settings(_user: str = Depends(current_user), db: Session = Depends(get_db)):
    row = get_or_create_settings(db)
    return {"tally_host": row.tally_host, "tally_port": row.tally_port}


@router.put("")
def write_settings(
    body: SettingsBody,
    _user: str = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = get_or_create_settings(db)
    row.tally_host = body.tally_host.strip()
    row.tally_port = body.tally_port
    db.commit()
    db.refresh(row)
    return {"tally_host": row.tally_host, "tally_port": row.tally_port}
