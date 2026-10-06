# Tally → CSV / MySQL sync (tally-odbc)

Hand-off notes for any agent continuing this repo. Read this before changing Tally pull scripts, the web app, or MySQL writes.

**As of 6 Oct 2026.** Working path:

- Native voucher list + per-voucher object enrich → CSV (`tallysync/`)
- Bills Receivable / Bills Payable reports → CSV only
- FastAPI + React on the Tally PC: login, loaded company, company → MySQL database, Fetch preview, Sync of **sales and purchase item lines** into `tallysync_sales` / `tallysync_purchases`

The browser never talks to Tally. Vite proxies `/api` to FastAPI. FastAPI calls Tally HTTP XML and MySQL.

## New machine

Git does **not** carry secrets or local state. Copy or clone the repo, then recreate these on the new PC.

| Path | In git? | What to do |
|---|---|---|
| `backend/.env` | No (see `backend/.env.example`) | Copy the example and fill passwords |
| `backend/app.sqlite` | No | Created on first API start. Holds Tally host/port, login profile, company→database |
| `frontend/node_modules/` | No | `npm install` in `frontend/` |
| `.venv/` | No | Create a venv and `pip install -r backend/requirements.txt` |
| `out/` | No | CSV output from the CLI |

`backend/.env` keys (all read by `backend/config.py`; empty values override the code defaults):

```text
MYSQL_HOST=homeserver
MYSQL_USER=sysadmin
MYSQL_PASSWORD=
MYSQL_DATABASE=tallysync
MYSQL_PORT=3306
SUPERUSER_PASSWORD=
SQLITE_PATH=app.sqlite
ADMIN_USER=admin
ADMIN_PASSWORD=
SESSION_SECRET=replace-with-a-long-random-string
TALLY_HOST=officehq
TALLY_PORT=9000
```

- Set `ADMIN_PASSWORD` **before the first API start**. The first run hashes it into SQLite `app_profile`. Later `.env` edits do not change the stored login. Change the password in Settings → Profile after that.
- `SESSION_SECRET` must be a long random string. Sessions die if it changes.
- `SUPERUSER_PASSWORD` is the password the Home page asks for when saving a company→database binding. If it is empty, the check uses `MYSQL_PASSWORD`.
- `MYSQL_DATABASE` is only a label in the example. Sync writes the database saved on the Home page for the loaded company, not this env value.
- `TALLY_HOST` / `TALLY_PORT` seed SQLite `app_settings` once. After that, Settings → Tally settings is the source of truth.

Setup, from the repo root (Windows, TallyPrime with **one** company open):

```text
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt
copy backend\.env.example backend\.env
# edit backend\.env

cd frontend
npm install
```

Two terminals, repo root for the API:

```text
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8005
cd frontend && npm run dev
```

- API: `http://127.0.0.1:8005` (`GET /api/health`)
- UI: `http://127.0.0.1:5175` (Vite `strictPort`; proxies `/api` to port 8005, proxy timeout 300s)
- CORS allows only `localhost:5175` and `127.0.0.1:5175`
- Sign in with `ADMIN_USER` / `ADMIN_PASSWORD`
- Home: confirm the loaded company, pick a MySQL database, Save with the superuser password, Fetch, then Sync

Tally HTTP/ODBC: `Client Server=Both`, `Enable ODBC Server=Yes`, `ServerPort=9000` (`tally.ini`). Default host in the app is `officehq:9000`. CLI default URL is still `http://127.0.0.1:9000`. If a heavy dump wedged the listener, the Tally process can still be running while `:9000` is dead. Re-enable HTTP (Gateway → F1 → Advanced Configuration) or restart Tally.

Python imports (`backend`, `tallysync`) need the **repo root** on `sys.path`. `uvicorn backend.main:app` from the repo root does that. `tallysync` is stdlib only (`urllib`, `xml.etree`, `csv`, `argparse`). The API adds FastAPI, SQLAlchemy, PyMySQL, pydantic-settings. No `requests` / `lxml`.

## Where the app left off

Logged-in routes: `/login`, `/` (Home), `/settings`.

