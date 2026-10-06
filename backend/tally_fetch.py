from __future__ import annotations

import argparse
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db
from backend.mysql import MysqlError
from backend.mysql_sync import replace_period
from backend.models import get_company_database, get_or_create_settings
from tallysync import purchase, sales
from tallysync.tallylib import (
    PURCHASE_LINE_FIELDS,
    PURCHASE_TYPE,
    PURCHASE_TYPES,
    SALES_LINE_FIELDS,
    SALES_TYPE,
    SALES_TYPES,
    TallyError,
    VOUCHER_DISPLAY_FIELDS,
    collect_from_root,
    loaded_company_info,
    parse_root,
    parse_row_date,
    post_voucher_object,
    tally_date,
    tally_status_error,
)

router = APIRouter(prefix="/api/tally", tags=["tally"])

COLLECTIONS = {
    "sales": {
        "label": "Sales (tallysync_sales)",
        "table": "tallysync_sales",
        "fetch": sales.fetch,
        "voucher_type": SALES_TYPE,
        "keep": SALES_TYPES,
        "line_fields": SALES_LINE_FIELDS,
    },
    "purchase": {
        "label": "Purchase (tallysync_purchases)",
        "table": "tallysync_purchases",
        "fetch": purchase.fetch,
        "voucher_type": PURCHASE_TYPE,
        "keep": PURCHASE_TYPES,
        "line_fields": PURCHASE_LINE_FIELDS,
    },
}


class FetchBody(BaseModel):
    collections: list[str] = Field(min_length=1)
    from_date: str = Field(min_length=1)
    to_date: str = Field(min_length=1)


class VoucherBody(BaseModel):
    collection: str = Field(min_length=1)
    master_id: str = Field(min_length=1)


def _parse_date(value: str) -> str:
    try:
        return tally_date(value)
    except argparse.ArgumentTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _loaded_company(url: str) -> dict:
    info = loaded_company_info(url, timeout=15)
    names = info["companies"]
    if len(names) > 1:
        raise HTTPException(status_code=400, detail="Keep only one company open in Tally")
    return info


def _in_tally_period(from_date: str, to_date: str, info: dict) -> None:
    start = parse_row_date(from_date)
    end = parse_row_date(to_date)
    period_start = parse_row_date(info.get("from_date", ""))
    period_end = parse_row_date(info.get("to_date", ""))
    if start and end and start > end:
        raise HTTPException(status_code=400, detail="From date is after To date")
    if period_start and start and start < period_start:
        raise HTTPException(status_code=400, detail="Dates must be within the Tally period")
    if period_end and end and end > period_end:
        raise HTTPException(status_code=400, detail="Dates must be within the Tally period")


DISPLAY_FIELDS = list(VOUCHER_DISPLAY_FIELDS)


def _elapsed_text(seconds: float) -> str:
    if seconds < 0.05:
        return "<0.1s"
    return f"{seconds:.1f}s"


def _row(header: dict, elapsed: str) -> dict:
    return {
        "elapsed": elapsed,
        "voucher_date": "" if header.get("date") is None else str(header.get("date")),
        "voucher_no": "" if header.get("voucher_number") is None else str(header.get("voucher_number")),
        "ledger_name": "" if header.get("party") is None else str(header.get("party")),
        "broker": "" if header.get("rep_or_broker") is None else str(header.get("rep_or_broker")),
        "voucher_type": "" if header.get("voucher_type") is None else str(header.get("voucher_type")),
        "master_id": "" if header.get("master_id") is None else str(header.get("master_id")),
    }


@router.get("/collections")
def list_collections(_user: str = Depends(current_user)):
    return [{"id": key, "label": spec["label"]} for key, spec in COLLECTIONS.items()]


