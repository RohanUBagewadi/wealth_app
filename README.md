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
- Service-worker caching is limited to the app shell. API responses and finance data are not cached for offline writes.
- Money is persisted as integer minor units. Wallets in different currencies are displayed separately and never added together.
- Transactions are manual or explicitly accepted from a staged import. No bank connection, scraping, automatic extraction, or OCR exists.

## Imports and exports

CSV imports use the header `transaction_date,type,amount,currency,wallet,category,description,notes`. Each row is staged and editable before the explicit save action. The app also accepts `date` as an alias for `transaction_date`. PDF text parsing is local and best-effort, supports selectable text only, and requires row review. Scanned PDFs and OCR are not supported. CSV export is limited to 50,000 records per request and escapes formula-leading description/note cells.

## Encrypted backup

Backups are portable `.wbackup` files encrypted with AES-256-GCM and a scrypt-derived key. Use a strong passphrase and store it separately; the app does not keep it. Restore first decrypts and previews the file, then requires a separate merge or typed-confirmation replacement action. pCloud is supported only as a manual destination for the encrypted file. The official [pCloud OAuth authorization](https://docs.pcloud.com/methods/oauth_2.0/authorize.html), [token exchange](https://docs.pcloud.com/methods/oauth_2.0/oauth2_token.html), and [file upload](https://docs.pcloud.com/methods/file/uploadfile.html) APIs are not configured in this prototype because OAuth requires app registration and secure token handling.

## Current limits

- This is a **single-device local app**, not cross-device sync. The interface reports remote sync as unconfigured. Authentication, a hosted canonical API, offline outbox, conflict resolution, and device/session management are not implemented.
- The local SQLite database remains plaintext. Encrypted backups protect exported copies, not the live database.
- PDF candidate detection is intentionally narrow and cannot reliably parse arbitrary statement layouts.
- Calendar-month budgets use explicit start/end dates and do not roll unused funds forward or recur automatically.
- Wallet activity is available through the transaction list with a wallet filter; a dedicated wallet-detail analytics page is not implemented yet.

## Checks

Run the synthetic domain tests with `.venv/bin/python -m unittest discover -s tests -v`. Check browser JavaScript syntax with `node --check static/app.js`.

No Spendee/browser data or real financial records are used in the test fixtures.