Home:

1. `GET /api/tally/status` — `List of Companies` via the saved host/port. Shows URL, loaded company, books period. Offline is a message, not a crash.
2. More than one company loaded: Fetch and Sync stay disabled. Message: keep only one company open. The API returns 400 `Keep only one company open in Tally`. The web app never sends `SVCURRENTCOMPANY`.
3. MySQL database dropdown from `SHOW DATABASES` (system schemas hidden). Save writes SQLite `company_database` (exact Tally company name → database name) after the superuser password check. The database must already exist on the server.
4. **Fetch** lists voucher headers only (`enrich=False`). Fast. Count is vouchers. Click the count to open them. Click a voucher to load that one object’s inventory lines.
5. **Sync** is enabled only after a Fetch has results and the dropdown matches the saved database. It re-fetches with `enrich=True` and replaces item lines in MySQL for that date range. Count is lines inserted, not vouchers.

Settings:

- Tally host and port → SQLite `app_settings`
- Profile username, display name, optional new password → SQLite `app_profile` (PBKDF2-HMAC-SHA256). Header shows the display name when set.

Forms: `autoComplete="off"` on forms. `Field` / `SelectField` use `autoComplete="new-password"` plus `data-1p-ignore` and `data-lpignore`. Leave browser autofill off.

Date inputs are `type="date"` (`yyyy-mm-dd`), clamped to the loaded company’s books period, `lang="en-IN"`. The API converts them with `tally_date()` to `5-Oct-2026` (no leading zero on the day). From must be on or before To, and both must sit inside the Tally period.

Web collections today are only `sales` and `purchase`. Receivables and payables stay CLI/CSV.

## MySQL sync

Implemented in `backend/mysql_sync.py`, called from `POST /api/tally/sync`.

| Collection | Table | Grain |
|---|---|---|
| `sales` | `tallysync_sales` | one row per inventory line |
| `purchase` | `tallysync_purchases` | one row per inventory line |

`CREATE TABLE IF NOT EXISTS` runs on sync. There is no separate migration. Tables are InnoDB `utf8mb4`, surrogate `id` bigint auto-increment. **Never write `tallydata_*`.**

Replace, not upsert: `DELETE` rows whose `voucher_date` is in `[from, to]` (end is exclusive next midnight), then `INSERT` the fetched lines. A voucher with no date, or lines that fail to parse, will not be deleted by a later sync of that period.

Column mapping (first non-empty source wins):

| MySQL | Sales source | Purchase source |
|---|---|---|
| `voucher_no` | `voucher_no` or `voucher_number` | same |
| `voucher_date` | `voucher_date` or `date` | same |
| `ledger_name` | `ledger_name` or `party` | same |
| `broker` | `broker` or `rep_or_broker` | same |
| `item_count` | `item_count` | `item_count` |
| line index | `item_no` | `itemno` or `item_no` (column `itemno`) |
| `stock_item`, `brand`, `packing`, `qty`, `rate`, `amount` | same names | same names |
| `discount` | `discount` | — |
| `cartage` | text | — |
| `weight`, `box`, `qty_per_box` | — | same names |

Empty strings become SQL NULL. Numbers are `double`. `cartage` stays text.

Fetch preview columns (`VOUCHER_DISPLAY_FIELDS`): `elapsed`, `voucher_date`, `voucher_no`, `ledger_name`, `broker`, `voucher_type`, `master_id`. Item modal columns are `SALES_LINE_FIELDS` / `PURCHASE_LINE_FIELDS` in `tallysync/tallylib.py`.

## API

Session cookie via Starlette `SessionMiddleware` (`same_site=lax`). Every route except login, logout, and `/api/health` requires the session.

