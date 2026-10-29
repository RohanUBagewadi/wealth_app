# Wealth — private finance workspace

A responsive, local-first personal finance app for laptop and mobile browsers. It supports manual entries, wallets, transfers, budgets, categories, reports, reviewed CSV/PDF imports, CSV export, and passphrase-encrypted backup files.

## Run locally

1. Create/activate the project environment if needed: `python3 -m venv .venv`.
2. Install the listed packages: `.venv/bin/python -m pip install -r requirements.txt`.
3. Start the server: `.venv/bin/python main.py`.
4. Open `http://127.0.0.1:8000`.

The server refuses non-loopback binding and only accepts requests addressed to its local host. Keep it on this computer; it has no user authentication and is not suitable for LAN or public hosting. By default, its SQLite data is stored under `instance/`. Set `WEALTH_APP_DATA_DIR` to choose a different private local folder before starting it.

## Data and privacy

- Wallets, transactions, categories, and budgets are stored in a local SQLite database. The database is **not encrypted at rest** by this prototype; the containing directory is restricted to the current user where the operating system supports those permissions.
- The app sends no analytics, telemetry, bank requests, or external font/icon requests. The server does not log request paths or payloads.
- The service worker caches the app shell and same-origin static GET assets; it bypasses `/api/` responses. It does not queue or save finance changes offline.
- Money is persisted as integer minor units. Wallets in different currencies are displayed separately and never added together.
- Transactions are manual or explicitly accepted from a staged import. No bank connection, scraping, automatic extraction, or OCR exists.

## Imports and exports

CSV imports support comma (the default) and semicolon delimiters. Select the delimiter in Import & export before choosing the file; the app uses that choice and does not guess or fall back to another delimiter. The required headers are `transaction_date` (or its alias `date`) and `amount`. Optional headers are `type`, `currency`, `wallet`, `category`, `description`, and `notes`; missing or unsupported types and unmapped non-empty categories are flagged and must be resolved in review before saving. Valid rows support `income` or `expense`, ISO dates (`YYYY-MM-DD`), and positive decimal amounts using a period as the decimal separator. Localized decimal/thousands separators and currency symbols are not inferred. UTF-8 BOMs are accepted, malformed UTF-8 and quoting are rejected, duplicate headers are rejected, and file and row counts are bounded. Rows are staged for correction and explicit confirmation before ledger changes. PDF text parsing is local and best-effort, supports selectable text only, and stages only rows matching its narrow date/description/amount pattern. Other PDF lines may be omitted rather than presented for repair. Scanned PDFs and OCR are not supported. CSV export is limited to 50,000 records per request and prefixes formula-leading content across all exported columns; spreadsheet programs may interpret cells differently, so verify files in the intended software.

## Encrypted backup

Backups are portable `.wbackup` files encrypted with AES-256-GCM and a scrypt-derived key. Use a strong passphrase and store it separately; the app does not keep it. Restore first decrypts and previews the file, then requires a separate merge or typed-confirmation replacement action. The app has no pCloud integration and makes no pCloud requests. You may manually transfer an encrypted backup using the pCloud client; OAuth and automatic upload are deferred.

## Current limits

- This is a **single-device local app**, not cross-device sync. The interface reports remote sync as unconfigured. Authentication, a hosted canonical API, offline outbox, conflict resolution, and device/session management are not implemented.
- The local SQLite database remains plaintext. Encrypted backups protect exported copies, not the live database.
- PDF candidate detection is intentionally narrow and cannot reliably parse arbitrary statement layouts.
- Calendar-month budgets use explicit start/end dates and do not roll unused funds forward or recur automatically.
- Wallet activity is available through the transaction list with a wallet filter; a dedicated wallet-detail analytics page is not implemented yet.

## Verification (2026-10-25)

- The full synthetic suite passed: 29 tests, including a real HTTP smoke test on an ephemeral loopback port with a temporary database. To run it: `WEALTH_APP_RUN_HTTP_SMOKE=1 .venv/bin/python -m unittest discover -s tests -v`.
- Python compilation and `node --check static/app.js` / `node --check static/service-worker.js` passed.
- Chrome 156 checks passed for Settings deep links, dialog keyboard navigation, focus containment/restoration, and visible keyboard focus. Responsive, contrast, and screen-reader checks remain outstanding.

Tests use synthetic financial data only; they do not connect to Spendee, bank accounts, or the app process on port 8000.

## Repository security notice

`rea_work/chrome-profile/` was included in the initial Git commit. Its 1,058 tracked entries have been removed from the current Git index and `rea_work/` is ignored; local profile files are preserved. Filename inventory identified browser stores such as Cookies, Login Data, and Web Data. No profile database contents or matched values were opened or disclosed. A limited pattern scan returned one match in a Safe Browsing data file, which has not been classified; no dedicated secret scanner was available. The profile remains in local Git history. **Do not commit or publish this repository until the history and any remote copies have been reviewed and cleaned.**
