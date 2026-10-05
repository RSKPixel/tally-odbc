#!/usr/bin/env python3
"""Shared Tally HTTP XML helpers. CLI modules and later FastAPI import from here."""

from __future__ import annotations

import argparse
import csv
import http.client
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:9000"
SALES_TYPE = "SIVENDHI BILLING"
PURCHASE_TYPE = "Purchase"
SALES_TYPES = {SALES_TYPE}
PURCHASE_TYPES = {PURCHASE_TYPE}

VOUCHER_FIELDS = [
    "master_id",
    "guid",
    "date",
    "voucher_type",
    "voucher_number",
    "party",
    "party_gstin",
    "place_of_supply",
    "reference",
    "class_name",
    "rep_or_broker",
    "entered_by",
    "is_deleted",
    "bill_amount",
    "raw_amount",
]
ITEM_FIELDS = [
    "master_id",
    "voucher_number",
    "voucher_type",
    "stock_item",
    "hsn",
    "hsn_desc",
    "qty",
    "rate",
    "amount",
    "godown",
    "brand",
    "packing_kgs",
    "gst_taxability",
]
LEDGER_FIELDS = [
    "master_id",
    "voucher_number",
    "voucher_type",
    "ledger_name",
    "amount",
    "bill_ref",
    "is_party_ledger",
]
BILL_FIELDS = [
    "as_on",
    "party",
    "bill_ref",
    "bill_date",
    "due_date",
    "overdue_days",
    "closing",
    "outstanding",
]


class TallyError(RuntimeError):
    pass


def tally_date(value: str) -> str:
    value = value.strip()
    parsed = None
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%Y%m%d", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(value, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        raise argparse.ArgumentTypeError(f"Bad date: {value}")
    return f"{parsed.day}-{parsed.strftime('%b-%Y')}"


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def child_text(el: ET.Element | None, name: str) -> str:
    if el is None:
        return ""
    for child in el:
        if local_name(child.tag) == name:
            return (child.text or "").strip()
    return ""


def attr(el: ET.Element, name: str) -> str:
    return (el.get(name) or "").strip()


def ymd(value: str) -> str:
    value = (value or "").strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


def money(value: str) -> str:
    return (value or "").replace(",", "").strip()


def abs_amount(value: str) -> str:
    try:
        return f"{abs(float(value)):.2f}"
    except ValueError:
        return value


def iter_named(el: ET.Element, name: str):
    for child in el:
        if local_name(child.tag) == name:
            yield child