| Method | Path | Role |
|---|---|---|
| POST | `/api/auth/login` | username + password |
| POST | `/api/auth/logout` | clear session |
| GET | `/api/auth/me` | `{username, name}` |
| GET/PUT | `/api/settings` | Tally host/port |
| GET/PUT | `/api/profile` | username, name, optional password |
| GET | `/api/tally/status` | online, company, companies, period, url |
| GET | `/api/tally/collections` | sales, purchase |
| POST | `/api/tally/fetch` | `{collections, from_date, to_date}` headers only |
| POST | `/api/tally/voucher` | `{collection, master_id}` one object’s lines |
| POST | `/api/tally/sync` | same body as fetch; writes MySQL |
| GET | `/api/mysql/databases` | user databases |
| GET/PUT | `/api/mysql/binding` | PUT body `{database, password}` |

Fetch/sync pass `company=""` into `tallysync`, so Tally uses whatever is loaded. Per-collection Tally/MySQL failures come back inside `results[].error` with HTTP 200. A dead Tally on the status/binding/fetch entry is HTTP 502.

## Goal

Terminal Python sync from TallyPrime HTTP XML into CSV, and the same sales/purchase item lines into MySQL from the web app on the Tally PC.

- One CLI per collection so FastAPI can `from tallysync.sales import fetch` (same for purchase / receivables / payables)
- Shared HTTP/XML lives in `tallysync/tallylib.py` (`TallyError` instead of `sys.exit`, so a web process is not killed)
- `python -m tallysync` still runs all four CLIs (receivables, payables, sales, purchase) to CSV
- `fetch(..., enrich=False)` is the web list. `enrich=True` (CLI default, and Sync) loads each voucher object
- No scheduler yet — run by hand
- List screens that read MySQL back are not built. The UI reads Tally for preview, then writes MySQL

## Hard constraints — do not violate

1. **Do not use loaded custom TDL collections:** `sivendhisales`, `ODBCPURCHASES`, `sivendhipurchase`. User wants Tally’s own voucher objects, not those reports.
2. **Do not use Day Book** (`TYPE Data`, `ID Day Book`). `ODBC DAYBOOK.tcp` breaks it (`Part: DB Body`). Day Book also ignored date vars in some envelopes.
3. **Do not dump all vouchers.** Unfiltered voucher collections hang Tally and drop port 9000. Always send an actual date range in the TDL formula (see below).
4. **Do not `FETCH *` on a voucher collection or on a voucher object.** Collection `FETCH *` emptied the collection or dropped HTTP. Object `FETCH *` emits XML-illegal control chars from `GST.LIST` / `STATKEY`. Objects use the explicit `FETCHLIST` in `post_voucher_object`.
5. **Do not use `$$IsPeriodValid` as the collection filter.** It returned an empty collection.
6. **Do not switch company.** Use whatever is currently loaded. The web app never sends `SVCURRENTCOMPANY`. Keep only one company open in Tally; if more than one is loaded, fetch is blocked. `SVCURRENTCOMPANY` with the wrong name can hang `:9000`.
7. **Do not invent inline collections named `MyVouchers` / `TYPE Voucher` as the main path.** Probes of `List of Vouchers` timed out and killed `:9000`.
8. Leave TDL files in `C:\Program Files\TallyPrime\tdl` alone unless the user asks.
9. Do not raise the Tally HTTP timeout (180 s in `post_xml`, 60 s list, 30 s object, 15 s company ping) to paper over a hung Tally.

## Companies seen

| Name | Notes |
|---|---|
| `Sivendhi Agro Foods Private Limited [26-27]` | Main books used for sales/purchase checks |
| `Sivendhi Industries` | Also loaded at times; different data (box / qty_per_box UDFs) |

`--company` on the CLI is optional. Empty = currently loaded. Do not hardcode Agro Foods. The web binding key is the exact loaded company name string.

### Voucher types in scope

| Kind | Collection `CHILDOF` | Kept voucher type names |
|---|---|---|
| Sales | `SIVENDHI BILLING`, then `Sales` | `Sales`, `SIVENDHI BILLING`, `Sivendhi Bill`, `Sivendhi BILL` |
| Purchase | `Purchase` | `Purchase` |

Sales runs both child collections and dedupes on `master_id`. A missing child type is skipped; if every child fails and nothing was found, that error is raised.

Reference bills (Agro Foods, 1 Apr 2026): sales **29597** (party O.A.S. Supermarket, rep **Venket S**, packing_kgs **2500**); purchase **1596** (Guruswamy Agencies).

