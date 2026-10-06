from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models import get_or_create_profile
from backend.security import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


def current_user(request: Request) -> str:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return user


@router.post("/login")
def login(body: LoginBody, request: Request, db: Session = Depends(get_db)):
    row = get_or_create_profile(db)
    if body.username != row.username or not verify_password(body.password, row.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    request.session["user"] = row.username
    return {"username": row.username, "name": row.name}


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(_user: str = Depends(current_user), db: Session = Depends(get_db)):
    row = get_or_create_profile(db)
    return {"username": row.username, "name": row.name}
