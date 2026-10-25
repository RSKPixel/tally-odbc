from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth import current_user
from backend.db import get_db
from backend.mysql import MysqlError
from backend.mysql_sync import (
    replace_accounts,
    replace_cost_centres,
    replace_daybook,
    replace_inventory,
    replace_payables,
    replace_period,
    replace_pnl,
    replace_receivables,
    replace_stock_register,
    replace_stock_summary,
)
from backend.models import get_company_database, get_or_create_settings
from backend.progress import (
    claim_sync,
    create_job,
    iter_events,
    job_meta,
    load_result,
    publish,
    set_status,
    store_result,
)
from tallysync import payables, purchase, receivables, sales
from tallysync.tallylib import (
    PURCHASE_LINE_FIELDS,
    PURCHASE_TYPE,
    PURCHASE_TYPES,
    SALES_LINE_FIELDS,
    SALES_TYPE,
    SALES_TYPES,
    TallyError,
    VOUCHER_DISPLAY_FIELDS,
    attach_alternate_qty,
    bind_progress,
    collect_from_root,
    emit_progress,
    loaded_company_info,
    parse_root,
    parse_row_date,
    post_voucher_object,
    reset_progress,
    tally_date,
    tally_status_error,
    fetch_accounts,
    fetch_cost_centres,
    fetch_daybook,
    fetch_profit_loss_months,
    fetch_stock_items,
    fetch_stock_register,
    fetch_stock_summary,
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
    "pnl": {
        "label": "Profit and Loss (tallysync_pnl)",
        "table": "tallysync_pnl",
    },
    "stocksummary": {
        "label": "Stock Summary (tallysync_stocksummary)",
        "table": "tallysync_stocksummary",
    },
    "stockregister": {
        "label": "Stock Register (tallysync_stockregister)",
        "table": "tallysync_stockregister",
    },
    "inventory": {
        "label": "Inventory (tallysync_inventory)",
        "table": "tallysync_inventory",
    },
    "accounts": {
        "label": "Accounts (tallysync_accounts)",
        "table": "tallysync_accounts",
    },
    "costcentres": {
        "label": "Cost Centres (tallysync_costcentres)",
        "table": "tallysync_costcentres",
    },
    "receivables": {
        "label": "Receivables (tallysync_receivables)",
        "table": "tallysync_receivables",
        "fetch": receivables.fetch,
    },
    "payables": {
        "label": "Payables (tallysync_payables)",
        "table": "tallysync_payables",
        "fetch": payables.fetch,
    },
    "daybook": {
        "label": "Daybook (tallysync_daybook)",
        "table": "tallysync_daybook",
    },
}

PNL_FIELDS = ["period_from", "period_to", "line_no", "account", "amount", "amount_side"]
STOCK_FIELDS = [
    "stock_group",
    "stock_item",
    "alternate_unit",
    "conversion",
    "opening",
    "opening_alt",
    "opening_rate",
    "opening_value",
    "inwards",
    "inwards_alt",
    "inward_rate",
    "inward_value",
    "outwards",
    "outwards_alt",
    "outward_rate",
    "outward_value",
    "closing",
    "closing_alt",
    "closing_rate",
    "closing_value",
]
STOCK_REGISTER_FIELDS = [
    "voucher_date",
    "stock_group",
    "stock_item",
    "particulars",
    "voucher_type",
    "voucher_no",
    "inwards",
    "inward_value",
    "outwards",
    "outward_value",
    "closing",
    "closing_value",
]
INVENTORY_FIELDS = [
    "stock_item",
    "stock_group",
    "category",
    "base_unit",
    "alternate_unit",
    "conversion",
    "denominator",
    "packing",
    "gst_applicable",
    "master_id",
]
ACCOUNT_FIELDS = [
    "ledger_name",
    "account_group",
    "primary_group",
    "mailing_name",
    "address_1",
    "address_2",
    "address_3",
    "address_4",
    "pin_code",
    "gstin",
    "gst_registration_type",
    "state",
    "country",
    "pan",
    "phone",
    "mobile",
    "email",
    "bill_wise",
    "favouring_name",
    "account_number",
    "bank_code",
    "bank_name",
    "representative",
    "master_id",
]
COSTCENTRE_FIELDS = [
    "cost_centre",
    "parent",
    "category",
    "master_id",
]
BILL_DISPLAY_FIELDS = [
    "as_on",
    "invoice_no",
    "invoice_date",
    "due_date",
    "overdue_days",
    "ledger_name",
    "representative",
    "amount",
    "closing",
]
DAYBOOK_FIELDS = [
    "voucher_date",
    "voucher_type",
    "voucher_no",
    "debit_credit",
    "ledger_name",
    "ledger_amount",
    "bill_no",
    "bill_type",
    "costcentre_name",
    "costcentre_amt",
    "narration",
]