## How the pull works

Two-step native XML in `tallysync/tallylib.py` (`fetch_native_vouchers`).

### Step 1 — slim list (IDs in date range)

`TYPE Collection`, inline TDL, **not** a loaded TDL collection. Collection name `TallySyncVouchers`:

```
TYPE: Vouchers:VoucherType
CHILDOF: SIVENDHI BILLING   (sales also retries Sales; purchase uses Purchase)
BELONGSTO: Yes
FILTER: TallySyncDateFilter
NATIVEMETHOD: Date, MasterID, VoucherNumber, VoucherTypeName, PartyLedgerName
```

Formula (this is the only date filter Tally honored):

```
$Date >= $$Date:"5-Oct-2026" AND $Date <= $$Date:"5-Oct-2026"
```

Date strings come from `tally_date()`: **`5-Oct-2026`** (no leading zero on day). `01-Apr-2026` vs `1-Apr-2026` matters. Accepted inputs: `5-Oct-2026`, `2026-10-05`, `20261005`, `05/10/2026`.

`PartyLedgerName` is on the slim list so Fetch can show the party without loading objects.

### Step 2 — full object per voucher

Only when `enrich=True` and the list has headers but no inventory lines (the slim list never has lines).

```
TYPE: Object
SUBTYPE: Voucher
ID TYPE="Name": ID:{MASTERID}
FETCHLIST:
  Date, MasterID, GUID, VoucherNumber, VoucherTypeName, PartyLedgerName,
  PartyGSTIN, PlaceOfSupply, Reference, ClassName, EnteredBy, IsDeleted, Amount
  AllInventoryEntries.*, InventoryEntries.*, BatchAllocations.*
  LedgerEntries.*, AllLedgerEntries.*, BillAllocations.*
```

Python still runs `filter_period` as a safety net. After the `$$Date` fix, list count == kept count.

Web Fetch passes `enrich=False`. Web Sync and the CLIs pass `enrich=True`. Clicking one voucher calls `post_voucher_object` for that `master_id` only.

### Date filter — what failed vs what works

Live tests on 5 Oct 2026 against loaded company, sales `CHILDOF SIVENDHI BILLING`, slim `NATIVEMETHOD` unless noted. Raw `<VOUCHER>` tag counts can be +1 from CMPINFO; parsed rows are 37 for that day.

| Attempt | Time | Size | Vouchers / dates | Result |
|---|---|---|---|---|
| `$Date = $$Date:"5-Oct-2026"` | 0.5 s | 0.06 MB (61,535 B) | 37 kept / 1 date | **Works** |
| `$Date >= $$Date:"5-Oct-2026" AND $Date <= $$Date:"5-Oct-2026"` | 0.4 s | 0.06 MB | 37 kept / 1 date | **Works — this is what `post_native_vouchers` sends** |
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

Native voucher **objects** do include these when the explicit `FETCHLIST` returns inventory/batch nodes. Loaded TDL is not required for export.

| Meaning | TDL name | Index / other | Where | CSV column |
|---|---|---|---|---|
| Line total kg (not bag size) | `sivendhivoukgs` / `SIVENDHIVOUKGS` | `1228` | Inventory / batch on voucher | `packing_kgs` |
| Bag size 50 / 100 / 30 | `sivendhikgs` | stock-item UDF; Tally label **Packing** | Stock item master, not sales voucher | derive `packing` = kgs/qty on voucher lines |
| Brand | `sivendhibrand` | `1212` / internal `788530365` | Inventory line | `brand` |
| Rep / broker | `sivendhisalerepvou` | `1230` / internal `788530383` | Voucher header | `rep_or_broker` |
| Box count (Industries / PET) | `SIVENDHI_pack` / `SIVENDHI_PACK` | `9238` | Inventory line list | `box` |
| Pieces per box (Industries / PET) | `sivendhi_pack_qty` / `SIVENDHI_PACK_QTY` | `9239` | Inventory line list | `qty_per_box` |

