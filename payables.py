#!/usr/bin/env python3
"""Bills Payable (outstanding) → CSV. Import fetch() from FastAPI later."""

from __future__ import annotations

from pathlib import Path

from tallylib import BILL_FIELDS, fetch_bills_report, run_cli, write_csv

REPORT_ID = "Bills Payable"


def fetch(url: str, company: str, from_date: str, to_date: str) -> list[dict]:
    return fetch_bills_report(url, company, from_date, to_date, REPORT_ID)


def save(out: Path, rows: list[dict]) -> Path:
    path = out / "payables.csv"
    write_csv(path, BILL_FIELDS, rows)
    return path


def run(url: str, company: str, from_date: str, to_date: str, out: Path) -> list[dict]:
    rows = fetch(url, company, from_date, to_date)
    path = save(out, rows)
    print(f"Saved {len(rows)} payables as on {to_date}")
    print(f"  {path}")
    return rows


def main() -> None:
    run_cli("Tally native Bills Payable → CSV", run)


if __name__ == "__main__":
    main()
