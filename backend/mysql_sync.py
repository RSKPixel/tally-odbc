from __future__ import annotations

from datetime import datetime, timedelta

from backend.mysql import MysqlError, mysql_connect, valid_database_name
from tallysync.tallylib import first_number, parse_row_date

SALES_TABLE = "tallysync_sales"
PURCHASE_TABLE = "tallysync_purchases"
PNL_TABLE = "tallysync_pnl"
STOCK_TABLE = "tallysync_stocksummary"
STOCK_REGISTER_TABLE = "tallysync_stockregister"
INVENTORY_TABLE = "tallysync_inventory"
ACCOUNT_TABLE = "tallysync_accounts"
COSTCENTRE_TABLE = "tallysync_costcentres"
COSTCENTRE_COLUMNS = [
    "master_id",
    "guid",
    "cost_centre",
    "parent",
    "category",
]
RECEIVABLE_TABLE = "tallysync_receivables"
PAYABLE_TABLE = "tallysync_payables"
BILL_COLUMNS = [
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
DAYBOOK_TABLE = "tallysync_daybook"
DAYBOOK_COLUMNS = [
    "voucher_type",
    "voucher_no",
    "voucher_date",
    "narration",
    "debit_credit",
    "ledger_name",
    "costcentre_name",
    "costcentre_amt",
    "ledger_amount",
    "bill_no",
    "bill_type",
]
ACCOUNT_COLUMNS = [
    "master_id",
    "guid",
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
]
INVENTORY_COLUMNS = [
    "master_id",
    "guid",
    "stock_item",
    "stock_group",
    "category",
    "base_unit",
    "alternate_unit",
    "conversion",
    "denominator",
    "packing",
    "gst_applicable",
]
STOCK_COLUMNS = [
    "period_from",
    "period_to",
    "line_no",
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
STOCK_REGISTER_COLUMNS = [
    "period_from",
    "period_to",
    "line_no",
    "voucher_date",
    "stock_group",
    "stock_item",
    "particulars",
    "voucher_type",
    "voucher_no",
    "inwards",
    "inward_qty",
    "inward_value",
    "outwards",
    "outward_qty",
    "outward_value",
    "closing",
    "closing_qty",
    "closing_value",
]
PNL_COLUMNS = [
    "period_from",
    "period_to",
    "line_no",
    "account",
    "amount",
    "amount_side",
]
SALES_COLUMNS = [
    "voucher_no",
    "voucher_date",
    "ledger_name",
    "broker",
    "item_count",
    "item_no",
    "stock_group",
    "stock_item",
    "brand",
    "packing",
    "qty",
    "qty_alt",
    "alternate_unit",
    "conversion",
    "rate",
    "amount",
    "discount",
    "cartage",
]
PURCHASE_COLUMNS = [
    "voucher_no",
    "voucher_date",
    "ledger_name",
    "broker",
    "item_count",
    "itemno",
    "stock_item",
    "brand",
    "packing",
    "qty",
    "weight",
    "rate",
    "amount",
    "box",
    "qty_per_box",
]
CREATE_TABLES = {
    SALES_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_sales` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `voucher_no` text,
  `voucher_date` datetime DEFAULT NULL,
  `ledger_name` text,
  `broker` text,
  `item_count` double DEFAULT NULL,
  `item_no` double DEFAULT NULL,
  `stock_group` text,
  `stock_item` text,
  `brand` text,
  `packing` double DEFAULT NULL,
  `qty` double DEFAULT NULL,
  `qty_alt` double DEFAULT NULL,
  `alternate_unit` text,
  `conversion` double DEFAULT NULL,
  `rate` double DEFAULT NULL,
  `amount` double DEFAULT NULL,
  `discount` double DEFAULT 0,
  `cartage` double DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
    PURCHASE_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_purchases` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `voucher_no` text,
  `voucher_date` datetime DEFAULT NULL,
  `ledger_name` text,
  `broker` text,
  `item_count` double DEFAULT NULL,
  `itemno` double DEFAULT NULL,
  `stock_item` text,
  `brand` text,
  `packing` double DEFAULT NULL,
  `qty` double DEFAULT NULL,
  `weight` double DEFAULT NULL,
  `rate` double DEFAULT NULL,
  `amount` double DEFAULT NULL,
  `box` double DEFAULT NULL,
  `qty_per_box` double DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
    PNL_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_pnl` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `period_from` datetime DEFAULT NULL,
  `period_to` datetime DEFAULT NULL,
  `line_no` double DEFAULT NULL,
  `account` text,
  `amount` double DEFAULT NULL,
  `amount_side` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
    STOCK_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_stocksummary` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `period_from` datetime DEFAULT NULL,
  `period_to` datetime DEFAULT NULL,
  `line_no` double DEFAULT NULL,
  `stock_group` text,
  `stock_item` text,
  `alternate_unit` text,
  `conversion` double DEFAULT NULL,
  `opening` text,
  `opening_alt` double DEFAULT NULL,
  `opening_rate` double DEFAULT NULL,
  `opening_value` double DEFAULT NULL,
  `inwards` text,
  `inwards_alt` double DEFAULT NULL,
  `inward_rate` double DEFAULT NULL,
  `inward_value` double DEFAULT NULL,
  `outwards` text,
  `outwards_alt` double DEFAULT NULL,
  `outward_rate` double DEFAULT NULL,
  `outward_value` double DEFAULT NULL,
  `closing` text,
  `closing_alt` double DEFAULT NULL,
  `closing_rate` double DEFAULT NULL,
  `closing_value` double DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
    STOCK_REGISTER_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_stockregister` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `period_from` datetime DEFAULT NULL,
  `period_to` datetime DEFAULT NULL,
  `line_no` double DEFAULT NULL,
  `voucher_date` datetime DEFAULT NULL,
  `stock_group` text,
  `stock_item` text,
  `particulars` text,
  `voucher_type` text,
  `voucher_no` text,
  `inwards` text,
  `inward_qty` double DEFAULT NULL,
  `inward_value` double DEFAULT NULL,
  `outwards` text,
  `outward_qty` double DEFAULT NULL,
  `outward_value` double DEFAULT NULL,
  `closing` text,
  `closing_qty` double DEFAULT NULL,
  `closing_value` double DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
    INVENTORY_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_inventory` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `master_id` text,
  `guid` text,
  `stock_item` text,
  `stock_group` text,
  `category` text,
  `base_unit` text,
  `alternate_unit` text,
  `conversion` double DEFAULT NULL,
  `denominator` double DEFAULT NULL,
  `packing` double DEFAULT NULL,
  `gst_applicable` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
    ACCOUNT_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_accounts` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `master_id` text,
  `guid` text,
  `ledger_name` text,
  `account_group` text,
  `primary_group` text,
  `mailing_name` text,
  `address_1` text,
  `address_2` text,
  `address_3` text,
  `address_4` text,
  `pin_code` text,
  `gstin` text,
  `gst_registration_type` text,
  `state` text,
  `country` text,
  `pan` text,
  `phone` text,
  `mobile` text,
  `email` text,
  `bill_wise` text,
  `favouring_name` text,
  `account_number` text,
  `bank_code` text,
  `bank_name` text,
  `representative` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
    COSTCENTRE_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_costcentres` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `master_id` text,
  `guid` text,
  `cost_centre` text,
  `parent` text,
  `category` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
    RECEIVABLE_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_receivables` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `as_on` datetime DEFAULT NULL,
  `invoice_no` text,
  `invoice_date` datetime DEFAULT NULL,
  `due_date` datetime DEFAULT NULL,
  `overdue_days` double DEFAULT NULL,
  `ledger_name` text,
  `representative` text,
  `amount` double DEFAULT NULL,
  `closing` double DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
    PAYABLE_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_payables` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `as_on` datetime DEFAULT NULL,
  `invoice_no` text,
  `invoice_date` datetime DEFAULT NULL,
  `due_date` datetime DEFAULT NULL,
  `overdue_days` double DEFAULT NULL,
  `ledger_name` text,
  `representative` text,
  `amount` double DEFAULT NULL,
  `closing` double DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
    DAYBOOK_TABLE: """
CREATE TABLE IF NOT EXISTS `tallysync_daybook` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `voucher_type` text,
  `voucher_no` text,
  `voucher_date` datetime DEFAULT NULL,
  `narration` text,
  `debit_credit` text,
  `ledger_name` text,
  `costcentre_name` text,
  `costcentre_amt` double DEFAULT NULL,
  `ledger_amount` double DEFAULT NULL,
  `bill_no` text,
  `bill_type` text,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",
}


def _ensure_text_columns(cur, table: str, columns: list[str]) -> None:
    cur.execute(f"SHOW COLUMNS FROM `{table}`")
    existing = set()
    for row in cur.fetchall():
        if isinstance(row, dict):
            existing.add(str(row.get("Field") or row.get("field") or ""))
        else:
            existing.add(str(row[0]))
    existing.discard("")
    for name in columns:
        if name not in existing:
            cur.execute(f"ALTER TABLE `{table}` ADD COLUMN `{name}` text")


def _number(value: str | None):
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _text(value: str | None) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


def _when(value: str | None):
    parsed = parse_row_date(value or "")
    if parsed is None:
        return None
    return datetime(parsed.year, parsed.month, parsed.day)


def _sales_row(item: dict) -> dict:
    discount = _number(item.get("discount"))
    return {
        "voucher_no": _text(item.get("voucher_no") or item.get("voucher_number")),
        "voucher_date": _when(item.get("voucher_date") or item.get("date")),
        "ledger_name": _text(item.get("ledger_name") or item.get("party")),
        "broker": _text(item.get("broker") or item.get("rep_or_broker")),
        "item_count": _number(item.get("item_count")),
        "item_no": _number(item.get("item_no")),
        "stock_group": _text(item.get("stock_group")),
        "stock_item": _text(item.get("stock_item")),
        "brand": _text(item.get("brand")),
        "packing": _number(item.get("packing")),
        "qty": _number(item.get("qty")),
        "qty_alt": _number(item.get("qty_alt")),
        "alternate_unit": _text(item.get("alternate_unit")),
        "conversion": _number(item.get("conversion")),
        "rate": _number(item.get("rate")),
        "amount": _number(item.get("amount")),
        "discount": 0.0 if discount is None else discount,
        "cartage": _number(item.get("cartage")),
    }


def _purchase_row(item: dict) -> dict:
    return {
        "voucher_no": _text(item.get("voucher_no") or item.get("voucher_number")),
        "voucher_date": _when(item.get("voucher_date") or item.get("date")),
        "ledger_name": _text(item.get("ledger_name") or item.get("party")),
        "broker": _text(item.get("broker") or item.get("rep_or_broker")),
        "item_count": _number(item.get("item_count")),
        "itemno": _number(item.get("itemno") or item.get("item_no")),
        "stock_item": _text(item.get("stock_item")),
        "brand": _text(item.get("brand")),
        "packing": _number(item.get("packing")),
        "qty": _number(item.get("qty")),
        "weight": _number(item.get("weight")),
        "rate": _number(item.get("rate")),
        "amount": _number(item.get("amount")),
        "box": _number(item.get("box")),
        "qty_per_box": _number(item.get("qty_per_box")),
    }


def _pnl_row(item: dict) -> dict:
    return {
        "period_from": _when(item.get("period_from")),
        "period_to": _when(item.get("period_to")),
        "line_no": _number(item.get("line_no")),
        "account": _text(item.get("account")),
        "amount": _number(item.get("amount")),
        "amount_side": _text(item.get("amount_side")),
    }


def replace_pnl(database: str, rows: list[dict], from_date: str, to_date: str) -> int:
    """Replace Profit and Loss lines whose period_from sits in [from_date, to_date]."""
    if not valid_database_name(database):
        raise MysqlError("Invalid database name")
    start = parse_row_date(from_date)
    end = parse_row_date(to_date)
    if start is None or end is None:
        raise MysqlError("Invalid sync dates")
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day) + timedelta(days=1)
    mapped = [_pnl_row(item) for item in rows]
    placeholders = ", ".join(["%s"] * len(PNL_COLUMNS))
    column_sql = ", ".join(PNL_COLUMNS)
    insert_sql = f"INSERT INTO `{PNL_TABLE}` ({column_sql}) VALUES ({placeholders})"

    conn = mysql_connect(database)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES[PNL_TABLE])
            cur.execute(
                f"DELETE FROM `{PNL_TABLE}` WHERE period_from >= %s AND period_from < %s",
                (start_dt, end_dt),
            )
            values = [[row[name] for name in PNL_COLUMNS] for row in mapped]
            batch = 500
            for start_at in range(0, len(values), batch):
                cur.executemany(insert_sql, values[start_at : start_at + batch])
        conn.commit()
    except MysqlError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise MysqlError(str(exc)) from exc
    finally:
        conn.close()
    return len(mapped)


def _inventory_row(item: dict) -> dict:
    return {
        "master_id": _text(item.get("master_id")),
        "guid": _text(item.get("guid")),
        "stock_item": _text(item.get("stock_item")),
        "stock_group": _text(item.get("stock_group")),
        "category": _text(item.get("category")),
        "base_unit": _text(item.get("base_unit")),
        "alternate_unit": _text(item.get("alternate_unit")),
        "conversion": _number(item.get("conversion")),
        "denominator": _number(item.get("denominator")),
        "packing": _number(item.get("packing")),
        "gst_applicable": _text(item.get("gst_applicable")),
    }


def replace_inventory(database: str, rows: list[dict]) -> int:
    """Clear tallysync_inventory, then insert this stock-item master pull."""
    if not valid_database_name(database):
        raise MysqlError("Invalid database name")
    mapped = [_inventory_row(item) for item in rows if str(item.get("stock_item") or "").strip()]
    placeholders = ", ".join(["%s"] * len(INVENTORY_COLUMNS))
    column_sql = ", ".join(INVENTORY_COLUMNS)
    insert_sql = f"INSERT INTO `{INVENTORY_TABLE}` ({column_sql}) VALUES ({placeholders})"

    conn = mysql_connect(database)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES[INVENTORY_TABLE])
            cur.execute(f"DELETE FROM `{INVENTORY_TABLE}`")
            values = [[row[name] for name in INVENTORY_COLUMNS] for row in mapped]
            batch = 500
            for start_at in range(0, len(values), batch):
                cur.executemany(insert_sql, values[start_at : start_at + batch])
        conn.commit()
    except MysqlError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise MysqlError(str(exc)) from exc
    finally:
        conn.close()
    return len(mapped)


def _account_row(item: dict) -> dict:
    return {name: _text(item.get(name)) for name in ACCOUNT_COLUMNS}


def replace_accounts(database: str, rows: list[dict]) -> int:
    """Clear tallysync_accounts, then insert this ledger master pull."""
    if not valid_database_name(database):
        raise MysqlError("Invalid database name")
    mapped = [_account_row(item) for item in rows if str(item.get("ledger_name") or "").strip()]
    placeholders = ", ".join(["%s"] * len(ACCOUNT_COLUMNS))
    column_sql = ", ".join(ACCOUNT_COLUMNS)
    insert_sql = f"INSERT INTO `{ACCOUNT_TABLE}` ({column_sql}) VALUES ({placeholders})"

    conn = mysql_connect(database)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES[ACCOUNT_TABLE])
            _ensure_text_columns(cur, ACCOUNT_TABLE, ACCOUNT_COLUMNS)
            cur.execute(f"DELETE FROM `{ACCOUNT_TABLE}`")
            values = [[row[name] for name in ACCOUNT_COLUMNS] for row in mapped]
            batch = 500
            for start_at in range(0, len(values), batch):
                cur.executemany(insert_sql, values[start_at : start_at + batch])
        conn.commit()
    except MysqlError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise MysqlError(str(exc)) from exc
    finally:
        conn.close()
    return len(mapped)


def _costcentre_row(item: dict) -> dict:
    return {name: _text(item.get(name)) for name in COSTCENTRE_COLUMNS}


def replace_cost_centres(database: str, rows: list[dict]) -> int:
    """Clear tallysync_costcentres, then insert this cost-centre master pull."""
    if not valid_database_name(database):
        raise MysqlError("Invalid database name")
    mapped = [_costcentre_row(item) for item in rows if str(item.get("cost_centre") or "").strip()]
    placeholders = ", ".join(["%s"] * len(COSTCENTRE_COLUMNS))
    column_sql = ", ".join(COSTCENTRE_COLUMNS)
    insert_sql = f"INSERT INTO `{COSTCENTRE_TABLE}` ({column_sql}) VALUES ({placeholders})"

    conn = mysql_connect(database)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES[COSTCENTRE_TABLE])
            _ensure_text_columns(cur, COSTCENTRE_TABLE, COSTCENTRE_COLUMNS)
            cur.execute(f"DELETE FROM `{COSTCENTRE_TABLE}`")
            values = [[row[name] for name in COSTCENTRE_COLUMNS] for row in mapped]
            batch = 500
            for start_at in range(0, len(values), batch):
                cur.executemany(insert_sql, values[start_at : start_at + batch])
        conn.commit()
    except MysqlError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise MysqlError(str(exc)) from exc
    finally:
        conn.close()
    return len(mapped)


def _account_representatives(cur) -> dict[str, str]:
    try:
        cur.execute(
            f"SELECT ledger_name, representative FROM `{ACCOUNT_TABLE}` "
            "WHERE representative IS NOT NULL AND representative <> ''"
        )
    except Exception:
        return {}
    out: dict[str, str] = {}
    for row in cur.fetchall():
        if isinstance(row, dict):
            name = str(row.get("ledger_name") or "").strip()
            rep = str(row.get("representative") or "").strip()
        else:
            name = str(row[0] or "").strip()
            rep = str(row[1] or "").strip()
        if name and rep:
            out[name] = rep
    return out


def _bill_row(item: dict, representatives: dict[str, str]) -> dict:
    ledger = _text(item.get("ledger_name") or item.get("party"))
    return {
        "as_on": _when(item.get("as_on")),
        "invoice_no": _text(item.get("invoice_no") or item.get("bill_ref")),
        "invoice_date": _when(item.get("invoice_date") or item.get("bill_date")),
        "due_date": _when(item.get("due_date")),
        "overdue_days": _number(item.get("overdue_days")),
        "ledger_name": ledger,
        "representative": _text(item.get("representative") or (representatives.get(ledger or "") if ledger else "")),
        "amount": _number(item.get("amount") or item.get("outstanding")),
        "closing": _number(item.get("closing")),
    }


def _replace_bills(database: str, table: str, rows: list[dict]) -> int:
    if not valid_database_name(database):
        raise MysqlError("Invalid database name")
    placeholders = ", ".join(["%s"] * len(BILL_COLUMNS))
    column_sql = ", ".join(BILL_COLUMNS)
    insert_sql = f"INSERT INTO `{table}` ({column_sql}) VALUES ({placeholders})"

    conn = mysql_connect(database)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES[table])
            representatives = _account_representatives(cur)
            mapped = [_bill_row(item, representatives) for item in rows]
            mapped = [row for row in mapped if row.get("ledger_name") or row.get("invoice_no")]
            cur.execute(f"DELETE FROM `{table}`")
            values = [[row[name] for name in BILL_COLUMNS] for row in mapped]
            batch = 500
            for start_at in range(0, len(values), batch):
                cur.executemany(insert_sql, values[start_at : start_at + batch])
        conn.commit()
    except MysqlError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise MysqlError(str(exc)) from exc
    finally:
        conn.close()
    return len(mapped)


def replace_receivables(database: str, rows: list[dict]) -> int:
    """Clear tallysync_receivables, then insert this Bills Receivable snapshot."""
    return _replace_bills(database, RECEIVABLE_TABLE, rows)


def replace_payables(database: str, rows: list[dict]) -> int:
    """Clear tallysync_payables, then insert this Bills Payable snapshot."""
    return _replace_bills(database, PAYABLE_TABLE, rows)


def _daybook_row(item: dict) -> dict:
    return {
        "voucher_type": _text(item.get("voucher_type") or item.get("VTYPE")),
        "voucher_no": _text(item.get("voucher_no") or item.get("VNO")),
        "voucher_date": _when(item.get("voucher_date") or item.get("VDT")),
        "narration": _text(item.get("narration") or item.get("NARRATION")),
        "debit_credit": _text(item.get("debit_credit") or item.get("DEBIT_CREDIT")),
        "ledger_name": _text(item.get("ledger_name") or item.get("LEDGER_NAME")),
        "costcentre_name": _text(item.get("costcentre_name") or item.get("COSTCENTRE_NAME")),
        "costcentre_amt": _number(item.get("costcentre_amt") or item.get("COSTCENTRE_AMT")),
        "ledger_amount": _number(item.get("ledger_amount") or item.get("LEDGER_AMOUNT")),
        "bill_no": _text(item.get("bill_no") or item.get("BILL_NO")),
        "bill_type": _text(item.get("bill_type") or item.get("BILL_TYPE")),
    }


def replace_daybook(database: str, rows: list[dict], from_date: str, to_date: str) -> int:
    """Replace daybook ledger lines for [from_date, to_date]."""
    if not valid_database_name(database):
        raise MysqlError("Invalid database name")
    start = parse_row_date(from_date)
    end = parse_row_date(to_date)
    if start is None or end is None:
        raise MysqlError("Invalid sync dates")
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day) + timedelta(days=1)
    mapped = [_daybook_row(item) for item in rows if str(item.get("ledger_name") or item.get("LEDGER_NAME") or "").strip()]
    placeholders = ", ".join(["%s"] * len(DAYBOOK_COLUMNS))
    column_sql = ", ".join(DAYBOOK_COLUMNS)
    insert_sql = f"INSERT INTO `{DAYBOOK_TABLE}` ({column_sql}) VALUES ({placeholders})"

    conn = mysql_connect(database)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES[DAYBOOK_TABLE])
            _ensure_text_columns(
                cur,
                DAYBOOK_TABLE,
                [
                    "voucher_type",
                    "voucher_no",
                    "narration",
                    "debit_credit",
                    "ledger_name",
                    "costcentre_name",
                    "bill_no",
                    "bill_type",
                ],
            )
            cur.execute(
                f"DELETE FROM `{DAYBOOK_TABLE}` WHERE voucher_date >= %s AND voucher_date < %s",
                (start_dt, end_dt),
            )
            values = [[row[name] for name in DAYBOOK_COLUMNS] for row in mapped]
            batch = 500
            for start_at in range(0, len(values), batch):
                cur.executemany(insert_sql, values[start_at : start_at + batch])
        conn.commit()
    except MysqlError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise MysqlError(str(exc)) from exc
    finally:
        conn.close()
    return len(mapped)


def _stock_row(item: dict) -> dict:
    return {
        "period_from": _when(item.get("period_from")),
        "period_to": _when(item.get("period_to")),
        "line_no": _number(item.get("line_no")),
        "stock_group": _text(item.get("stock_group")),
        "stock_item": _text(item.get("stock_item")),
        "alternate_unit": _text(item.get("alternate_unit")),
        "conversion": _number(item.get("conversion")),
        "opening": _text(item.get("opening")),
        "opening_alt": _number(item.get("opening_alt")),
        "opening_rate": _number(item.get("opening_rate")),
        "opening_value": _number(item.get("opening_value")),
        "inwards": _text(item.get("inwards")),
        "inwards_alt": _number(item.get("inwards_alt")),
        "inward_rate": _number(item.get("inward_rate")),
        "inward_value": _number(item.get("inward_value")),
        "outwards": _text(item.get("outwards")),
        "outwards_alt": _number(item.get("outwards_alt")),
        "outward_rate": _number(item.get("outward_rate")),
        "outward_value": _number(item.get("outward_value")),
        "closing": _text(item.get("closing")),
        "closing_alt": _number(item.get("closing_alt")),
        "closing_rate": _number(item.get("closing_rate")),
        "closing_value": _number(item.get("closing_value")),
    }


def _stock_register_row(item: dict) -> dict:
    return {
        "period_from": _when(item.get("period_from")),
        "period_to": _when(item.get("period_to")),
        "line_no": _number(item.get("line_no")),
        "voucher_date": _when(item.get("voucher_date")),
        "stock_group": _text(item.get("stock_group")),
        "stock_item": _text(item.get("stock_item")),
        "particulars": _text(item.get("particulars")),
        "voucher_type": _text(item.get("voucher_type")),
        "voucher_no": _text(item.get("voucher_no")),
        "inwards": _text(item.get("inwards")),
        "inward_qty": _number(first_number(item.get("inwards") or "")),
        "inward_value": _number(item.get("inward_value")),
        "outwards": _text(item.get("outwards")),
        "outward_qty": _number(first_number(item.get("outwards") or "")),
        "outward_value": _number(item.get("outward_value")),
        "closing": _text(item.get("closing")),
        "closing_qty": _number(first_number(item.get("closing") or "")),
        "closing_value": _number(item.get("closing_value")),
    }


def replace_stock_register(database: str, rows: list[dict], from_date: str, to_date: str) -> int:
    """Replace stock register lines for [from_date, to_date]."""
    if not valid_database_name(database):
        raise MysqlError("Invalid database name")
    start = parse_row_date(from_date)
    end = parse_row_date(to_date)
    if start is None or end is None:
        raise MysqlError("Invalid sync dates")
    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day) + timedelta(days=1)
    mapped = [_stock_register_row(item) for item in rows]
    placeholders = ", ".join(["%s"] * len(STOCK_REGISTER_COLUMNS))
    column_sql = ", ".join(STOCK_REGISTER_COLUMNS)
    insert_sql = f"INSERT INTO `{STOCK_REGISTER_TABLE}` ({column_sql}) VALUES ({placeholders})"

    conn = mysql_connect(database)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES[STOCK_REGISTER_TABLE])
            cur.execute(
                f"DELETE FROM `{STOCK_REGISTER_TABLE}` WHERE voucher_date >= %s AND voucher_date < %s",
                (start_dt, end_dt),
            )
            values = [[row[name] for name in STOCK_REGISTER_COLUMNS] for row in mapped]
            batch = 500
            for start_at in range(0, len(values), batch):
                cur.executemany(insert_sql, values[start_at : start_at + batch])
        conn.commit()
    except MysqlError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise MysqlError(str(exc)) from exc
    finally:
        conn.close()
    return len(mapped)


def replace_stock_summary(database: str, rows: list[dict], from_date: str, to_date: str) -> int:
    """Clear tallysync_stocksummary, then insert this pull."""
    if not valid_database_name(database):
        raise MysqlError("Invalid database name")
    if parse_row_date(from_date) is None or parse_row_date(to_date) is None:
        raise MysqlError("Invalid sync dates")
    mapped = [_stock_row(item) for item in rows]
    placeholders = ", ".join(["%s"] * len(STOCK_COLUMNS))
    column_sql = ", ".join(STOCK_COLUMNS)
    insert_sql = f"INSERT INTO `{STOCK_TABLE}` ({column_sql}) VALUES ({placeholders})"

    conn = mysql_connect(database)
    try:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES[STOCK_TABLE])
            for column, kind in (
                ("alternate_unit", "text"),
                ("conversion", "double DEFAULT NULL"),
                ("opening_alt", "double DEFAULT NULL"),
                ("inwards_alt", "double DEFAULT NULL"),
                ("outwards_alt", "double DEFAULT NULL"),
                ("closing_alt", "double DEFAULT NULL"),
            ):
                cur.execute(f"SHOW COLUMNS FROM `{STOCK_TABLE}` LIKE %s", (column,))
                if cur.fetchone() is None:
                    cur.execute(f"ALTER TABLE `{STOCK_TABLE}` ADD COLUMN `{column}` {kind}")
            cur.execute(f"DELETE FROM `{STOCK_TABLE}`")
            values = [[row[name] for name in STOCK_COLUMNS] for row in mapped]
            batch = 500
            for start_at in range(0, len(values), batch):
                cur.executemany(insert_sql, values[start_at : start_at + batch])
        conn.commit()
    except MysqlError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise MysqlError(str(exc)) from exc
    finally:
        conn.close()
    return len(mapped)


def replace_period(
    database: str,
    collection: str,
    items: list[dict],
    from_date: str,
    to_date: str,
) -> int:
    """Replace item lines for [from_date, to_date). Lines with no stock item are not written."""
    if not valid_database_name(database):
        raise MysqlError("Invalid database name")
    start = parse_row_date(from_date)
    end = parse_row_date(to_date)
    if start is None or end is None:
        raise MysqlError("Invalid sync dates")
    if collection == "sales":
        table, columns, mapper = SALES_TABLE, SALES_COLUMNS, _sales_row
    elif collection == "purchase":
        table, columns, mapper = PURCHASE_TABLE, PURCHASE_COLUMNS, _purchase_row
    else:
        raise MysqlError(f"Unknown collection: {collection}")

    start_dt = datetime(start.year, start.month, start.day)
    end_dt = datetime(end.year, end.month, end.day) + timedelta(days=1)
    items = [item for item in items if str(item.get("stock_item") or "").strip()]
    rows = [mapper(item) for item in items]
    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(columns)
    insert_sql = f"INSERT INTO `{table}` ({column_sql}) VALUES ({placeholders})"
    create_sql = CREATE_TABLES[table]

    conn = mysql_connect(database)
    try:
        with conn.cursor() as cur:
            cur.execute(create_sql)
            if collection == "sales":
                for column, kind in (
                    ("stock_group", "text"),
                    ("qty_alt", "double DEFAULT NULL"),
                    ("alternate_unit", "text"),
                    ("conversion", "double DEFAULT NULL"),
                ):
                    cur.execute(f"SHOW COLUMNS FROM `{table}` LIKE %s", (column,))
                    if cur.fetchone() is None:
                        cur.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {kind}")
                cur.execute(f"SHOW COLUMNS FROM `{table}` LIKE 'cartage'")
                cartage = cur.fetchone()
                if cartage and "double" not in str(cartage["Type"]).lower():
                    cur.execute(f"ALTER TABLE `{table}` MODIFY COLUMN `cartage` double DEFAULT NULL")
                cur.execute(
                    f"ALTER TABLE `{table}` MODIFY COLUMN `discount` double DEFAULT 0"
                )
                cur.execute(f"UPDATE `{table}` SET `discount` = 0 WHERE `discount` IS NULL")
            cur.execute(f"DELETE FROM `{table}` WHERE voucher_date >= %s AND voucher_date < %s", (start_dt, end_dt))
            values = [[row[name] for name in columns] for row in rows]
            batch = 500
            for start_at in range(0, len(values), batch):
                cur.executemany(insert_sql, values[start_at : start_at + batch])
        conn.commit()
    except MysqlError:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise MysqlError(str(exc)) from exc
    finally:
        conn.close()
    return len(rows)
