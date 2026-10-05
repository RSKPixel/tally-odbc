# Tally → CSV sync (tally-odbc)

Hand-off notes for any agent continuing this repo. Read this before changing Tally pull scripts or talking to Tally.

**As of 5 Oct 2026.** Working path: native voucher list + per-voucher object enrich, plus Bills Receivable / Bills Payable reports → CSV. MySQL is next, not started.

## Goal

Terminal Python sync from TallyPrime HTTP XML (`localhost:9000`) into CSV first, then the same rows into MySQL.

- One CLI per collection so FastAPI can `from sales import fetch` (and the same for purchase / receivables / payables)
- Shared HTTP/XML lives in `tallylib.py` (`TallyError` instead of `sys.exit`, so a web process is not killed)
- `python tallysync.py` still runs all four
- No scheduler yet — run by hand
- Stdlib only (`urllib`, `xml.etree`, `csv`, `argparse`). No `requests` / `lxml` unless asked
- Later UI (FastAPI + React) must **read MySQL** (or call `fetch()` on the Tally PC), never call Tally from the browser

## Hard constraints — do not violate

1. **Do not use loaded custom TDL collections:** `sivendhisales`, `ODBCPURCHASES`, `sivendhipurchase`. User wants Tally’s own voucher objects, not those reports.
2. **Do not use Day Book** (`TYPE Data`, `ID Day Book`). `ODBC DAYBOOK.tcp` breaks it (`Part: DB Body`). Day Book also ignored date vars in some envelopes.
3. **Do not dump all vouchers.** Unfiltered voucher collections hang Tally and drop port 9000. Always send an actual date range in the TDL formula (see below).
4. **Do not `FETCH *` on a voucher collection.** That emptied the collection or dropped the HTTP connection.
5. **Do not use `$$IsPeriodValid` as the collection filter.** It returned an empty collection.
6. **Do not switch company** unless the user asks. Default is whatever is currently loaded. `SVCURRENTCOMPANY` with the wrong name fails the request.
7. **Do not invent inline collections named `MyVouchers` / `TYPE Voucher` as the main path.** Probes of `List of Vouchers` timed out and killed `:9000`.
8. Leave TDL files in `C:\Program Files\TallyPrime\tdl` alone unless the user asks.

## Environment

- Windows, TallyPrime, company **must be open**
- HTTP/ODBC: `Client Server=Both`, `Enable ODBC Server=Yes`, `ServerPort=9000` (`tally.ini`)
- URL: `http://127.0.0.1:9000`
- If a heavy dump wedged the listener: Tally process still runs but `:9000` is dead. User re-enables HTTP (Gateway → F1 → Advanced Configuration) or restarts Tally.

### Companies seen

| Name | Notes |
|---|---|
| `Sivendhi Agro Foods Private Limited [26-27]` | Main books used for sales/purchase checks |
| `Sivendhi Industries` | Also loaded at times; different data |

`--company` is optional. Empty = currently loaded. Do not hardcode Agro Foods.

### Voucher types in scope

| Kind | Tally voucher type name | Collection `CHILDOF` |
|---|---|---|
| Sales | `SIVENDHI BILLING` | `SIVENDHI BILLING` |
| Purchase | `Purchase` | `Purchase` |

Reference bills (Agro Foods, 1 Apr 2026): sales **29597** (party O.A.S. Supermarket, rep **Venket S**, packing_kgs **2500**); purchase **1596** (Guruswamy Agencies).

## How the pull works

Two-step native XML. Implemented in `tallysync.py`.

### Step 1 — slim list (IDs in date range)

`TYPE Collection`, inline TDL, **not** a loaded TDL collection:

```
TYPE: Vouchers:VoucherType
CHILDOF: SIVENDHI BILLING   (or Purchase)
BELONGSTO: Yes
FILTER: TallySyncDateFilter
NATIVEMETHOD: Date, MasterID, VoucherNumber, VoucherTypeName
```

Formula (this is the only date filter Tally honored):

```
$Date >= $$Date:"5-Oct-2026" AND $Date <= $$Date:"5-Oct-2026"
```

Date strings come from `tally_date()`: **`5-Oct-2026`** (no leading zero on day). `01-Apr-2026` vs `1-Apr-2026` matters.

### Step 2 — full object per voucher

```
TYPE: Object
SUBTYPE: Voucher
ID TYPE="Name": ID:{MASTERID}
FETCH: *
```

List XML has no inventory lines, so `fetch_native_vouchers` always enriches when headers exist and items are empty.

Python still runs `filter_period` as a safety net. After the `$$Date` fix, list count == kept count.

### Date filter — what failed vs what works

Live tests on 5 Oct 2026 against loaded company, sales `CHILDOF SIVENDHI BILLING`, slim `NATIVEMETHOD` unless noted. Raw `<VOUCHER>` tag counts can be +1 from CMPINFO; parsed rows are 37 for that day.

