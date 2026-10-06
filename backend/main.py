from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from backend.auth import router as auth_router
from backend.config import settings
from backend.db import init_engine
from backend.profile import router as profile_router
from backend.settings import router as settings_router
from backend.mysql_binding import router as mysql_router
from backend.tally_fetch import router as tally_fetch_router
from backend.tally_status import router as tally_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_engine()
    yield


app = FastAPI(title="Tally sync", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=False,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5175", "http://127.0.0.1:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(profile_router)
app.include_router(tally_router)
app.include_router(tally_fetch_router)
app.include_router(mysql_router)


@app.get("/api/health")
def health():
    return {"ok": True}