def _count_noun(collection_id: str) -> str:
    return {
        "accounts": "accounts",
        "inventory": "items",
        "costcentres": "centres",
        "receivables": "bills",
        "payables": "bills",
        "daybook": "lines",
    }.get(collection_id, "lines")


def _bill_display_row(item: dict) -> dict:
    ledger = "" if item.get("party") is None else str(item.get("party"))
    return {
        "as_on": "" if item.get("as_on") is None else str(item.get("as_on")),
        "invoice_no": "" if item.get("bill_ref") is None else str(item.get("bill_ref")),
        "invoice_date": "" if item.get("bill_date") is None else str(item.get("bill_date")),
        "due_date": "" if item.get("due_date") is None else str(item.get("due_date")),
        "overdue_days": "" if item.get("overdue_days") is None else str(item.get("overdue_days")),
        "ledger_name": ledger,
        "representative": "" if item.get("representative") is None else str(item.get("representative")),
        "amount": "" if item.get("outstanding") is None else str(item.get("outstanding")),
        "closing": "" if item.get("closing") is None else str(item.get("closing")),
    }


class FetchBody(BaseModel):
    collections: list[str] = Field(min_length=1)
    from_date: str = Field(min_length=1)
    to_date: str = Field(min_length=1)
    full_fetch: bool = False


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


