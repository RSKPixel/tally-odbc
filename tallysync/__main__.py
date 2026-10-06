#!/usr/bin/env python3
"""Run all collection CLIs: receivables, payables, sales, purchase."""

from __future__ import annotations

from tallysync import payables, purchase, receivables, sales
from tallysync.tallylib import run_cli


def run(url: str, company: str, from_date: str, to_date: str, out) -> None:
    receivables.run(url, company, from_date, to_date, out)
    payables.run(url, company, from_date, to_date, out)
    sales.run(url, company, from_date, to_date, out)
    purchase.run(url, company, from_date, to_date, out)


def main() -> None:
    run_cli("Tally native sales + purchase + receivables + payables → CSV", run)


if __name__ == "__main__":
    main()
