#!/usr/bin/env python3
"""Pull Tally native Voucher objects (sales + purchase) to CSV. Later: same rows -> MySQL."""

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
SALES_TYPES = {"SIVENDHI BILLING"}
PURCHASE_TYPES = {"Purchase"}
KEEP_TYPES = SALES_TYPES | PURCHASE_TYPES

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
    if len(value) == 8 and value.isdigit():
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
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
    except (TimeoutError, ConnectionError, http.client.RemoteDisconnected):
        sys.exit(f"Tally timed out or dropped the connection at {url}")
    except urllib.error.URLError as exc:
        sys.exit(f"Tally not reachable at {url}: {exc}")


def post_native_vouchers(
    url: str, company: str, from_date: str, to_date: str, child_of: str, coll_name: str
) -> bytes:
    # Tally ignores SVFROMDATE/SVTODATE on Vouchers:VoucherType. A full-year
    # NATIVEMETHOD=* list was 58.6 MB / 2533 bills and blocked the HTTP server.
    # Inject the real range with $$Date:"D-Mon-YYYY" and keep the list slim.
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


def sanitize_tally_xml(text: str) -> str:
    # Tally emits control-char entities (e.g. &#4;) which are invalid in XML 1.0.
    text = re.sub(r"&#(?:0{0,2}[0-8]|1[12]|1[4-9]|2[0-9]|3[01]);", "", text)
    text = re.sub(r"&#x0{0,2}[0-8A-Ca-c];", "", text)
    text = re.sub(r"&(?!(?:amp|lt|gt|apos|quot|#(?:\d+|x[0-9A-Fa-f]+));)", "&amp;", text)
    text = re.sub(r'(?:\s*xmlns:UDF="TallyUDF")+', "", text, count=1)
    text = re.sub(r"<ENVELOPE\b", '<ENVELOPE xmlns:UDF="TallyUDF"', text, count=1)
    return text


def parse_root(raw: bytes) -> ET.Element:
    text = sanitize_tally_xml(raw.decode("utf-8", errors="replace"))
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        dump = Path("out") / "parse-error.xml"
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(text, encoding="utf-8")
        sys.exit(f"Tally XML parse error: {exc} (dumped {dump})")
    return root


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
        return "SIVENDHI BILLING"
    if upper == "PURCHASE":
        return "Purchase"
    return vtype


def iter_named_any(el: ET.Element, *names: str):
    wanted = {n.upper() for n in names}
    for child in el:
        if local_name(child.tag).upper() in wanted:
            yield child


def parse_voucher(v: ET.Element, default_type: str = "") -> tuple[dict, list[dict], list[dict]] | None:
    vtype = normalize_vtype(
        child_text(v, "VOUCHERTYPENAME") or attr(v, "VCHTYPE") or default_type
    )
    if vtype not in KEEP_TYPES:
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


def parse_flat_line(el: ET.Element, default_type: str) -> tuple[dict, dict] | None:
    number = child_text(el, "VNO") or child_text(el, "VOUCHERNUMBER")
    stock_item = child_text(el, "ITEM") or child_text(el, "STOCKITEM") or child_text(el, "STOCKITEMNAME")
    if not (child_text(el, "VNO") or child_text(el, "VDT") or child_text(el, "UNIQUEID")):
        return None
    if not number and not stock_item:
        return None
    vtype = normalize_vtype(child_text(el, "VTYPE") or child_text(el, "VOUCHERTYPENAME") or default_type)
    if vtype not in KEEP_TYPES:
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