**Packing:** Agro Foods bag size is `packing_kgs / bags`. Industries billed qty is `N PCS` with no dual unit; box and qty_per_box come from those UDFs (`10`×`48`=`480`, `24`×`108`=`2592`, `6`×`108`=`648` on purchase 44). Do not treat piece qty as packing (that produced packing=`1`). `BASICNUMPACKAGES` was empty on that voucher. Dual-unit `Box = Nos` still parsed if Tally sends it.

Parser: `udf_text(..., "SIVENDHIVOUKGS")` or `udf_by_index(..., "1228")`. Namespace tags look like `UDF:SIVENDHIVOUKGS`.

MySQL stores derived `packing`, not `packing_kgs`. Sales `broker` is `rep_or_broker`.

## CSV output

`out/` is gitignored. Default `--out out`. If Excel has a CSV open, write fails with PermissionError — use another `--out` or close the file.

| File | Grain | CLI |
|---|---|---|
| `sales.csv` / `sales_items.csv` / `sales_ledgers.csv` | SIVENDHI BILLING + Sales | `python -m tallysync.sales` |
| `purchases.csv` / `purchases_items.csv` / `purchases_ledgers.csv` | Purchase | `python -m tallysync.purchase` |
| `receivables.csv` | open debtor bills as on `--to` | `python -m tallysync.receivables` |
| `payables.csv` | open creditor bills as on `--to` | `python -m tallysync.payables` |

Field lists are in `tallysync/tallylib.py`. Each module exposes `fetch()` / `save()` / `run()`. Root-level `sales.py` / `purchase.py` / `receivables.py` / `payables.py` / `tallylib.py` / `tallysync.py` are gone; import from the `tallysync` package.

### Outstanding receivables / payables

Native reports **`Bills Receivable`** and **`Bills Payable`** (`TYPE Data`), not voucher collections. `EXPLODEFLAG` No. As-on date is `SVCURRENTDATE` / `SVTODATE` (`--to`). Do not use report IDs `Receivables` or `Outstanding Receivables`. Do not use `TYPE Bill` (no party name) or custom `odbc_receipts`.

Measured 5 Oct 2026 Agro Foods receivables: **601 bills**, 202 parties, 137 KB, ~1 s. `closing` is Tally’s signed amount; `outstanding` is absolute.

CLI (`--from` defaults to today, `--to` defaults to `--from`; same flags on every CLI: `--url`, `--company`, `--out`):

```text
python -m tallysync.sales --from 5-Oct-2026 --to 5-Oct-2026
python -m tallysync.purchase --from 5-Oct-2026 --to 5-Oct-2026
python -m tallysync.receivables --from 1-Apr-2026 --to 5-Oct-2026
python -m tallysync.payables --from 1-Apr-2026 --to 5-Oct-2026
python -m tallysync --from 5-Oct-2026 --to 5-Oct-2026
```

## Performance (measured 5 Oct 2026, Agro Foods / loaded company)

Before date fix, **every** sales run listed all **2533** bills (58.6 MB, ~19 s) then object-loaded only the filtered IDs.

After `$$Date` + slim `NATIVEMETHOD` (sales objects ~0.11 s each; list stayed under 1 MB):

| Period | Dates | Sales vch | Items | Ledgers | List | List time | Object time | Sales total | Was (year dump) |
|---|---|---|---|---|---|---|---|---|---|
| 1 day | 5 Oct | 37 | 58 | 81 | 0.06 MB | 0.6 s | 4.2 s | **4.8 s** | 25.3 s |
| 10 days | 26 Sep – 5 Oct | 166 | 227 | 370 | 0.26 MB | 0.6 s | 18.4 s | **19.0 s** | 48.7 s |
| 30 days | 6 Sep – 5 Oct | 462 | 637 | 1039 | 0.74 MB | 0.5 s | 52.2 s | **52.8 s** | 66.3 s |

Purchase on the same windows: 0 / 4 / 38 vouchers, **0.1 s / 0.4 s / 2.9 s**. Combined sales+purchase ≈ **5 s / 19 s / 56 s**.