@router.post("/fetch")
def fetch_collections(
    body: FetchBody,
    _user: str = Depends(current_user),
    db: Session = Depends(get_db),
):
    unknown = [name for name in body.collections if name not in COLLECTIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown collection: {unknown[0]}")
    seen: list[str] = []
    for name in body.collections:
        if name not in seen:
            seen.append(name)

    from_date = _parse_date(body.from_date)
    to_date = _parse_date(body.to_date)

    row = get_or_create_settings(db)
    url = f"http://{row.tally_host}:{row.tally_port}"
    try:
        info = _loaded_company(url)
    except TallyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    company = info["company"]
    _in_tally_period(from_date, to_date, info)

    results = []
    for name in seen:
        spec = COLLECTIONS[name]
        started = time.perf_counter()
        try:
            headers, _items, _ledgers = spec["fetch"](
                url, "", from_date, to_date, enrich=False
            )
            elapsed = _elapsed_text(time.perf_counter() - started)
            rows = [_row(header, elapsed) for header in headers]
            results.append(
                {
                    "id": name,
                    "label": spec["label"],
                    "count": len(rows),
                    "elapsed": elapsed,
                    "columns": list(DISPLAY_FIELDS),
                    "rows": rows,
                    "error": "",
                }
            )
        except TallyError as exc:
            elapsed = _elapsed_text(time.perf_counter() - started)
            results.append(
                {
                    "id": name,
                    "label": spec["label"],
                    "count": 0,
                    "elapsed": elapsed,
                    "columns": list(DISPLAY_FIELDS),
                    "rows": [],
                    "error": str(exc),
                }
            )
        except Exception as exc:
            elapsed = _elapsed_text(time.perf_counter() - started)
            results.append(
                {
                    "id": name,
                    "label": spec["label"],
                    "count": 0,
                    "elapsed": elapsed,
                    "columns": list(DISPLAY_FIELDS),
                    "rows": [],
                    "error": str(exc),
                }
            )
    return {"company": company, "from_date": from_date, "to_date": to_date, "results": results}


@router.post("/sync")
def sync_collections(
    body: FetchBody,
    _user: str = Depends(current_user),
    db: Session = Depends(get_db),
):
    unknown = [name for name in body.collections if name not in COLLECTIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown collection: {unknown[0]}")
    seen: list[str] = []
    for name in body.collections:
        if name not in seen:
            seen.append(name)

    from_date = _parse_date(body.from_date)
    to_date = _parse_date(body.to_date)

    row = get_or_create_settings(db)
    url = f"http://{row.tally_host}:{row.tally_port}"
    try:
        info = _loaded_company(url)
    except TallyError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    company = info["company"]
    _in_tally_period(from_date, to_date, info)
    binding = get_company_database(db, company)
    if not binding or not binding.mysql_database:
        raise HTTPException(status_code=400, detail="Select and save a MySQL database")
    database = binding.mysql_database

    results = []
    for name in seen:
        spec = COLLECTIONS[name]
        started = time.perf_counter()
        try:
            _headers, items, _ledgers = spec["fetch"](
                url, "", from_date, to_date, enrich=True
            )
            count = replace_period(database, name, items, from_date, to_date)
            elapsed = _elapsed_text(time.perf_counter() - started)
            results.append(
                {
                    "id": name,
                    "label": spec["label"],
                    "count": count,
                    "elapsed": elapsed,
                    "error": "",
                }
            )
        except (TallyError, MysqlError) as exc:
            elapsed = _elapsed_text(time.perf_counter() - started)
            results.append(
                {
                    "id": name,
                    "label": spec["label"],
                    "count": 0,
                    "elapsed": elapsed,
                    "error": str(exc),
                }
            )
        except Exception as exc:
            elapsed = _elapsed_text(time.perf_counter() - started)
            results.append(
                {
                    "id": name,
                    "label": spec["label"],
                    "count": 0,
                    "elapsed": elapsed,
                    "error": str(exc),
                }
            )
    return {"company": company, "database": database, "from_date": from_date, "to_date": to_date, "results": results}


def _item_row(row: dict, fields: list[str]) -> dict:
    return {key: "" if row.get(key) is None else str(row.get(key)) for key in fields}


@router.post("/voucher")
def fetch_voucher(
    body: VoucherBody,
    _user: str = Depends(current_user),
    db: Session = Depends(get_db),
):
    spec = COLLECTIONS.get(body.collection)
    if spec is None:
        raise HTTPException(status_code=400, detail=f"Unknown collection: {body.collection}")
    row = get_or_create_settings(db)
    url = f"http://{row.tally_host}:{row.tally_port}"
    master_id = body.master_id.strip()
    try:
        _loaded_company(url)
        raw = post_voucher_object(url, "", master_id)
        root = parse_root(raw)
        err = tally_status_error(root)
        if err:
            raise TallyError(err)
        _headers, items, _ledgers = collect_from_root(root, spec["voucher_type"], spec["keep"])
    except TallyError as exc:
        fields = list(spec["line_fields"])
        return {
            "master_id": master_id,
            "columns": fields,
            "items": [],
            "error": str(exc),
        }
    fields = list(spec["line_fields"])
    return {
        "master_id": master_id,
        "columns": fields,
        "items": [_item_row(item, fields) for item in items],
        "error": "",
    }
