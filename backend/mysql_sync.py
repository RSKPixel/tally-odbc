from __future__ import annotations

from datetime import datetime, timedelta

from backend.mysql import MysqlError, mysql_connect, valid_database_name
from tallysync.tallylib import parse_row_date

SALES_TABLE = "tallysync_sales"
PURCHASE_TABLE = "tallysync_purchases"
PNL_TABLE = "tallysync_pnl"
STOCK_TABLE = "tallysync_stocksummary"
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
}


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
