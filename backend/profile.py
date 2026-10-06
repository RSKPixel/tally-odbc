from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db
from backend.models import get_or_create_profile
from backend.security import hash_password

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfileBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=255)
    password: str = Field(default="", max_length=255)


def profile_payload(row) -> dict:
    return {"username": row.username, "name": row.name}


@router.get("")
def read_profile(_user: str = Depends(current_user), db: Session = Depends(get_db)):
    return profile_payload(get_or_create_profile(db))


@router.put("")
def write_profile(
    body: ProfileBody,
    request: Request,
    _user: str = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = get_or_create_profile(db)
    row.username = body.username.strip()
    row.name = body.name.strip()
    if body.password:
        row.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(row)
    request.session["user"] = row.username
    return profile_payload(row)
