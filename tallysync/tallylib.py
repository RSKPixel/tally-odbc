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
from collections.abc import Callable, Sequence
from contextvars import ContextVar, Token
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:9000"
PING_TIMEOUT = 15
LIST_TIMEOUT = 60
OBJECT_TIMEOUT = 30
SALES_TYPE = "Sales"
SALES_CHILDOF = ("SIVENDHI BILLING", "Sales")
PURCHASE_TYPE = "Purchase"
SALES_TYPES = {
    "Sales",
    "SIVENDHI BILLING",
    "Sivendhi Bill",
    "Sivendhi BILL",
}
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
    "packing",
    "weight",
    "item_no",
    "itemno",
    "item_count",
    "discount",
    "cartage",
    "box",
    "qty_per_box",
    "gst_taxability",
]
SALES_LINE_FIELDS = [
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
PURCHASE_LINE_FIELDS = [
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
VOUCHER_DISPLAY_FIELDS = [
    "elapsed",
    "voucher_date",
    "voucher_no",
    "ledger_name",
    "broker",
    "voucher_type",
    "master_id",
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


class TallyDropped(TallyError):
    """Tally closed the HTTP connection before the export finished."""


_progress_cb: ContextVar[Callable[[str], None] | None] = ContextVar("tally_progress", default=None)


def emit_progress(message: str) -> None:
    print(message, flush=True)
    callback = _progress_cb.get()
    if callback is not None:
        callback(message)


def bind_progress(callback: Callable[[str], None]) -> Token:
    return _progress_cb.set(callback)


def reset_progress(token: Token) -> None:
    _progress_cb.reset(token)


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


def first_number(value: str) -> str:
    match = re.search(r"-?\d+(?:\.\d+)?", value or "")
    return match.group(0) if match else ""


def parse_bags_kgs(qty_text: str) -> tuple[str, str]:
    parts = parse_qty_parts(qty_text)
    return parts["qty"], parts["weight"]


def parse_qty_parts(qty_text: str) -> dict:
    text = (qty_text or "").strip()
    bags = re.search(r"([\d.]+)\s*BAGS?\s*=\s*([\d.]+)\s*KGS?", text, re.I)
    if bags:
        return {
            "qty": bags.group(1),
            "weight": bags.group(2),
            "alt_qty": bags.group(2),
            "box": "",
            "qty_per_box": "",
        }
    box_to_pcs = re.search(
        r"([\d.]+)\s*(BOX(?:ES)?|CARTONS?|PKGS?|PACKAGES?)\s*=\s*([\d.]+)\s*(NOS|PCS|NUMBERS?|PIECES?)",
        text,
        re.I,
    )
    if box_to_pcs:
        box, qty = box_to_pcs.group(1), box_to_pcs.group(3)
        return {"qty": qty, "weight": qty, "alt_qty": "", "box": box, "qty_per_box": derive_packing(box, qty)}
    pcs_to_box = re.search(
        r"([\d.]+)\s*(NOS|PCS|NUMBERS?|PIECES?)\s*=\s*([\d.]+)\s*(BOX(?:ES)?|CARTONS?|PKGS?|PACKAGES?)",
        text,
        re.I,
    )
    if pcs_to_box:
        qty, box = pcs_to_box.group(1), pcs_to_box.group(3)
        return {"qty": qty, "weight": qty, "alt_qty": "", "box": box, "qty_per_box": derive_packing(box, qty)}
    n = first_number(text)
    if n and not re.search(r"BAG|KG", text, re.I):
        return {"qty": n, "weight": n, "alt_qty": "", "box": "", "qty_per_box": ""}
    return {"qty": n, "weight": "", "alt_qty": "", "box": "", "qty_per_box": ""}


def inventory_box_count(inv: ET.Element) -> str:
    for name in (
        "BASICNUMPACKAGES",
        "NUMPACKAGES",
        "NUMBOXES",
        "NUMOFBOXES",
        "NUMBEROFPACKAGES",
        "BOXES",
        "NOOFBOXES",
        "NOOFPACKAGES",
    ):
        val = first_number(child_text(inv, name))
        if val:
            return val
    for child in inv:
        tag = local_name(child.tag).upper()
        if "NUMPACKAGE" in tag or tag in {"NUMBOXES", "NUMOFBOXES", "NOOFBOXES", "NOOFPACKAGES"}:
            val = first_number(child.text or "")
            if val:
                return val
    return inventory_udf_number(inv, "SIVENDHI_PACK", "9238")


def inventory_udf_number(inv: ET.Element, *names: str) -> str:
    want = {name.upper() for name in names}
    indexes = {name for name in names if name.isdigit()}
    for node in inv.iter():
        tag = local_name(node.tag).upper()
        if tag not in want and (node.get("INDEX") or "").strip() not in indexes:
            continue
        val = first_number(node.text or "")
        if val:
            return val
        for child in node:
            val = first_number(child.text or "")
            if val:
                return val
    return ""


def nonzero(value: str) -> str:
    text = (value or "").strip()
    try:
        if text and float(text) == 0:
            return ""
    except ValueError:
        return text
    return text


def derive_packing(qty: str, kgs: str) -> str:
    try:
        bags = float(qty)
        weight = float(kgs)
        if bags:
            packing = weight / bags
            return str(int(packing)) if packing == int(packing) else f"{packing:.4g}"
    except (TypeError, ValueError):
        return ""
    return ""


def iter_named(el: ET.Element, name: str):
    for child in el:
        if local_name(child.tag) == name:
            yield child


def post_xml(url: str, xml: str, timeout: int = 180) -> bytes:
    req = urllib.request.Request(
        url,
        data=xml.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except TimeoutError as exc:
        raise TallyError(f"Tally timed out at {url}") from exc
    except (ConnectionError, http.client.RemoteDisconnected, http.client.IncompleteRead) as exc:
        raise TallyDropped(f"Tally dropped the connection at {url}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError):
            raise TallyError(f"Tally timed out at {url}") from exc
        if isinstance(reason, (ConnectionError, http.client.RemoteDisconnected)):
            raise TallyDropped(f"Tally dropped the connection at {url}") from exc
        raise TallyError(f"Tally not reachable at {url}: {exc}") from exc


def loaded_company_info(url: str, timeout: int = 15) -> dict:
    """Loaded company plus the period currently selected in Tally (Alt+F2)."""
    xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>TallySyncCompanyInfo</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="TallySyncCompanyInfo" ISINITIALIZE="Yes">
            <TYPE>Company</TYPE>
            <NATIVEMETHOD>Name</NATIVEMETHOD>
            <NATIVEMETHOD>StartingFrom</NATIVEMETHOD>
            <NATIVEMETHOD>EndingAt</NATIVEMETHOD>
            <NATIVEMETHOD>BooksFrom</NATIVEMETHOD>
            <COMPUTE>SVFromDate: ##SVFromDate</COMPUTE>
            <COMPUTE>SVToDate: ##SVToDate</COMPUTE>
            <COMPUTE>SVCurrentDate: ##SVCurrentDate</COMPUTE>
            <COMPUTE>SVCurrentCompany: ##SVCurrentCompany</COMPUTE>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""
    root = parse_root(post_xml(url, xml, timeout=timeout))
    err = tally_status_error(root)
    if err:
        raise TallyError(err)
    companies: list[dict] = []
    current = ""
    for el in root.iter():
        if local_name(el.tag) != "COMPANY":
            continue
        name = attr(el, "NAME") or child_text(el, "NAME")
        if not name:
            continue
        if not current:
            current = child_text(el, "SVCURRENTCOMPANY")
        companies.append(
            {
                "name": name,
                "from_date": ymd(child_text(el, "SVFROMDATE")),
                "to_date": ymd(child_text(el, "SVTODATE")),
                "current_date": ymd(child_text(el, "SVCURRENTDATE")),
            }
        )
    if not companies:
        raise TallyError("No company is loaded in Tally")
    selected = next((row for row in companies if row["name"] == current), companies[0])
    return {
        "company": selected["name"],
        "companies": [row["name"] for row in companies],
        "from_date": selected["from_date"],
        "to_date": selected["to_date"],
        "current_date": selected["current_date"],
    }


def loaded_company(url: str, timeout: int = 15) -> str:
    return loaded_company_info(url, timeout=timeout)["company"]


# Explicit methods only. AllInventoryEntries.* on a year of vouchers is multi-megabyte
# and slow; FETCH * / NATIVEMETHOD * is forbidden.
LINE_NATIVEMETHODS = (
    "GUID",
    "Amount",
    "PartyGSTIN",
    "PlaceOfSupply",
    "Reference",
    "ClassName",
    "EnteredBy",
    "IsDeleted",
    "SIVENDHISALEREPVOU",
    "AllInventoryEntries.StockItemName",
    "AllInventoryEntries.BilledQty",
    "AllInventoryEntries.ActualQty",
    "AllInventoryEntries.Rate",
    "AllInventoryEntries.Amount",
    "AllInventoryEntries.GSTHSNName",
    "AllInventoryEntries.SIVENDHIVOUKGS",
    "AllInventoryEntries.SIVENDHIBRAND",
    "AllInventoryEntries.SIVENDHI_PACK",
    "AllInventoryEntries.SIVENDHI_PACK_QTY",
    "AllInventoryEntries.BatchAllocations.GodownName",
    "LedgerEntries.LedgerName",
    "LedgerEntries.Amount",
    "LedgerEntries.IsPartyLedger",
    "LedgerEntries.BillAllocations.Name",
    "AllLedgerEntries.LedgerName",
    "AllLedgerEntries.Amount",
    "AllLedgerEntries.IsPartyLedger",
    "AllLedgerEntries.BillAllocations.Name",
)


def post_native_vouchers(
    url: str,
    company: str,
    from_date: str,
    to_date: str,
    child_of: str,
    coll_name: str,
    *,
    lines: bool = False,
) -> bytes:
    # Tally ignores SVFROMDATE/SVTODATE on Vouchers:VoucherType. Inject $$Date.
    company_tag = f"        <SVCURRENTCOMPANY>{xml_escape(company)}</SVCURRENTCOMPANY>\n" if company else ""
    extra = ""
    if lines:
        extra = "\n".join(
            f"            <NATIVEMETHOD>{xml_escape(name)}</NATIVEMETHOD>" for name in LINE_NATIVEMETHODS
        )
        extra = f"\n{extra}"
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
            <NATIVEMETHOD>PartyLedgerName</NATIVEMETHOD>{extra}
          </COLLECTION>
          <SYSTEM TYPE="Formulae" NAME="TallySyncDateFilter">$Date &gt;= $$Date:"{from_date}" AND $Date &lt;= $$Date:"{to_date}"</SYSTEM>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""
    return post_xml(url, xml, timeout=LIST_TIMEOUT)


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
    # XML 1.0 forbids C0 controls except tab/LF/CR. Tally emits them raw (STATKEY) and as entities.
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
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
    original = (vtype or "").strip()
    upper = original.upper()
    if upper == "SALES" or ("SIVENDHI" in upper and "BILL" in upper):
        return original or SALES_TYPE
    if upper == "PURCHASE":
        return PURCHASE_TYPE
    return original


def type_kept(vtype: str, keep: set[str] | None) -> bool:
    if keep is None:
        return True
    vt = (vtype or "").strip()
    if vt in keep:
        return True
    return vt.upper() in {name.upper() for name in keep}


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
    if not type_kept(vtype, keep):
        return None

    master_id = child_text(v, "MASTERID").strip() or child_text(v, "UNIQUEID").strip()
    number = child_text(v, "VOUCHERNUMBER") or child_text(v, "VNO")
    party = child_text(v, "PARTYLEDGERNAME") or child_text(v, "PARTYNAME") or child_text(v, "LEDGERNAME")

    items: list[dict] = []
    for inv in iter_named_any(v, "ALLINVENTORYENTRIES.LIST", "INVENTORYENTRIES.LIST"):
        godown = ""
        for batch in iter_named(inv, "BATCHALLOCATIONS.LIST"):
            godown = child_text(batch, "GODOWNNAME") or godown
        qty_raw = child_text(inv, "BILLEDQTY") or child_text(inv, "ACTUALQTY") or child_text(inv, "QTY")
        parts = parse_qty_parts(qty_raw)
        qty = parts["qty"]
        box = nonzero(parts["box"] or inventory_box_count(inv))
        qty_per_box = nonzero(parts["qty_per_box"] or inventory_udf_number(inv, "SIVENDHI_PACK_QTY", "9239"))
        if not qty_per_box and box and qty:
            qty_per_box = derive_packing(box, qty)
        packing_kgs = nonzero(money(udf_text(inv, "SIVENDHIVOUKGS") or udf_by_index(inv, "1228")))
        if not packing_kgs and not box and parts["weight"] and re.search(r"BAG|KG", qty_raw, re.I):
            packing_kgs = parts["weight"]
        items.append(
            {
                "master_id": master_id,
                "voucher_number": number,
                "voucher_type": vtype,
                "stock_item": child_text(inv, "STOCKITEMNAME") or child_text(inv, "ITEM"),
                "hsn": child_text(inv, "GSTHSNNAME"),
                "hsn_desc": child_text(inv, "GSTHSNDESCRIPTION"),
                "qty": qty,
                "qty_alt": parts.get("alt_qty", ""),
                "weight": packing_kgs or parts["weight"],
                "rate": first_number(child_text(inv, "RATE")),
                "amount": abs_amount(money(child_text(inv, "AMOUNT") or child_text(inv, "VALUE"))),
                "godown": godown,
                "brand": udf_text(inv, "788530365", "SIVENDHIBRAND") or child_text(inv, "BRAND"),
                "packing_kgs": packing_kgs,
                "packing": derive_packing(qty, packing_kgs) if packing_kgs else "",
                "gst_taxability": child_text(inv, "GSTOVRDNTAXABILITY"),
                "box": box,
                "qty_per_box": qty_per_box,
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
    discount = ""
    cartage = ""
    for led in ledgers:
        name = (led.get("ledger_name") or "").upper()
        if "DISCOUNT" in name:
            discount = led.get("amount") or ""
        elif "CARTAGE" in name:
            cartage = led.get("amount") or ""
    count = str(len(items)) if items else ""
    for index, item in enumerate(items, start=1):
        item["item_no"] = str(index)
        item["itemno"] = str(index)
        item["item_count"] = count
        item["discount"] = discount
        item["cartage"] = cartage
        item["ledger_name"] = party
        item["broker"] = header["rep_or_broker"]
        item["voucher_date"] = header["date"]
        item["voucher_no"] = number
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
    if not type_kept(vtype, keep):
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
    # Do not FETCH * — GST.LIST/STATKEY emits XML-illegal control chars, and
    # Agro Foods UDFs (brand/packing/broker) are absent on other companies.
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
        <FETCH>Date, MasterID, GUID, VoucherNumber, VoucherTypeName, PartyLedgerName, PartyGSTIN, PlaceOfSupply, Reference, ClassName, EnteredBy, IsDeleted, Amount</FETCH>
        <FETCH>AllInventoryEntries.*, InventoryEntries.*, BatchAllocations.*</FETCH>
        <FETCH>LedgerEntries.*, AllLedgerEntries.*, BillAllocations.*</FETCH>
      </FETCHLIST>
    </DESC>
  </BODY>
</ENVELOPE>"""
    return post_xml(url, xml, timeout=OBJECT_TIMEOUT)


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
        try:
            raw = post_voucher_object(url, company, master_id)
            root = parse_root(raw)
            err = tally_status_error(root)
            if err:
                print(f"  object {master_id}: {err}")
                full_headers.append(header)
                continue
            parsed_h, parsed_i, parsed_l = collect_from_root(root, default_type, keep)
        except TallyError as exc:
            print(f"  object {master_id}: {exc}")
            full_headers.append(header)
            continue
        full_headers.append(parsed_h[0] if parsed_h else header)
        items.extend(parsed_i)
        ledgers.extend(parsed_l)
        if index == 1 or index == len(headers):
            print(f"  objects {index}/{len(headers)}")
    return full_headers, items, ledgers


def _date_spans(from_date: str, to_date: str, span_days: int = 15) -> list[tuple[str, str]]:
    start = parse_row_date(from_date)
    end = parse_row_date(to_date)
    if not start or not end or end < start:
        raise TallyError("Invalid date range")
    spans: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=span_days - 1))
        spans.append((tally_date(cursor.isoformat()), tally_date(chunk_end.isoformat())))
        cursor = chunk_end + timedelta(days=1)
    return spans


def _type_filter_formula(types: set[str]) -> str:
    parts = [f'$VoucherTypeName = "{xml_escape(name)}"' for name in sorted(types)]
    if not parts:
        raise TallyError("No voucher types to fetch")
    return " OR ".join(parts)


def post_voucher_register(url: str, from_day: str, to_day: str, type_formula: str) -> bytes:
    """Voucher Register for a date range. Day Book returns only the current date."""
    xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Voucher Register</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
        <SVFROMDATE>{xml_escape(from_day)}</SVFROMDATE>
        <SVTODATE>{xml_escape(to_day)}</SVTODATE>
        <EXPLODEFLAG>No</EXPLODEFLAG>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <REPORT NAME="Voucher Register" ISMODIFY="Yes">
            <LOCAL>Collection : Default : Add : Filter : VchTypeFilter</LOCAL>
            <LOCAL>Collection : Default : Add : Fetch : VoucherTypeName</LOCAL>
          </REPORT>
          <SYSTEM TYPE="Formulae" NAME="VchTypeFilter">{type_formula}</SYSTEM>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""
    return post_xml(url, xml, timeout=LIST_TIMEOUT)


def _register_header(el: ET.Element, default_type: str, keep_types: set[str]) -> dict | None:
    vtype = normalize_vtype(child_text(el, "VOUCHERTYPENAME") or attr(el, "VCHTYPE") or default_type)
    if not type_kept(vtype, keep_types):
        return None
    number = child_text(el, "VOUCHERNUMBER")
    master_id = child_text(el, "MASTERID").strip()
    if not number and not master_id:
        return None
    stock_lines = 0
    for inv in iter_named_any(el, "ALLINVENTORYENTRIES.LIST", "INVENTORYENTRIES.LIST"):
        if (child_text(inv, "STOCKITEMNAME") or child_text(inv, "ITEM")).strip():
            stock_lines += 1
    rep = ""
    for child in el:
        tag = local_name(child.tag).upper()
        if "SIVENDHISALEREPVOU" not in tag and "788530383" not in tag:
            continue
        rep = (child.text or "").strip()
        if not rep:
            for nested in child:
                rep = (nested.text or "").strip()
                if rep:
                    break
        if rep:
            break
    return {
        "master_id": master_id,
        "guid": child_text(el, "GUID") or attr(el, "REMOTEID"),
        "date": ymd(child_text(el, "DATE")),
        "voucher_type": vtype,
        "voucher_number": number,
        "party": child_text(el, "PARTYLEDGERNAME") or child_text(el, "PARTYNAME") or child_text(el, "LEDGERNAME"),
        "party_gstin": child_text(el, "PARTYGSTIN"),
        "place_of_supply": child_text(el, "PLACEOFSUPPLY"),
        "reference": child_text(el, "REFERENCE"),
        "class_name": child_text(el, "CLASSNAME"),
        "rep_or_broker": rep or child_text(el, "SALEREP") or child_text(el, "REPNAME"),
        "entered_by": child_text(el, "ENTEREDBY"),
        "is_deleted": child_text(el, "ISDELETED") or "No",
        "bill_amount": "",
        "raw_amount": "",
        "stock_lines": stock_lines,
    }


def _parse_register_headers(
    raw: bytes,
    frm: str,
    to: str,
    default_type: str,
    keep_types: set[str],
) -> list[dict]:
    root = parse_root(raw)
    err = tally_status_error(root)
    if err:
        raise TallyError(f"Tally error for Voucher Register {frm} .. {to}: {err}")
    found: list[dict] = []
    for el in root.iter():
        if local_name(el.tag) != "VOUCHER":
            continue
        if not (attr(el, "VCHTYPE") or child_text(el, "VOUCHERNUMBER") or child_text(el, "MASTERID")):
            continue
        header = _register_header(el, default_type, keep_types)
        if header:
            found.append(header)
    found, _items, _ledgers = filter_period(found, [], [], frm, to)
    return found


def _read_register(url: str, frm: str, to: str, formula: str) -> bytes:
    """One Voucher Register span. A dropped connection is tried once more."""
    try:
        return post_voucher_register(url, frm, to, formula)
    except TallyDropped:
        emit_progress(f"Ign {frm} .. {to} connection dropped, retrying")
        return post_voucher_register(url, frm, to, formula)


def _collect_register_span(
    url: str,
    frm: str,
    to: str,
    formula: str,
    default_type: str,
    keep_types: set[str],
    headers: list[dict],
    seen: set[str],
    label: str,
) -> None:
    try:
        raw = _read_register(url, frm, to, formula)
    except TallyDropped:
        start = parse_row_date(frm)
        end = parse_row_date(to)
        if not start or not end or start >= end:
            raise
        half = max(1, (end - start).days // 2)
        mid = start + timedelta(days=half)
        if mid >= end:
            mid = end - timedelta(days=1)
        left_to = tally_date(mid.isoformat())
        right_from = tally_date((mid + timedelta(days=1)).isoformat())
        emit_progress(f"Ign {frm} .. {to} connection dropped, splitting at {left_to}")
        _collect_register_span(url, frm, left_to, formula, default_type, keep_types, headers, seen, label)
        _collect_register_span(url, right_from, to, formula, default_type, keep_types, headers, seen, label)
        return
    found = _parse_register_headers(raw, frm, to, default_type, keep_types)
    before = len(headers)
    _take_new(headers, [], [], found, [], [], seen)
    emit_progress(f"{label}:1 {frm} .. {to} [{len(headers) - before} vouchers]")


def fetch_daybook_vouchers(
    url: str,
    from_date: str,
    to_date: str,
    keep_types: set[str],
    default_type: str,
    label: str,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Voucher headers in 15-day Voucher Register calls."""
    formula = _type_filter_formula(keep_types)
    headers: list[dict] = []
    seen: set[str] = set()
    for frm, to in _date_spans(from_date, to_date):
        _collect_register_span(url, frm, to, formula, default_type, keep_types, headers, seen, label)
    return headers, [], []


def fetch_native_vouchers(
    url: str,
    company: str,
    from_date: str,
    to_date: str,
    child_of: str | Sequence[str],
    default_type: str,
    keep_types: set[str] | None = None,
    *,
    enrich: bool = True,
    label: str = "",
) -> tuple[list[dict], list[dict], list[dict]]:
    keep = keep_types or {default_type}
    shown = label or default_type
    names = [child_of] if isinstance(child_of, str) else list(child_of)
    headers: list[dict] = []
    items: list[dict] = []
    ledgers: list[dict] = []
    seen: set[str] = set()
    last_error = ""
    for name in names:
        added = len(headers)
        try:
            if enrich and seen and not _child_has_new_vouchers(
                url, company, from_date, to_date, name, keep, default_type, seen
            ):
                emit_progress(f"Ign {name} already listed")
                continue
            raw = post_native_vouchers(
                url, company, from_date, to_date, name, "TallySyncVouchers", lines=enrich
            )
            root = parse_root(raw)
            err = tally_status_error(root)
            if err:
                raise TallyError(f"Tally error for {name}: {err}")
            found_h, found_i, found_l = collect_from_root(root, default_type, keep)
            found_h, found_i, found_l = filter_period(found_h, found_i, found_l, from_date, to_date)
            emit_progress(f"{shown}:1 {from_date} .. {to_date} [{len(found_h)} vouchers]")
            _take_new(headers, items, ledgers, found_h, found_i, found_l, seen)
        except TallyError as exc:
            emit_progress(f"Err {name}: {exc}")
            last_error = str(exc)
            if len(headers) != added:
                raise
            continue
    if not headers and last_error:
        raise TallyError(last_error)
    if enrich and headers and not items:
        emit_progress(f"  loading full objects for {len(headers)} vouchers")
        headers, items, ledgers = enrich_from_objects(url, company, headers, default_type, keep)
        emit_progress(f"  {len(headers)} vouchers, {len(items)} items, {len(ledgers)} ledgers")
    return headers, items, ledgers


def _child_has_new_vouchers(
    url: str,
    company: str,
    from_date: str,
    to_date: str,
    child_of: str,
    keep: set[str],
    default_type: str,
    seen: set[str],
) -> bool:
    raw = post_native_vouchers(url, company, from_date, to_date, child_of, "TallySyncVouchers")
    emit_progress(f"  check {len(raw):,} bytes")
    root = parse_root(raw)
    err = tally_status_error(root)
    if err:
        raise TallyError(f"Tally error for {child_of}: {err}")
    found_h, _found_i, _found_l = collect_from_root(root, default_type, keep)
    found_h, _found_i, _found_l = filter_period(found_h, _found_i, _found_l, from_date, to_date)
    return any((header["master_id"] or header["voucher_number"]) not in seen for header in found_h)


def _take_new(headers, items, ledgers, found_h, found_i, found_l, seen: set[str]) -> None:
    new_keys: set[str] = set()
    for header in found_h:
        key = header["master_id"] or header["voucher_number"]
        if not key or key in seen:
            continue
        seen.add(key)
        new_keys.add(key)
        headers.append(header)
    items.extend(row for row in found_i if (row["master_id"] or row["voucher_number"]) in new_keys)
    ledgers.extend(row for row in found_l if (row["master_id"] or row["voucher_number"]) in new_keys)


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


def month_periods(from_date: str, to_date: str) -> list[tuple[str, str]]:
    """Calendar months from `from_date` through `to_date`. The last month ends on `to_date`."""
    start = parse_row_date(from_date)
    end = parse_row_date(to_date)
    if not start or not end or end < start:
        raise TallyError("Invalid profit and loss period")
    periods: list[tuple[str, str]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        if cursor.month == 12:
            next_month = date(cursor.year + 1, 1, 1)
        else:
            next_month = date(cursor.year, cursor.month + 1, 1)
        month_end = next_month - timedelta(days=1)
        slice_start = start if cursor < start else cursor
        slice_end = end if month_end > end else month_end
        periods.append((tally_date(slice_start.isoformat()), tally_date(slice_end.isoformat())))
        cursor = next_month
    return periods


def post_profit_loss(url: str, company: str, from_date: str, to_date: str) -> bytes:
    # Group statement only. EXPLODEFLAG Yes is a second call; do not add a Period collection.
    company_tag = f"        <SVCURRENTCOMPANY>{xml_escape(company)}</SVCURRENTCOMPANY>\n" if company else ""
    xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Profit and Loss</ID>
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
    return post_xml(url, xml, timeout=LIST_TIMEOUT)


def parse_profit_loss(root: ET.Element) -> list[dict]:
    rows: list[dict] = []
    name: str | None = None
    for el in root.iter():
        tag = local_name(el.tag)
        if tag == "DSPDISPNAME":
            name = (el.text or "").strip()
            continue
        if tag != "PLAMT" or name is None:
            continue
        sub = ""
        main = ""
        for child in el:
            ctag = local_name(child.tag)
            if ctag == "PLSUBAMT":
                sub = (child.text or "").strip()
            elif ctag == "BSMAINAMT":
                main = (child.text or "").strip()
        if main:
            amount, side = main, "main"
        elif sub:
            amount, side = sub, "sub"
        else:
            amount, side = "", ""
        rows.append({"account": name, "amount": amount, "amount_side": side})
        name = None
    return rows


def fetch_profit_loss(url: str, company: str, from_date: str, to_date: str) -> list[dict]:
    raw = post_profit_loss(url, company, from_date, to_date)
    if b"Unknown Request" in raw:
        raise TallyError("Tally error for Profit and Loss: Unknown Request")
    root = parse_root(raw)
    err = tally_status_error(root)
    if err:
        raise TallyError(f"Tally error for Profit and Loss: {err}")
    rows = parse_profit_loss(root)
    period_from = ymd(from_date)
    period_to = ymd(to_date)
    for index, row in enumerate(rows, start=1):
        row["line_no"] = str(index)
        row["period_from"] = period_from
        row["period_to"] = period_to
    return rows


def post_stock_summary(url: str, company: str, from_date: str, to_date: str) -> bytes:
    # Item rows with opening, inwards, outwards, and closing. No Period collection.
    company_tag = f"        <SVCURRENTCOMPANY>{xml_escape(company)}</SVCURRENTCOMPANY>\n" if company else ""
    xml = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Data</TYPE>
    <ID>Stock Summary</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
{company_tag}        <SVFROMDATE>{from_date}</SVFROMDATE>
        <SVTODATE>{to_date}</SVTODATE>
        <ISITEMWISE>Yes</ISITEMWISE>
        <DSPSHOWOPENING>Yes</DSPSHOWOPENING>
        <DSPSHOWINWARDS>Yes</DSPSHOWINWARDS>
        <DSPSHOWOUTWARDS>Yes</DSPSHOWOUTWARDS>
        <DSPSHOWCLOSING>Yes</DSPSHOWCLOSING>
      </STATICVARIABLES>
    </DESC>
  </BODY>
</ENVELOPE>"""
    return post_xml(url, xml, timeout=LIST_TIMEOUT)


def parse_stock_summary(root: ET.Element) -> list[dict]:
    qty_tags = {
        "DSPOPQTY": "opening",
        "DSPINQTY": "inwards",
        "DSPOUTQTY": "outwards",
        "DSPCLQTY": "closing",
    }
    rate_tags = {
        "DSPOPRATE": "opening_rate",
        "DSPINRATE": "inward_rate",
        "DSPOUTRATE": "outward_rate",
        "DSPCLRATE": "closing_rate",
    }
    value_tags = {
        "DSPOPAMTA": "opening_value",
        "DSPDRAMTA": "inward_value",
        "DSPNETTCRAMTA": "outward_value",
        "DSPCLAMTA": "closing_value",
    }
    blank = {
        "stock_item": "",
        "opening": "",
        "opening_rate": "",
        "opening_value": "",
        "inwards": "",
        "inward_rate": "",
        "inward_value": "",
        "outwards": "",
        "outward_rate": "",
        "outward_value": "",
        "closing": "",
        "closing_rate": "",
        "closing_value": "",
    }
    rows: list[dict] = []
    current: dict | None = None
    for el in root.iter():
        tag = local_name(el.tag)
        if tag == "DSPDISPNAME":
            if current and current.get("stock_item"):
                rows.append(current)
            current = dict(blank)
            current["stock_item"] = (el.text or "").strip()
            continue
        if current is None:
            continue
        text = money(el.text or "")
        if tag in qty_tags:
            current[qty_tags[tag]] = (el.text or "").strip()
        elif tag in rate_tags:
            current[rate_tags[tag]] = text
        elif tag in value_tags:
            current[value_tags[tag]] = text
    if current and current.get("stock_item"):
        rows.append(current)
    return rows


def _alt_qty(qty_text: str, conversion: str, denominator: str) -> str:
    bags = first_number(qty_text)
    if not bags:
        return ""
    try:
        factor = float(conversion)
        den = float(denominator) if denominator else 1.0
    except ValueError:
        return ""
    if factor == 0 or den == 0:
        return ""
    value = float(bags) * factor / den
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}"


def fetch_stock_item_groups(url: str) -> dict[str, dict]:
    xml = """<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>Export</TALLYREQUEST>
    <TYPE>Collection</TYPE>
    <ID>TallySyncStockParents</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="TallySyncStockParents" ISINITIALIZE="Yes">
            <TYPE>Stock Item</TYPE>
            <NATIVEMETHOD>Name</NATIVEMETHOD>
            <NATIVEMETHOD>Parent</NATIVEMETHOD>
            <NATIVEMETHOD>BaseUnits</NATIVEMETHOD>
            <NATIVEMETHOD>AdditionalUnits</NATIVEMETHOD>
            <NATIVEMETHOD>Conversion</NATIVEMETHOD>
            <NATIVEMETHOD>Denominator</NATIVEMETHOD>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""
    raw = post_xml(url, xml, timeout=LIST_TIMEOUT)
    if b"Unknown Request" in raw:
        raise TallyError("Tally error for stock item groups: Unknown Request")
    root = parse_root(raw)
    err = tally_status_error(root)
    if err:
        raise TallyError(f"Tally error for stock item groups: {err}")
    groups: dict[str, dict] = {}
    for el in root.iter():
        if local_name(el.tag) != "STOCKITEM":
            continue
        name = attr(el, "NAME") or child_text(el, "NAME")
        if not name:
            continue
        unit = child_text(el, "ADDITIONALUNITS")
        if unit.lower() in {"", "not applicable"}:
            unit = ""
        groups[name] = {
            "stock_group": child_text(el, "PARENT"),
            "alternate_unit": unit,
            "conversion": child_text(el, "CONVERSION").strip(),
            "denominator": child_text(el, "DENOMINATOR").strip(),
        }
    return groups


def attach_alternate_qty(url: str, items: list[dict]) -> None:
    """Attach stock group and unit. Packing is the stock item conversion. qty_alt is the kg side of BILLEDQTY."""
    if not items:
        return
    groups = fetch_stock_item_groups(url)
    for item in items:
        master = groups.get(item.get("stock_item") or "", {})
        unit = master.get("alternate_unit", "")
        conversion = master.get("conversion", "")
        item["stock_group"] = master.get("stock_group", "")
        item["alternate_unit"] = unit
        item["conversion"] = conversion if unit else ""
        if item["conversion"]:
            item["packing"] = item["conversion"]
        item["qty_alt"] = item.get("qty_alt") or ""


def fetch_stock_summary(url: str, company: str, from_date: str, to_date: str) -> list[dict]:
    raw = post_stock_summary(url, company, from_date, to_date)
    if b"Unknown Request" in raw:
        raise TallyError("Tally error for Stock Summary: Unknown Request")
    root = parse_root(raw)
    err = tally_status_error(root)
    if err:
        raise TallyError(f"Tally error for Stock Summary: {err}")
    rows = parse_stock_summary(root)
    groups = fetch_stock_item_groups(url)
    period_from = ymd(from_date)
    period_to = ymd(to_date)
    for index, row in enumerate(rows, start=1):
        master = groups.get(row["stock_item"], {})
        conversion = master.get("conversion", "")
        denominator = master.get("denominator", "")
        row["line_no"] = str(index)
        row["stock_group"] = master.get("stock_group", "")
        row["alternate_unit"] = master.get("alternate_unit", "")
        row["conversion"] = conversion if row["alternate_unit"] else ""
        row["opening_alt"] = _alt_qty(row["opening"], conversion, denominator)
        row["inwards_alt"] = _alt_qty(row["inwards"], conversion, denominator)
        row["outwards_alt"] = _alt_qty(row["outwards"], conversion, denominator)
        row["closing_alt"] = _alt_qty(row["closing"], conversion, denominator)
        row["period_from"] = period_from
        row["period_to"] = period_to
    emit_progress(f"Stock Summary:1 {from_date} .. {to_date} [{len(rows)} lines]")
    return rows


def fetch_profit_loss_months(url: str, company: str, from_date: str, to_date: str) -> list[dict]:
    rows: list[dict] = []
    for frm, to in month_periods(from_date, to_date):
        found = fetch_profit_loss(url, company, frm, to)
        emit_progress(f"Profit and Loss:1 {frm} .. {to} [{len(found)} lines]")
        rows.extend(found)
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
    item_fields = list(ITEM_FIELDS)
    if prefix == "sales":
        item_at = item_fields.index("stock_item")
        item_fields.insert(item_at, "stock_group")
        qty_at = item_fields.index("qty") + 1
        item_fields[qty_at:qty_at] = ["qty_alt", "alternate_unit", "conversion"]
    write_csv(voucher_path, VOUCHER_FIELDS, headers)
    write_csv(items_path, item_fields, items)
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
