from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db
from backend.models import get_or_create_settings
from tallysync.tallylib import TallyError, loaded_company_info

router = APIRouter(prefix="/api/tally", tags=["tally"])


@router.get("/status")
def tally_status(_user: str = Depends(current_user), db: Session = Depends(get_db)):
    row = get_or_create_settings(db)
    url = f"http://{row.tally_host}:{row.tally_port}"
    try:
        info = loaded_company_info(url, timeout=15)
        return {
            "online": True,
            "company": info["company"],
            "companies": info["companies"],
            "from_date": info["from_date"],
            "to_date": info["to_date"],
            "url": url,
            "error": "",
        }
    except TallyError as exc:
        return {
            "online": False,
            "company": "",
            "companies": [],
            "from_date": "",
            "to_date": "",
            "url": url,
            "error": str(exc),
        }