| Attempt | Time | Size | Vouchers / dates | Result |
|---|---|---|---|---|
| `$Date = $$Date:"5-Oct-2026"` | 0.5 s | 0.06 MB (61,535 B) | 37 kept / 1 date | **Works** |
| `$Date >= $$Date:"5-Oct-2026" AND $Date <= $$Date:"5-Oct-2026"` | 0.4 s | 0.06 MB | 37 kept / 1 date | **Works — this is what `tallysync.py` sends** |
| `TYPE Voucher` + hardcoded `$$Date` (type+date in filter) | 1.3 s | 0.06 MB | 37 kept / 1 date | Works, slightly slower; not the main path |
| `SVFROMDATE TYPE="Date">20261005` + `$Date >= ##SVFromDate` | 0.7 s | 3.96 MB (4,149,123 B) | 2534 / 160 dates (1 Apr–5 Oct) | **Ignored** |
| Slim fetch, no date filter | 0.7 s | 3.96 MB | 2534 / 160 dates | Same full-year list |
| `<SVFROMDATE>5-Oct-2026</SVFROMDATE>` + `##SVFromDate` + `NATIVEMETHOD *` | ~19 s | **58.6 MB** | 2533 / 160 dates | Ignored; **blocked Tally** |
| `$$IsPeriodValid` | — | empty | 0 | Do not use |
| `FETCH *` on voucher collection | — | — | empty / connection drop | Do not use |

`SVFROMDATE` / `SVTODATE` / `SVCURRENTDATE` are still sent in STATICVARIABLES but Tally does not apply them to this voucher collection. **Always interpolate the actual from/to into the SYSTEM Formulae with `$$Date:"…"`.**

### XML sanitizer (required)

Tally XML is not always well-formed:

- Control-char entities like `&#4;` (XML 1.0 illegal)
- Bare `&` in names
- Unbound `UDF:` prefix / duplicate `xmlns:UDF="TallyUDF"`

`sanitize_tally_xml()` strips illegal numeric entities, escapes stray `&`, and injects one `xmlns:UDF` on `<ENVELOPE>`. Parse failures dump to `out/parse-error.xml`.

Count of `<VOUCHER>` tags can be off-by-one vs real vouchers because CMPINFO also has `<VOUCHER>n</VOUCHER>`. Trust parsed `MASTERID` rows, not a raw tag count.

## Custom fields (UDFs)

Native voucher **objects** do include these. Loaded TDL is not required for export.

| Meaning | TDL name | Index / other | Where | CSV column |
|---|---|---|---|---|
| Line total kg (not bag size) | `sivendhivoukgs` / `SIVENDHIVOUKGS` | `1228` | Inventory / batch on voucher | `packing_kgs` |
| Bag size 50 / 100 / 30 | `sivendhikgs` | stock-item UDF; Tally label **Packing** | Stock item master, not sales voucher | not joined yet |
| Brand | `sivendhibrand` | `1212` / internal `788530365` | Inventory line | `brand` |
| Rep / broker | `sivendhisalerepvou` | `1230` / internal `788530383` | Voucher header | `rep_or_broker` |

**Packing:** sales can derive bag size as `packing_kgs / bags` (qty) so a stock-item join is not required. That derive is **not implemented** yet. Purchase ODBC used to expose item packing as `PACKING`; native purchase object path should be checked when wiring packing.

Parser: `udf_text(..., "SIVENDHIVOUKGS")` or `udf_by_index(..., "1228")`. Namespace tags look like `UDF:SIVENDHIVOUKGS`.

## CSV output

`out/` is gitignored. Default `--out out`. If Excel has a CSV open, write fails with PermissionError — use another `--out` or close the file.

| File | Grain | CLI |
|---|---|---|
| `sales.csv` / `sales_items.csv` / `sales_ledgers.csv` | SIVENDHI BILLING | `python sales.py` |
| `purchases.csv` / `purchases_items.csv` / `purchases_ledgers.csv` | Purchase | `python purchase.py` |
| `receivables.csv` | open debtor bills as on `--to` | `python receivables.py` |
| `payables.csv` | open creditor bills as on `--to` | `python payables.py` |

Field lists are in `tallylib.py`. Each module exposes `fetch()` / `save()` / `run()` for FastAPI.

### Outstanding receivables / payables

Native reports **`Bills Receivable`** and **`Bills Payable`** (`TYPE Data`), not voucher collections. `EXPLODEFLAG` No. As-on date is `SVCURRENTDATE` / `SVTODATE` (`--to`). Do not use report IDs `Receivables` or `Outstanding Receivables`. Do not use `TYPE Bill` (no party name) or custom `odbc_receipts`.

