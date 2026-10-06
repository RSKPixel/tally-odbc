#!/usr/bin/env python3
"""Sales vouchers (SIVENDHI BILLING + Sales) → CSV. Import fetch() from FastAPI later."""

from __future__ import annotations

from pathlib import Path

from tallysync.tallylib import (
    SALES_CHILDOF,
    SALES_TYPE,
    SALES_TYPES,
    fetch_native_vouchers,
    run_cli,
    write_voucher_csvs,
)


def fetch(
    url: str, company: str, from_date: str, to_date: str, *, enrich: bool = True
) -> tuple[list[dict], list[dict], list[dict]]:
    return fetch_native_vouchers(
        url, company, from_date, to_date, SALES_CHILDOF, SALES_TYPE, SALES_TYPES, enrich=enrich
    )


def save(
    out: Path, headers: list[dict], items: list[dict], ledgers: list[dict]
) -> tuple[Path, Path, Path]:
    return write_voucher_csvs(out, "sales", headers, items, ledgers)


def run(url: str, company: str, from_date: str, to_date: str, out: Path) -> tuple[list[dict], list[dict], list[dict]]:
    headers, items, ledgers = fetch(url, company, from_date, to_date)
    paths = save(out, headers, items, ledgers)
    print(f"Saved {len(headers)} sales, {len(items)} items, {len(ledgers)} ledgers")
    for path in paths:
        print(f"  {path}")
    return headers, items, ledgers


def main() -> None:
    run_cli("Tally native Sales + SIVENDHI BILLING → CSV", run)


if __name__ == "__main__":
    main()