def collect_from_root(root: ET.Element, default_type: str) -> tuple[list[dict], list[dict], list[dict]]:
    headers: list[dict] = []
    items: list[dict] = []
    ledgers: list[dict] = []
    for el in root.iter():
        if local_name(el.tag) != "VOUCHER":
            continue
        if not (attr(el, "VCHTYPE") or child_text(el, "VOUCHERNUMBER") or child_text(el, "MASTERID")):
            continue
        parsed = parse_voucher(el, default_type)
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
        parsed_line = parse_flat_line(el, default_type)
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
    url: str, company: str, headers: list[dict], default_type: str
) -> tuple[list[dict], list[dict], list[dict]]:
    full_headers: list[dict] = []
    items: list[dict] = []
    ledgers: list[dict] = []
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
        parsed_h, parsed_i, parsed_l = collect_from_root(root, default_type)
        full_headers.append(parsed_h[0] if parsed_h else header)
        items.extend(parsed_i)
        ledgers.extend(parsed_l)
        if index == 1 or index == len(headers):
            print(f"  objects {index}/{len(headers)}")
    return full_headers, items, ledgers


def fetch_native_vouchers(
    url: str, company: str, from_date: str, to_date: str, child_of: str, default_type: str
) -> tuple[list[dict], list[dict], list[dict]]:
    coll_name = "TallySyncVouchers"
    print(f"Native Voucher / {child_of}")
    raw = post_native_vouchers(url, company, from_date, to_date, child_of, coll_name)
    print(f"  list {len(raw):,} bytes")
    root = parse_root(raw)
    err = tally_status_error(root)
    if err:
        sys.exit(f"Tally error for {child_of}: {err}")
    headers, items, ledgers = collect_from_root(root, default_type)
    before = len(headers)
    headers, items, ledgers = filter_period(headers, items, ledgers, from_date, to_date)
    if before and before != len(headers):
        print(f"  {before} fetched, {len(headers)} in date range")
    else:
        print(f"  {len(headers)} vouchers")
    if headers and not items:
        print(f"  loading full objects for {len(headers)} vouchers")
        headers, items, ledgers = enrich_from_objects(url, company, headers, default_type)
        print(f"  {len(headers)} vouchers, {len(items)} items, {len(ledgers)} ledgers")
    return headers, items, ledgers


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    today = date.today()
    today_tally = f"{today.day}-{today.strftime('%b-%Y')}"
    parser = argparse.ArgumentParser(description="Tally native Voucher (sales + purchase) → CSV")
    parser.add_argument("--from", dest="from_date", type=tally_date, default=today_tally)
    parser.add_argument("--to", dest="to_date", type=tally_date, default=None)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--company", default="", help="Tally company name (default: currently loaded, do not switch)")
    parser.add_argument("--out", type=Path, default=Path("out"))
    args = parser.parse_args()
    to_date = args.to_date or args.from_date
    company = args.company.strip()
    if company:
        print(f"Company: {company}")
    else:
        print("Company: currently loaded in Tally")
    print(f"Period {args.from_date} .. {to_date}")

    sales_h, sales_i, sales_l = fetch_native_vouchers(
        args.url, company, args.from_date, to_date, "SIVENDHI BILLING", "SIVENDHI BILLING"
    )
    purch_h, purch_i, purch_l = fetch_native_vouchers(
        args.url, company, args.from_date, to_date, "Purchase", "Purchase"
    )
    headers = sales_h + purch_h
    items = sales_i + purch_i
    ledgers = sales_l + purch_l

    write_csv(args.out / "vouchers.csv", VOUCHER_FIELDS, headers)
    write_csv(args.out / "voucher_items.csv", ITEM_FIELDS, items)
    write_csv(args.out / "voucher_ledgers.csv", LEDGER_FIELDS, ledgers)

    sales = sum(1 for row in headers if row["voucher_type"] in SALES_TYPES)
    purchases = sum(1 for row in headers if row["voucher_type"] in PURCHASE_TYPES)
    print(f"Saved {len(headers)} vouchers ({sales} sales, {purchases} purchase)")
    print(f"  {args.out / 'vouchers.csv'}")
    print(f"  {args.out / 'voucher_items.csv'}")
    print(f"  {args.out / 'voucher_ledgers.csv'}")


if __name__ == "__main__":
    main()