def post_xml(url: str, xml: str) -> bytes:
    req = urllib.request.Request(
        url,
        data=xml.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.read()
    except (TimeoutError, ConnectionError, http.client.RemoteDisconnected) as exc:
        raise TallyError(f"Tally timed out or dropped the connection at {url}") from exc
    except urllib.error.URLError as exc:
        raise TallyError(f"Tally not reachable at {url}: {exc}") from exc


def post_native_vouchers(
    url: str, company: str, from_date: str, to_date: str, child_of: str, coll_name: str
) -> bytes:
    # Tally ignores SVFROMDATE/SVTODATE on Vouchers:VoucherType. Inject $$Date.
    company_tag = f"        <SVCURRENTCOMPANY>{xml_escape(company)}</SVCURRENTCOMPANY>\n" if company else ""
    xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>{xml_escape(coll_name)}</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
{company_tag}        <SVCURRENTDATE>{from_date}</SVCURRENTDATE>
        <SVFROMDATE>{from_date}</SVFROMDATE>
        <SVTODATE>{to_date}</SVTODATE>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="{xml_escape(coll_name)}" ISINITIALIZE="Yes">
            <TYPE>Vouchers:VoucherType</TYPE>
            <CHILDOF>{xml_escape(child_of)}</CHILDOF>
            <BELONGSTO>Yes</BELONGSTO>
            <FILTER>TallySyncDateFilter</FILTER>
            <NATIVEMETHOD>Date</NATIVEMETHOD>
            <NATIVEMETHOD>MasterID</NATIVEMETHOD>
            <NATIVEMETHOD>VoucherNumber</NATIVEMETHOD>
            <NATIVEMETHOD>VoucherTypeName</NATIVEMETHOD>
          </COLLECTION>
          <SYSTEM TYPE="Formulae" NAME="TallySyncDateFilter">$Date &gt;= $$Date:"{from_date}" AND $Date &lt;= $$Date:"{to_date}"</SYSTEM>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""
    return post_xml(url, xml)


def post_bills_report(
    url: str, company: str, from_date: str, to_date: str, report_id: str
) -> bytes:
    # Native outstanding reports. EXPLODEFLAG No = one row per open bill.
    # As-on date is SVCURRENTDATE/SVTODATE.
    company_tag = f"        <SVCURRENTCOMPANY>{xml_escape(company)}</SVCURRENTCOMPANY>\n" if company else ""
    xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>{xml_escape(report_id)}</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
{company_tag}        <SVCURRENTDATE>{to_date}</SVCURRENTDATE>
        <SVFROMDATE>{from_date}</SVFROMDATE>
        <SVTODATE>{to_date}</SVTODATE>
        <EXPLODEFLAG>No</EXPLODEFLAG>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
    return post_xml(url, xml)


def sanitize_tally_xml(text: str) -> str:
    text = re.sub(r"&#(?:0{0,2}[0-8]|1[12]|1[4-9]|2[0-9]|3[01]);", "", text)
    text = re.sub(r"&#x0{0,2}[0-8A-Ca-c];", "", text)
    text = re.sub(r"&(?!(?:amp|lt|gt|apos|quot|#(?:\d+|x[0-9A-Fa-f]+));)", "&amp;", text)
    text = re.sub(r'(?:\s*xmlns:UDF="TallyUDF")+', "", text, count=1)
    text = re.sub(r"<ENVELOPE\b", '<ENVELOPE xmlns:UDF="TallyUDF"', text, count=1)
    return text


def parse_root(raw: bytes) -> ET.Element:
    text = sanitize_tally_xml(raw.decode("utf-8", errors="replace"))
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        dump = Path("out") / "parse-error.xml"
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(text, encoding="utf-8")
        raise TallyError(f"Tally XML parse error: {exc} (dumped {dump})") from exc


def tally_status_error(root: ET.Element) -> str:
    header = next((el for el in root.iter() if local_name(el.tag) == "HEADER"), None)
    status = child_text(header, "STATUS")
    if not status or status == "1":
        return ""
    lineerror = ""
    for el in root.iter():
        if local_name(el.tag) == "LINEERROR":
            lineerror = (el.text or "").strip()
            break
    return lineerror or f"STATUS={status}"


def udf_by_index(el: ET.Element, index: str) -> str:
    for node in el.iter():
        if (node.get("INDEX") or "").strip() != index:
            continue
        val = (node.text or "").strip()
        if val:
            return val
        for child in node:
            val = (child.text or "").strip()
            if val:
                return val
    return ""


def udf_text(el: ET.Element, *needles: str) -> str:
    upper = tuple(n.upper() for n in needles)
    for node in el.iter():
        tag = local_name(node.tag).upper()
        if any(needle in tag for needle in upper):
            val = (node.text or "").strip()
            if val:
                return val
    return ""


def normalize_vtype(vtype: str) -> str:
    upper = (vtype or "").upper().strip()
    if "SIVENDHI" in upper and "BILL" in upper:
        return SALES_TYPE
    if upper == "PURCHASE":
        return PURCHASE_TYPE
    return vtype


def iter_named_any(el: ET.Element, *names: str):
    wanted = {n.upper() for n in names}
    for child in el:
        if local_name(child.tag).upper() in wanted:
            yield child


def parse_voucher(
    v: ET.Element, default_type: str = "", keep_types: set[str] | None = None
) -> tuple[dict, list[dict], list[dict]] | None:
    keep = keep_types or (SALES_TYPES | PURCHASE_TYPES)
    vtype = normalize_vtype(
        child_text(v, "VOUCHERTYPENAME") or attr(v, "VCHTYPE") or default_type
    )
    if vtype not in keep:
        return None

    master_id = child_text(v, "MASTERID").strip() or child_text(v, "UNIQUEID").strip()
    number = child_text(v, "VOUCHERNUMBER") or child_text(v, "VNO")
    party = child_text(v, "PARTYLEDGERNAME") or child_text(v, "PARTYNAME") or child_text(v, "LEDGERNAME")

    items: list[dict] = []
    for inv in iter_named_any(v, "ALLINVENTORYENTRIES.LIST", "INVENTORYENTRIES.LIST"):
        godown = ""
        for batch in iter_named(inv, "BATCHALLOCATIONS.LIST"):
            godown = child_text(batch, "GODOWNNAME") or godown
        items.append(
            {
                "master_id": master_id,
                "voucher_number": number,
                "voucher_type": vtype,
                "stock_item": child_text(inv, "STOCKITEMNAME") or child_text(inv, "ITEM"),
                "hsn": child_text(inv, "GSTHSNNAME"),
                "hsn_desc": child_text(inv, "GSTHSNDESCRIPTION"),
                "qty": child_text(inv, "BILLEDQTY") or child_text(inv, "ACTUALQTY") or child_text(inv, "QTY"),
                "rate": child_text(inv, "RATE"),
                "amount": money(child_text(inv, "AMOUNT") or child_text(inv, "VALUE")),
                "godown": godown,
                "brand": udf_text(inv, "788530365", "SIVENDHIBRAND") or child_text(inv, "BRAND"),
                "packing_kgs": money(
                    udf_text(inv, "SIVENDHIVOUKGS") or udf_by_index(inv, "1228")
                ),
                "gst_taxability": child_text(inv, "GSTOVRDNTAXABILITY"),
            }
        )

    ledgers: list[dict] = []
    party_amt = ""
    for led in iter_named_any(v, "LEDGERENTRIES.LIST", "ALLLEDGERENTRIES.LIST"):
        amt = money(child_text(led, "AMOUNT"))
        bill_ref = ""
        for bill in iter_named(led, "BILLALLOCATIONS.LIST"):
            bill_ref = child_text(bill, "NAME") or bill_ref
        is_party = child_text(led, "ISPARTYLEDGER") == "Yes" or child_text(led, "LEDGERNAME") == party
        if is_party:
            party_amt = amt
        ledgers.append(
            {
                "master_id": master_id,
                "voucher_number": number,
                "voucher_type": vtype,
                "ledger_name": child_text(led, "LEDGERNAME"),
                "amount": amt,
                "bill_ref": bill_ref,
                "is_party_ledger": "Yes" if is_party else "No",
            }
        )

    raw_amount = money(child_text(v, "AMOUNT"))
    header = {
        "master_id": master_id,
        "guid": child_text(v, "GUID") or attr(v, "REMOTEID"),
        "date": ymd(child_text(v, "DATE")),
        "voucher_type": vtype,
        "voucher_number": number,
        "party": party,
        "party_gstin": child_text(v, "PARTYGSTIN"),
        "place_of_supply": child_text(v, "PLACEOFSUPPLY"),
        "reference": child_text(v, "REFERENCE"),
        "class_name": child_text(v, "CLASSNAME"),
        "rep_or_broker": (
            udf_text(v, "788530383", "SIVENDHISALEREPVOU")
            or child_text(v, "SALEREP")
            or child_text(v, "REPNAME")
        ),
        "entered_by": child_text(v, "ENTEREDBY"),
        "is_deleted": child_text(v, "ISDELETED") or "No",
        "bill_amount": abs_amount(party_amt or raw_amount),
        "raw_amount": raw_amount,
    }
    return header, items, ledgers


def parse_flat_line(
    el: ET.Element, default_type: str, keep_types: set[str] | None = None
) -> tuple[dict, dict] | None:
    keep = keep_types or (SALES_TYPES | PURCHASE_TYPES)
    number = child_text(el, "VNO") or child_text(el, "VOUCHERNUMBER")
    stock_item = child_text(el, "ITEM") or child_text(el, "STOCKITEM") or child_text(el, "STOCKITEMNAME")
    if not (child_text(el, "VNO") or child_text(el, "VDT") or child_text(el, "UNIQUEID")):
        return None
    if not number and not stock_item:
        return None
    vtype = normalize_vtype(child_text(el, "VTYPE") or child_text(el, "VOUCHERTYPENAME") or default_type)
    if vtype not in keep:
        return None
    master_id = child_text(el, "UNIQUEID") or child_text(el, "MASTERID")
    header = {
        "master_id": master_id,
        "guid": child_text(el, "GUID"),
        "date": ymd(child_text(el, "VDT") or child_text(el, "DATE")),
        "voucher_type": vtype,
        "voucher_number": number,
        "party": child_text(el, "LEDGERNAME") or child_text(el, "PARTYLEDGERNAME"),
        "party_gstin": child_text(el, "PARTYGSTIN"),
        "place_of_supply": child_text(el, "PLACEOFSUPPLY"),
        "reference": child_text(el, "REFERENCE"),
        "class_name": child_text(el, "CLASSNAME"),
        "rep_or_broker": child_text(el, "REPNAME") or child_text(el, "SALEREP"),
        "entered_by": child_text(el, "ENTEREDBY"),
        "is_deleted": child_text(el, "ISDELETED") or "No",
        "bill_amount": abs_amount(money(child_text(el, "VALUE") or child_text(el, "DEBENTUREVALUE") or child_text(el, "AMOUNT"))),
        "raw_amount": money(child_text(el, "VALUE") or child_text(el, "DEBENTUREVALUE") or child_text(el, "AMOUNT")),
    }
    item = {
        "master_id": master_id,
        "voucher_number": number,
        "voucher_type": vtype,
        "stock_item": stock_item,
        "hsn": child_text(el, "HSN") or child_text(el, "GSTHSNNAME"),
        "hsn_desc": "",
        "qty": child_text(el, "QTY") or child_text(el, "ALTQTY"),
        "rate": child_text(el, "RATE"),
        "amount": money(child_text(el, "VALUE") or child_text(el, "DEBENTUREVALUE") or child_text(el, "AMOUNT")),
        "godown": child_text(el, "GODOWNNAME"),
        "brand": child_text(el, "BRAND"),
        "packing_kgs": money(child_text(el, "ALTQTY") or child_text(el, "PACKING")),
        "gst_taxability": "",
    }
    return header, item


def collect_from_root(
    root: ET.Element, default_type: str, keep_types: set[str] | None = None
) -> tuple[list[dict], list[dict], list[dict]]:
    keep = keep_types if keep_types is not None else ({default_type} if default_type else None)
    headers: list[dict] = []
    items: list[dict] = []
    ledgers: list[dict] = []
    for el in root.iter():
        if local_name(el.tag) != "VOUCHER":
            continue
        if not (attr(el, "VCHTYPE") or child_text(el, "VOUCHERNUMBER") or child_text(el, "MASTERID")):
            continue
        parsed = parse_voucher(el, default_type, keep)
        if not parsed:
            continue
        header, voucher_items, voucher_ledgers = parsed
        headers.append(header)
        items.extend(voucher_items)
        ledgers.extend(voucher_ledgers)
    if headers:
        return headers, items, ledgers

    seen_headers: dict[str, dict] = {}
    for el in root.iter():
        parsed_line = parse_flat_line(el, default_type, keep)
        if not parsed_line:
            continue
        header, item = parsed_line
        key = header["master_id"] or header["voucher_number"]
        if key and key not in seen_headers:
            seen_headers[key] = header
            headers.append(header)
        if item["stock_item"]:
            items.append(item)
    return headers, items, ledgers


def parse_row_date(value: str):
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def filter_period(headers, items, ledgers, from_date: str, to_date: str):
    start = parse_row_date(from_date)
    end = parse_row_date(to_date)
    if not start or not end:
        return headers, items, ledgers
    keep_ids = set()
    kept = []
    for header in headers:
        row_date = parse_row_date(header.get("date", ""))
        if row_date and start <= row_date <= end:
            kept.append(header)
            keep_ids.add(header["master_id"] or header["voucher_number"])
    items = [row for row in items if (row["master_id"] or row["voucher_number"]) in keep_ids]
    ledgers = [row for row in ledgers if (row["master_id"] or row["voucher_number"]) in keep_ids]
    return kept, items, ledgers


def post_voucher_object(url: str, company: str, master_id: str) -> bytes:
    company_tag = f"        <SVCURRENTCOMPANY>{xml_escape(company)}</SVCURRENTCOMPANY>\n" if company else ""
    xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Object</TYPE>
    <SUBTYPE>Voucher</SUBTYPE>
    <ID TYPE="Name">ID:{xml_escape(master_id)}</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
{company_tag}      </STATICVARIABLES>
      <FETCHLIST>
        <FETCH>*</FETCH>
      </FETCHLIST>
    </DESC>
  </BODY>
</ENVELOPE>"""
    return post_xml(url, xml)


def enrich_from_objects(
    url: str, company: str, headers: list[dict], default_type: str, keep_types: set[str] | None = None
) -> tuple[list[dict], list[dict], list[dict]]:
    full_headers: list[dict] = []
    items: list[dict] = []
    ledgers: list[dict] = []
    keep = keep_types or {default_type}
    for index, header in enumerate(headers, start=1):
        master_id = header.get("master_id", "").strip()
        if not master_id:
            full_headers.append(header)
            continue
        raw = post_voucher_object(url, company, master_id)
        root = parse_root(raw)
        err = tally_status_error(root)
        if err:
            print(f"  object {master_id}: {err}")
            full_headers.append(header)
            continue
        parsed_h, parsed_i, parsed_l = collect_from_root(root, default_type, keep)
        full_headers.append(parsed_h[0] if parsed_h else header)
        items.extend(parsed_i)
        ledgers.extend(parsed_l)
        if index == 1 or index == len(headers):
            print(f"  objects {index}/{len(headers)}")
    return full_headers, items, ledgers


def fetch_native_vouchers(
    url: str,
    company: str,
    from_date: str,
    to_date: str,
    child_of: str,
    default_type: str,
    keep_types: set[str] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    keep = keep_types or {default_type}
    print(f"Native Voucher / {child_of}")
    raw = post_native_vouchers(url, company, from_date, to_date, child_of, "TallySyncVouchers")
    print(f"  list {len(raw):,} bytes")
    root = parse_root(raw)
    err = tally_status_error(root)
    if err:
        raise TallyError(f"Tally error for {child_of}: {err}")
    headers, items, ledgers = collect_from_root(root, default_type, keep)
    before = len(headers)
    headers, items, ledgers = filter_period(headers, items, ledgers, from_date, to_date)
    if before and before != len(headers):
        print(f"  {before} fetched, {len(headers)} in date range")
    else:
        print(f"  {len(headers)} vouchers")
    if headers and not items:
        print(f"  loading full objects for {len(headers)} vouchers")
        headers, items, ledgers = enrich_from_objects(url, company, headers, default_type, keep)
        print(f"  {len(headers)} vouchers, {len(items)} items, {len(ledgers)} ledgers")
    return headers, items, ledgers


def iter_data_nodes(el: ET.Element):
    for child in el:
        name = local_name(child.tag).upper()
        if name in {"HEADER", "BODY", "DESC", "DATA", "TDL", "TDLMESSAGE"}:
            yield from iter_data_nodes(child)
        else:
            yield child


def parse_bills_report(root: ET.Element, as_on: str) -> list[dict]:
    rows: list[dict] = []
    current: dict | None = None
    as_on_ymd = ymd(as_on)
    for el in iter_data_nodes(root):
        name = local_name(el.tag).upper()
        if name == "BILLFIXED":
            if current and (current.get("bill_ref") or current.get("party")):
                rows.append(current)
            current = {
                "as_on": as_on_ymd,
                "party": child_text(el, "BILLPARTY"),
                "bill_ref": child_text(el, "BILLREF"),
                "bill_date": ymd(child_text(el, "BILLDATE")),
                "due_date": "",
                "overdue_days": "",
                "closing": "",
                "outstanding": "",
            }
            continue
        if current is None:
            continue
        if name == "BILLCL":
            current["closing"] = money(el.text or "")
            current["outstanding"] = abs_amount(current["closing"])
        elif name == "BILLDUE":
            current["due_date"] = ymd((el.text or "").strip())
        elif name == "BILLOVERDUE":
            current["overdue_days"] = (el.text or "").strip()
    if current and (current.get("bill_ref") or current.get("party")):
        rows.append(current)
    return rows


def fetch_bills_report(
    url: str, company: str, from_date: str, to_date: str, report_id: str
) -> list[dict]:
    print(report_id)
    raw = post_bills_report(url, company, from_date, to_date, report_id)
    print(f"  report {len(raw):,} bytes")
    root = parse_root(raw)
    err = tally_status_error(root)
    if err:
        raise TallyError(f"Tally error for {report_id}: {err}")
    rows = parse_bills_report(root, to_date)
    print(f"  {len(rows)} open bills")
    return rows


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_voucher_csvs(
    out: Path, prefix: str, headers: list[dict], items: list[dict], ledgers: list[dict]
) -> tuple[Path, Path, Path]:
    voucher_path = out / f"{prefix}.csv"
    items_path = out / f"{prefix}_items.csv"
    ledgers_path = out / f"{prefix}_ledgers.csv"
    write_csv(voucher_path, VOUCHER_FIELDS, headers)
    write_csv(items_path, ITEM_FIELDS, items)
    write_csv(ledgers_path, LEDGER_FIELDS, ledgers)
    return voucher_path, items_path, ledgers_path


def parse_cli(description: str) -> argparse.Namespace:
    today = date.today()
    today_tally = f"{today.day}-{today.strftime('%b-%Y')}"
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--from", dest="from_date", type=tally_date, default=today_tally)
    parser.add_argument("--to", dest="to_date", type=tally_date, default=None)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--company", default="", help="Tally company name (default: currently loaded, do not switch)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    args.to_date = args.to_date or args.from_date
    args.company = args.company.strip()
    return args


def print_period(args: argparse.Namespace) -> None:
    if args.company:
        print(f"Company: {args.company}")
    else:
        print("Company: currently loaded in Tally")
    print(f"Period {args.from_date} .. {args.to_date}")


def run_cli(description: str, runner) -> None:
    args = parse_cli(description)
    print_period(args)
    try:
        runner(args.url, args.company, args.from_date, args.to_date, args.out)
    except TallyError as exc:
        sys.exit(str(exc))