Do not re-introduce `NATIVEMETHOD *` on the list. Object POSTs are the remaining cost. Web Fetch skips them on purpose.

## Tally collections that are safe vs not

Safe master lists (no extra TDL): `List of Companies`, `List of Ledgers`, `List of Groups`, `List of StockItems`, `List of Godowns`, `List of Voucher Types`, `List of Cost Centres`.

There is **no** built-in `List of Vouchers`. Vouchers = native `Vouchers:VoucherType` + object, or Day Book (broken here).

Local TDL (loaded, **do not query as collections**):

- `sivendhi_correction_27_03_25.tdl` — defines `sivendhisales`, `ODBCPURCHASES`, packing compute
- `ODBC DAYBOOK.tcp` — breaks Day Book `Part: DB Body`

Old dumps under `out/` (`daybook.raw.xml` ~95 MB, `purchases.raw.xml`) came from those TDL collections. Ignore them as the product path.

## Pitfalls

- **Port 9000 drop:** unfiltered voucher collection, `FETCH *` on a collection, huge Day Book / TDL dump. Ping `List of Companies` with a 15 s timeout before a long pull.
- **Ask-mode / sandbox** cannot POST to Tally; needs a real local Tally with company open.
- Diagnostic scripts (`time_sales_pulls.py`, `try_date_filters.py`, `measure_1day.py`, `check_stock_udf.py`) lived in `%TEMP%`, not this repo.
- `out_sync/` was a one-off when `out\voucher_items.csv` was locked.
- Sync deletes by `voucher_date` then inserts. Running Sync on an empty Fetch result still deletes that period if Tally returns no lines.
- Company→database lives in SQLite on this PC. A new machine must Save the binding again.
- Profile password lives in SQLite. A new machine uses `ADMIN_PASSWORD` only until the first start creates `app_profile`.

## Next work (not done)

1. Receivables / payables MySQL upsert. They are CSV-only. Do not add them to the Home checkboxes unless asked.
2. Optional stock-item join for `sivendhikgs` if voucher UDF / bags=kgs derive is missing on a company.
3. Scheduler (Task Scheduler, 1–5 min, today + yesterday) only after MySQL is stable.
4. Screens that **read** `tallysync_sales` / `tallysync_purchases`. Home still previews from Tally, not from MySQL.
5. Do not expand voucher types, add TDL collections, or fetch stock-item masters on every sync unless asked.

## Code map

| Path | Role |
|---|---|
| `tallysync/tallylib.py` | HTTP POST, XML sanitize/parse, voucher list+object, bills reports, `loaded_company_info`, `TallyError`, field lists |
| `tallysync/sales.py` | `fetch()` SIVENDHI BILLING + Sales → `out/sales*.csv` |
| `tallysync/purchase.py` | `fetch()` Purchase → `out/purchases*.csv` |
| `tallysync/receivables.py` | `fetch()` Bills Receivable → `out/receivables.csv` |
| `tallysync/payables.py` | `fetch()` Bills Payable → `out/payables.csv` |
| `tallysync/__main__.py` | `python -m tallysync` runs all four CLIs |
| `backend/main.py` | FastAPI app, session, CORS, routers |
| `backend/config.py` | `backend/.env` |
| `backend/db.py` | SQLite engine, `backend/app.sqlite` |
| `backend/models.py` | `app_settings`, `app_profile`, `company_database` |
| `backend/auth.py` | login / logout / me |
| `backend/security.py` | password hash |
| `backend/settings.py` | Tally host/port |
| `backend/profile.py` | username, name, password |
| `backend/tally_status.py` | `GET /api/tally/status` |
| `backend/tally_fetch.py` | collections, fetch, voucher, sync |
| `backend/mysql.py` | PyMySQL connect, `SHOW DATABASES`, superuser check |
| `backend/mysql_binding.py` | company → database |
| `backend/mysql_sync.py` | create/replace `tallysync_sales` and `tallysync_purchases` |
| `frontend/` | Vite React Tailwind. Pages: `Login`, `Landing`, `Settings`. `FetchCard` + `RecordsModal` |