def _apply_fetch_window(from_date: str, to_date: str, full_fetch: bool, info: dict) -> tuple[str, str]:
    """Full fetch keeps the selected period. Otherwise keep the last 15 days through To."""
    if full_fetch:
        return from_date, to_date
    end = parse_row_date(to_date)
    if end is None:
        return from_date, to_date
    start = end - timedelta(days=14)
    period_start = parse_row_date(info.get("from_date", ""))
    if period_start and start < period_start:
        start = period_start
    if start > end:
        start = end
    return tally_date(start.isoformat()), to_date


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
):
    unknown = [name for name in body.collections if name not in COLLECTIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown collection: {unknown[0]}")
    job_id = create_job(_user, body.model_dump())
    threading.Thread(target=_fetch_worker, args=(job_id,), daemon=True).start()
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def job_status(job_id: str, _user: str = Depends(current_user)):
    meta = _owned_job(job_id, _user)
    result = load_result(job_id) or {}
    return {"job_id": job_id, "status": meta.get("status") or "", **result}


@router.get("/jobs/{job_id}/events")
def job_events(job_id: str, _user: str = Depends(current_user)):
    _owned_job(job_id, _user)
    return StreamingResponse(
        iter_events(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/jobs/{job_id}/sync")
def job_sync(job_id: str, _user: str = Depends(current_user)):
    _owned_job(job_id, _user)
    if not claim_sync(job_id):
        raise HTTPException(status_code=409, detail="Fetch is not waiting for sync")
    threading.Thread(target=_sync_worker, args=(job_id,), daemon=True).start()
    return {"ok": True}


def _owned_job(job_id: str, user: str) -> dict:
    meta = job_meta(job_id)
    if not meta or meta.get("user") != user:
        raise HTTPException(status_code=404, detail="Job not found")
    return meta


def _line_kind(text: str) -> str:
    if text.startswith("Err"):
        return "err"
    if text.startswith("Hit:"):
        return "hit"
    if text.startswith("Get:"):
        return "get"
    if text.startswith("Ign"):
        return "ign"
    return "info"


def _session():
    from backend import db as database

    if database.SessionLocal is None:
        database.init_engine()
    return database.SessionLocal()


def _fetch_worker(job_id: str) -> None:
    meta = job_meta(job_id) or {}
    body = FetchBody(**json.loads(meta.get("payload") or "{}"))
    token = bind_progress(lambda line: publish(job_id, _line_kind(line), line))
    db = _session()
    try:
        publish(job_id, "cmd", "fetch")
        publish(job_id, "info", "Reading package lists...")
        result = _perform_fetch(db, body)
        store_result(job_id, result)
        for row in result["results"]:
            if row.get("error"):
                publish(job_id, "err", f"Err {row['label']}: {row['error']}")
                continue
            if row.get("vouchers") is not None:
                publish(
                    job_id,
                    "ok",
                    f"Fetched {row['vouchers']} vouchers, {row['lines']} lines — {row['label']} ({row['elapsed']})",
                )
            else:
                noun = _count_noun(str(row.get("id") or ""))
                publish(job_id, "ok", f"Fetched {row['count']} {noun} — {row['label']} ({row['elapsed']})")
        labels = " ".join(row["label"] for row in result["results"] if not row.get("error"))
        publish(job_id, "info", "The following collections will be synced:")
        publish(job_id, "info", f"  {labels}")
        publish(job_id, "info", "After this operation, rows in this period are replaced.")
        publish(job_id, "prompt", "Do you want to continue? [Y/n]")
        set_status(job_id, "prompt")
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Fetch failed"
        publish(job_id, "err", f"Err {detail}")
        publish(job_id, "error", detail)
        set_status(job_id, "error")
    except Exception as exc:
        publish(job_id, "err", f"Err {exc}")
        publish(job_id, "error", str(exc))
        set_status(job_id, "error")
    finally:
        reset_progress(token)
        db.close()


def _sync_worker(job_id: str) -> None:
    meta = job_meta(job_id) or {}
    body = FetchBody(**json.loads(meta.get("payload") or "{}"))
    token = bind_progress(lambda line: publish(job_id, _line_kind(line), line))
    db = _session()
    try:
        publish(job_id, "cmd", "sync")
        publish(job_id, "info", "Reading package lists...")
        result = _perform_sync(db, body)
        store_result(job_id, result)
        for row in result["results"]:
            if row.get("error"):
                publish(job_id, "err", f"Err {row['label']}: {row['error']}")
                continue
            if row.get("vouchers") is not None:
                publish(job_id, "info", f"Unpacking {row['label']} ({row['lines']} lines) ...")
                publish(
                    job_id,
                    "ok",
                    f"Setting up {row['label']} ({row['vouchers']} vouchers, {row['lines']} lines) ...",
                )
            else:
                noun = _count_noun(str(row.get("id") or ""))
                publish(job_id, "info", f"Unpacking {row['label']} ({row['count']} {noun}) ...")
                publish(job_id, "ok", f"Setting up {row['label']} ({row['count']} {noun}) ...")
        publish(job_id, "ok", "done.")
        publish(job_id, "done", "done.")
        set_status(job_id, "done")
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Sync failed"
        publish(job_id, "err", f"Err {detail}")
        publish(job_id, "error", detail)
        set_status(job_id, "error")
    except Exception as exc:
        publish(job_id, "err", f"Err {exc}")
        publish(job_id, "error", str(exc))
        set_status(job_id, "error")
    finally:
        reset_progress(token)
        db.close()


def _perform_fetch(db: Session, body: FetchBody) -> dict:
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
    emit_progress(f"Hit:1 {url} {company}")
    emit_progress("Reading state information...")
    _in_tally_period(from_date, to_date, info)
    from_date, to_date = _apply_fetch_window(from_date, to_date, body.full_fetch, info)

    results = []
    for name in seen:
        spec = COLLECTIONS[name]
        started = time.perf_counter()
        try:
            if name == "pnl":
                lines = fetch_profit_loss_months(url, "", from_date, to_date)
                elapsed = _elapsed_text(time.perf_counter() - started)
                rows = [_item_row(line, PNL_FIELDS) for line in lines]
                results.append(
                    {
                        "id": name,
                        "label": spec["label"],
                        "count": len(rows),
                        "elapsed": elapsed,
                        "columns": list(PNL_FIELDS),
                        "rows": rows,
                        "error": "",
                    }
                )
                continue
            if name == "stocksummary":
                lines = fetch_stock_summary(url, "", from_date, to_date)
                elapsed = _elapsed_text(time.perf_counter() - started)
                rows = [_item_row(line, STOCK_FIELDS) for line in lines]
                results.append(
                    {
                        "id": name,
                        "label": spec["label"],
                        "count": len(rows),
                        "elapsed": elapsed,
                        "columns": list(STOCK_FIELDS),
                        "rows": rows,
                        "error": "",
                    }
                )
                continue
            if name == "stockregister":
                lines = fetch_stock_register(url, "", from_date, to_date)
                elapsed = _elapsed_text(time.perf_counter() - started)
                rows = [_item_row(line, STOCK_REGISTER_FIELDS) for line in lines]
                results.append(
                    {
                        "id": name,
                        "label": spec["label"],
                        "count": len(rows),
                        "elapsed": elapsed,
                        "columns": list(STOCK_REGISTER_FIELDS),
                        "rows": rows,
                        "error": "",
                    }
                )
                continue
            if name == "inventory":
                lines = fetch_stock_items(url)
                elapsed = _elapsed_text(time.perf_counter() - started)
                rows = [_item_row(line, INVENTORY_FIELDS) for line in lines]
                results.append(
                    {
                        "id": name,
                        "label": spec["label"],
                        "count": len(rows),
                        "elapsed": elapsed,
                        "columns": list(INVENTORY_FIELDS),
                        "rows": rows,
                        "error": "",
                    }
                )
                continue
            if name == "accounts":
                lines = fetch_accounts(url)
                elapsed = _elapsed_text(time.perf_counter() - started)
                rows = [_item_row(line, ACCOUNT_FIELDS) for line in lines]
                results.append(
                    {
                        "id": name,
                        "label": spec["label"],
                        "count": len(rows),
                        "elapsed": elapsed,
                        "columns": list(ACCOUNT_FIELDS),
                        "rows": rows,
                        "error": "",
                    }
                )
                continue
            if name == "costcentres":
                lines = fetch_cost_centres(url)
                elapsed = _elapsed_text(time.perf_counter() - started)
                rows = [_item_row(line, COSTCENTRE_FIELDS) for line in lines]
                results.append(
                    {
                        "id": name,
                        "label": spec["label"],
                        "count": len(rows),
                        "elapsed": elapsed,
                        "columns": list(COSTCENTRE_FIELDS),
                        "rows": rows,
                        "error": "",
                    }
                )
                continue
            if name in {"receivables", "payables"}:
                lines = spec["fetch"](url, "", from_date, to_date)
                elapsed = _elapsed_text(time.perf_counter() - started)
                rows = [_bill_display_row(line) for line in lines]
                results.append(
                    {
                        "id": name,
                        "label": spec["label"],
                        "count": len(rows),
                        "elapsed": elapsed,
                        "columns": list(BILL_DISPLAY_FIELDS),
                        "rows": rows,
                        "error": "",
                    }
                )
                continue
            if name == "daybook":
                lines = fetch_daybook(url, "", from_date, to_date)
                elapsed = _elapsed_text(time.perf_counter() - started)
                rows = [_item_row(line, DAYBOOK_FIELDS) for line in lines]
                results.append(
                    {
                        "id": name,
                        "label": spec["label"],
                        "count": len(rows),
                        "elapsed": elapsed,
                        "columns": list(DAYBOOK_FIELDS),
                        "rows": rows,
                        "error": "",
                    }
                )
                continue
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
                    "vouchers": len(rows),
                    "lines": sum(int(header.get("stock_lines") or 0) for header in headers),
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


def _perform_sync(db: Session, body: FetchBody) -> dict:
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
    emit_progress(f"Hit:1 {url} {company}")
    emit_progress("Reading state information...")
    _in_tally_period(from_date, to_date, info)
    from_date, to_date = _apply_fetch_window(from_date, to_date, body.full_fetch, info)
    binding = get_company_database(db, company)
    if not binding or not binding.mysql_database:
        raise HTTPException(status_code=400, detail="Select and save a MySQL database")
    database = binding.mysql_database

    results = []
    for name in seen:
        spec = COLLECTIONS[name]
        started = time.perf_counter()
        try:
            if name == "pnl":
                lines = fetch_profit_loss_months(url, "", from_date, to_date)
                count = replace_pnl(database, lines, from_date, to_date)
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
                continue
            if name == "stocksummary":
                lines = fetch_stock_summary(url, "", from_date, to_date)
                count = replace_stock_summary(database, lines, from_date, to_date)
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
                continue
            if name == "stockregister":
                lines = fetch_stock_register(url, "", from_date, to_date)
                count = replace_stock_register(database, lines, from_date, to_date)
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
                continue
            if name == "inventory":
                lines = fetch_stock_items(url)
                count = replace_inventory(database, lines)
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
                continue
            if name == "accounts":
                lines = fetch_accounts(url)
                count = replace_accounts(database, lines)
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
                continue
            if name == "costcentres":
                lines = fetch_cost_centres(url)
                count = replace_cost_centres(database, lines)
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
                continue
            if name == "receivables":
                lines = receivables.fetch(url, "", from_date, to_date)
                count = replace_receivables(database, lines)
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
                continue
            if name == "payables":
                lines = payables.fetch(url, "", from_date, to_date)
                count = replace_payables(database, lines)
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
                continue
            if name == "daybook":
                lines = fetch_daybook(url, "", from_date, to_date)
                count = replace_daybook(database, lines, from_date, to_date)
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
                continue
            headers, items, _ledgers = spec["fetch"](
                url, "", from_date, to_date, enrich=True
            )
            count = replace_period(database, name, items, from_date, to_date)
            elapsed = _elapsed_text(time.perf_counter() - started)
            results.append(
                {
                    "id": name,
                    "label": spec["label"],
                    "count": count,
                    "vouchers": len(headers),
                    "lines": count,
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
    if "line_fields" not in spec:
        raise HTTPException(status_code=400, detail="This collection has no voucher lines")
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
        if body.collection == "sales":
            attach_alternate_qty(url, items)
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