Measured 5 Oct 2026 Agro Foods receivables: **601 bills**, 202 parties, 137 KB, ~1 s. `closing` is Tally’s signed amount; `outstanding` is absolute.

CLI:

```text
python sales.py --from 5-Oct-2026 --to 5-Oct-2026
python purchase.py --from 5-Oct-2026 --to 5-Oct-2026
python receivables.py --from 1-Apr-2026 --to 5-Oct-2026
python payables.py --from 1-Apr-2026 --to 5-Oct-2026
python tallysync.py --from 5-Oct-2026 --to 5-Oct-2026
```

`--from` defaults to today. `--to` defaults to `--from`. Date args accept `5-Oct-2026`, `2026-10-05`, `20261005`, `05/10/2026`.

Same flags on every CLI: `--url`, `--company`, `--out`.

## Performance (measured 5 Oct 2026, Agro Foods / loaded company)

Before date fix, **every** sales run listed all **2533** bills (58.6 MB, ~19 s) then object-loaded only the filtered IDs.

After `$$Date` + slim `NATIVEMETHOD` (sales objects ~0.11 s each; list stayed under 1 MB):

| Period | Dates | Sales vch | Items | Ledgers | List | List time | Object time | Sales total | Was (year dump) |
|---|---|---|---|---|---|---|---|---|---|
| 1 day | 5 Oct | 37 | 58 | 81 | 0.06 MB | 0.6 s | 4.2 s | **4.8 s** | 25.3 s |
| 10 days | 26 Sep – 5 Oct | 166 | 227 | 370 | 0.26 MB | 0.6 s | 18.4 s | **19.0 s** | 48.7 s |
| 30 days | 6 Sep – 5 Oct | 462 | 637 | 1039 | 0.74 MB | 0.5 s | 52.2 s | **52.8 s** | 66.3 s |

Purchase on the same windows: 0 / 4 / 38 vouchers, **0.1 s / 0.4 s / 2.9 s**. Combined sales+purchase ≈ **5 s / 19 s / 56 s**.

Do not re-introduce `NATIVEMETHOD *` on the list. Object POSTs are the remaining cost.

## Tally collections that are safe vs not

Safe master lists (no extra TDL): `List of Companies`, `List of Ledgers`, `List of Groups`, `List of StockItems`, `List of Godowns`, `List of Voucher Types`, `List of Cost Centres`.

There is **no** built-in `List of Vouchers`. Vouchers = native `Vouchers:VoucherType` + object, or Day Book (broken here).

Local TDL (loaded, **do not query as collections**):

- `sivendhi_correction_27_03_25.tdl` — defines `sivendhisales`, `ODBCPURCHASES`, packing compute
- `ODBC DAYBOOK.tcp` — breaks Day Book `Part: DB Body`

Old dumps under `out/` (`daybook.raw.xml` ~95 MB, `purchases.raw.xml`) came from those TDL collections. Ignore them as the product path.

## Pitfalls

- **Port 9000 drop:** unfiltered voucher collection, `FETCH` on collection, huge Day Book / TDL dump. Ping `List of Companies` with a 15 s timeout before a long pull.
- **HTTP timeout** in `post_xml` is 180 s. Do not raise it to paper over a hung Tally.
- **Ask-mode / sandbox** cannot POST to Tally; needs a real local Tally with company open.
- Diagnostic scripts (`time_sales_pulls.py`, `try_date_filters.py`, `measure_1day.py`, `check_stock_udf.py`) lived in `%TEMP%`, not this repo.
- `out_sync/` was a one-off when `out\voucher_items.csv` was locked.

## Next work (not done)

1. **MySQL upsert** per collection; idempotent on `master_id` (bills: party + bill_ref + as_on). Run on the Tally PC.
2. Optional derive **packing** = `packing_kgs / qty` on sales lines; confirm purchase packing from native object / stock item `sivendhikgs`.
3. Scheduler (Task Scheduler, 1–5 min, today + yesterday) only after MySQL is stable.
4. FastAPI/React: import `fetch()` from `sales` / `purchase` / `receivables` / `payables`; UI should still read MySQL, not Tally, on every page load.

Do not expand voucher types, add TDL collections, or fetch stock-item masters on every sync unless asked.

## Code map

| File | Role |
|---|---|
| `tallylib.py` | HTTP POST, XML sanitize/parse, voucher list+object, bills reports, CSV, `TallyError`, shared CLI flags |
| `sales.py` | `fetch()` SIVENDHI BILLING → `out/sales*.csv` |
| `purchase.py` | `fetch()` Purchase → `out/purchases*.csv` |
| `receivables.py` | `fetch()` Bills Receivable → `out/receivables.csv` |
| `payables.py` | `fetch()` Bills Payable → `out/payables.csv` |
| `tallysync.py` | Runs all four |
