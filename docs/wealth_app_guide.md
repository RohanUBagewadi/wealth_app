# Wealth App Guide

This guide describes the code currently in this repository. It is a local, single-user finance app; it is not yet a cloud-synced or production-hardened service.

## 1. Project Overview

The app uses Python 3.9's standard-library HTTP server, SQLite, and a browser interface written in plain HTML, CSS, and JavaScript. There is no Flask, Django, React, or ORM. `main.py` serves the page and JSON API; `finance_core.py` validates financial data and performs database operations.

The default database is `instance/wealth_app.sqlite3`. `WEALTH_APP_DATA_DIR` can point to another local folder. The service binds to `127.0.0.1:8000` only. It has no login and should not be exposed to a network.

**Approved release scope:** keep this app local-first. Hosted sync, cloud accounts, authentication, pCloud OAuth, and automatic uploads are deferred and are not requirements for the local release. Manual encrypted backup/restore remains the supported way to transfer or recover data.

## 2. What Is Implemented

| Feature | Status | What it does and current limits |
|---|---|---|
| Dashboard | Done | Date range, income/expense/net summaries, cash-flow comparison, budget progress, wallet balances, and recent activity. Balances stay grouped by currency. |
| Responsive layout | Done | Desktop sidebar; compact icon sidebar at medium widths; mobile bottom navigation and stacked content on narrow screens. Browser/device visual review is still needed. |
| Icons and backgrounds | Done | Local inline SVG icons and CSS gradients; no icon CDN or external font dependency. |
| Wallets | Partial | Create/edit, opening balance/date, type/currency, archive/restore, currency totals, and a shortcut to filtered activity. No dedicated wallet detail/analytics page. |
| Transactions | Done | Manual expense/income entry, edit, search, wallet/type/category filters, pagination, and confirmed soft delete. The UI does not provide a separate import-batch filter. |
| Transfers | Partial | Create/edit and delete as a paired operation through the transaction form. There is no standalone Transfers page. Same-currency wallets are required; fees are not supported. |
| Categories | Partial | Seeded and custom categories, type, icon, color, one-level parent, and archive fields. Reordering, usage counts, and a clear archived-category restore view are not present. |
| Budgets | Partial | Create, edit, archive, date range, amount, currency, and overall/category/wallet scope. They use explicit dates; automatic recurrence and rollover are not supported. |
| Reports | Partial | Date-filtered summary, spending by category and wallet, and monthly income/expense. Report exports, additional filters, and detailed chart accessibility review remain to do. |
| CSV import | Partial | UTF-8 CSV is staged for row review/editing and explicit commit or discard. Input is bounded to 2 MB/5,000 rows; BOM headers are accepted and malformed quoting rejected. Wider real-world format compatibility is unverified. |
| PDF import | Partial | Local text extraction with `pypdf`, then staged review of rows matching a narrow ISO-date / description / amount pattern. The 8 MB decoded-file limit is enforced; unrecognized lines are omitted rather than offered for repair. Scanned PDFs and OCR are unsupported. |
| CSV export | Done (core safety) | Optional date range and up to 50,000 records. All emitted cells are protected against formula-leading content and the synthetic suite checks wallet, category, description, and note fields. Compatibility across spreadsheet programs is not visually tested. |
| Settings | Partial | Display currency, theme, week-start preference, and privacy/sync/backup status. Preferences are browser-local; the selected currency/week start are not consistently applied throughout the UI. There is no account or session management. |
| Encrypted backup | Done | Passphrase-derived key using scrypt and AES-256-GCM; version 1 now accepts only the app's generated work factors to bound decryption cost. Passphrase is not saved; a lost passphrase cannot be recovered. |
| Backup restore | Partial | Decrypt and preview first, then merge or separately confirmed replacement. Preview rejects missing required database fields; synthetic tests verify encryption round-trip, tamper/wrong-passphrase rejection, bounded KDF settings, and rollback on failed replacement. Broader malformed archive testing is still needed. |
| Local persistence | Done | SQLite with integer minor-unit money, foreign keys, WAL, version fields, soft-delete/archive behavior, and restricted file/directory permissions where supported. The database itself is plaintext. |
| Remote sync / login | Not implemented | This is one local workspace. No authentication, multi-user API, offline outbox, conflict resolution, or device management exists. |
| pCloud transfer | Manual process only | The app has no pCloud integration and sends no files to pCloud. A user may transfer encrypted backup files manually with the separate pCloud client; direct OAuth/API integration and automatic upload are deferred. |

No bank connections, automatic bank extraction, statement scraping, or OCR are implemented.

## 3. UI Layout and Navigation

On a laptop, a fixed left sidebar links to Dashboard, Transactions, Wallets, Budgets, Reports, Categories, Import & export, and Settings. The top bar shows the current section, transaction search, local-mode indicator, and Add transaction button. On a phone, the sidebar is hidden; a bottom bar links Home, Activity, Add, Wallets, and More (Settings). Budgets, Reports, Categories, and Import & export remain available from the responsive sidebar layout at wider sizes.

```text
Wealth
├── Desktop sidebar / mobile bottom navigation
├── Top bar: section, search, local mode, Add transaction
└── Main content
    ├── Dashboard: summaries, cash flow, budgets, wallets, recent entries
    ├── Transactions: searchable, filtered, paginated ledger
    ├── Wallets: wallet cards and archived wallets
    ├── Budgets: budget summaries and progress cards
    ├── Reports: date range, category, month, wallet
    ├── Categories: expense and income groups
    ├── Import & export: CSV, PDF review, CSV export, backup/restore
    └── Settings: preferences, privacy, sync and backup status
```

Transfers do not have their own page. Start with **Add transaction**, then choose **Transfer** in the form. A wallet's **Activity** control opens Transactions with that wallet filter selected. Settings are displayed as panels on one page.

## 4. How to Customize the UI

Open the project in PyCharm, then use the Project pane to open the files below. Save changes and reload the app page. CSS/HTML/JavaScript changes are served directly; restart the Python server after Python changes. To undo an edit, use PyCharm's local history or restore the original lines with Undo before saving.

| File | UI area / safe changes |
|---|---|
| `static/index.html` | Main shell, desktop and mobile navigation, page sections, labels, and form roots. Change structure and static copy here. |
| `static/app.js` | Page switching, dashboard/wallet/transaction/budget/category/report rendering, form behavior, and UI events. Change behavior or generated page content here. |
| `static/app.css` | Main visual theme, typography, desktop layout, cards, sidebar, colors, spacing, and responsive rules. Much of this file is currently one long/minified line, which makes editing less convenient. |
| `static/components.css` | Smaller readable overrides for cash-flow rows and report components. Add focused component styles here. |
| `finance_core.py` | SQLite schema, validation, balances, reports, budgets, imports, exports, and restore logic. Avoid changing this just to adjust appearance. |
| `main.py` | HTTP routes, static-file allowlist, local server, CSV/PDF parsing, and encrypted backup endpoints. |

Examples from the current styles:

- **Change the page background:** in the `:root` rule in `static/app.css`, change `--canvas:#f5f6fa`. The `body` background uses this variable beneath its soft radial gradients.
- **Change the accent color:** change `--lav:#7c6ef2` and, if desired, its related `--lav-deep` and `--lav-soft` values in the same rule.
- **Change card rounding:** adjust `--radius:20px` in `:root`.
- **Change spacing:** find `.content-wrap` in `static/app.css` and adjust its `padding`; find `.dashboard-grid` to adjust the gap between dashboard panels. Since the file is minified, use PyCharm Find (`⌘F` on Mac) for the selector.
- **Change an icon:** icons are SVG `<symbol>` entries near the top of `static/index.html`. For example, `id="i-wallet"` defines the wallet icon. `static/app.js` renders one with `icon('wallet')`. Keep the symbol ID and the name passed to `icon()` aligned.
- **Change a page layout:** edit that page's `<section data-view="…">` in `static/index.html`, then update its rendering function in `static/app.js` if it contains dynamic data.

To add a navigation page, add a sidebar link with `data-page="new-page"` and `href="#new-page"`, add a matching `<section id="view-new-page" data-view="new-page">`, and add its title to the page-title map in `setPage()` in `static/app.js`. Add a mobile link too if it should appear in the bottom bar. If it needs dynamic data, connect its renderer in `refresh()` / `setPage()` and implement any required API/domain work; a link alone does not implement a feature.

## 5. How to Launch the App

1. Open the `wealth_app` folder in PyCharm.
2. Open PyCharm's Terminal at the project root.
3. The project environment is `.venv`. If it is not present, create it with `python3 -m venv .venv`.
4. Install dependencies if needed: `.venv/bin/python -m pip install -r requirements.txt`. The listed libraries are `cryptography` and `pypdf`.
5. Start the server: `.venv/bin/python main.py`.
6. Open `http://127.0.0.1:8000` in a browser.
7. Stop the server with **Ctrl+C** in its terminal, or the Stop button if it was started from PyCharm.

The configured environment uses Python 3.9.6. If `Address already in use` appears, another process already owns port 8000; stop that process only if you know it is your app, or arrange a different port in code and keep the documented URL in sync. `serve()` defaults to port 8000; the Host/Origin guard validates the actual bound loopback port. If the page cannot connect, confirm the terminal still shows the server running and use the exact loopback URL above.

## 6. Testing and Verification

### Recorded verification (2026-10-25)

These results are from the most recent recorded verification run; they were not rerun during this documentation review.

- `WEALTH_APP_RUN_HTTP_SMOKE=1 .venv/bin/python -m unittest discover -s tests -v`: **29 tests passed**. This includes real HTTP requests to the application handler on an ephemeral loopback port using a disposable synthetic SQLite database, plus a check that the server refuses non-loopback binding.
- The HTTP test exercised app/static pages, health/bootstrap/reports/settings, wallet/category/budget/transaction/transfer create and update routes, CSV preview/commit/cancel/export, invalid PDF input, encrypted backup create/preview/restore, malformed requests, and Host/Origin rejection. It did not connect to port 8000.
- `node --check static/app.js` and `node --check static/service-worker.js`: passed.
- Python compilation for `main.py`, `finance_core.py`, and test modules: passed.
- Chrome 156 on macOS: Settings deep links (`preferences`, `privacy`, `sync`), dialog keyboard navigation and focus containment, Escape close with focus restoration, and visible keyboard focus passed. No page runtime errors occurred.

The browser checks used a separate temporary Chrome profile. Browser requests were restricted to the synthetic local test server; no forms were submitted. No live database, real financial records, or Spendee pages were accessed.

### Tests still needed

- Responsive layout checks on laptop and phone-sized viewports, screen-reader testing, and contrast review.
- End-to-end wallet create/edit/archive/restore; transaction create/edit/delete; income/expense dashboard calculations; transfer balance consistency.
- Category selection and archive behavior; budget scopes, dates, and filters; report date boundaries and currency grouping.
- CSV imports with unusual delimiters, bad dates/amounts, duplicates, formula cells, and representative exports from other apps; PDF imports with multiple statement layouts, encrypted/scanned files, and ambiguous rows.
- CSV export boundary at 50,000 records and formula behavior in target spreadsheet programs.
- Broader backup malformed/oversized file cases, merge conflicts, replacement confirmation, and recovery scenarios.
- Error paths, browser storage behavior, local database permissions, dependency review, and an independent security review before entering real data.

## 7. What Is Still Missing

| Feature | Status | What's missing |
|---|---|---|
| Wallet detail/activity | Partial | Dedicated wallet page, scoped summary and date controls; current Activity action filters the transaction list. |
| Remote synchronization | Not implemented (deferred) | Hosted canonical API, offline queue, revisions, conflict UI, retry policy, and device sync; intentionally outside the approved local release. |
| Authentication/account management | Not implemented (deferred) | Identity provider, secure sessions, recovery, sign-out, and account lifecycle; intentionally outside the approved local release. |
| Multi-device deployment | Not implemented (deferred) | Hosting, TLS, domain, owner isolation, operations, backups, and abuse/rate controls; no deployment is approved. |
| Integrated pCloud | Not implemented (deferred) | OAuth app registration, token lifecycle/storage, encrypted-file upload/download, and status/revocation handling. Manual encrypted file transfer is supported instead. |
| Live database encryption | Not implemented | The SQLite file is plaintext; OS-level full-disk encryption or an evaluated encrypted database/storage design is needed. |
| Import compatibility | Partial | More formats, parser fixtures, ambiguous-row handling, and integration tests. PDF support is deliberately narrow. |
| Accessibility and visual QA | Needs verification | Keyboard/focus behavior, screen-reader descriptions, contrast, and real viewport checks. |
| Schema migrations | Needs verification | A schema version exists, but a production migration and rollback process is not established. |

## 8. Challenges and Limitations

### Confirmed limitations

- **Plaintext live database:** AES-GCM applies to exported backup files only. A person or malware with access to the local database file can read its contents. Before storing real records, evaluate full-disk encryption and an encrypted database approach, backups, key handling, and recovery. File permissions are not encryption.
- **No multi-device sync or login:** Sync would require an authenticated server, TLS, per-user authorization, offline change queue, conflict resolution, transfer-level atomicity, deletion handling, and device/session management. These choices are not present in the current local-only app.
- **Manual pCloud workflow:** the app does not contact pCloud. Users may transfer the encrypted archive themselves with a separate client. Direct support would require an OAuth application, safe token handling, least-privilege access, token refresh/revocation, upload error handling, and a policy to upload only encrypted backups.
- **Wallet activity is a filter:** activity opens the general transaction list with one wallet selected. There is no wallet detail analytics screen.
- **Import reliability:** CSV/PDF parsing is not universal. PDF parsing expects selectable text and a narrow ISO-date/description/amount row; it is not OCR. Imports require user review, but varied/malformed files and duplicates still need systematic tests.
- **CSV formula safety:** all exported cells are now protected against formula evaluation, with synthetic tests covering each user-controlled text column. Confirm behavior in the spreadsheet programs the owner plans to use.
- **Preference coverage:** theme, currency, and week-start preferences are stored in browser local storage, but currency/week-start behavior is not consistently wired to all forms/views; preferences are also not part of the encrypted backup payload.
- **Single-user security boundary:** there is no authentication. Loopback binding, Host/Origin checks, payload limits, security headers, and suppressed request logging are useful safeguards, but do not make this a hardened hosted product.
- **Offline behavior:** the service worker caches the app shell only. It does not queue or save finance changes offline.
- **Other feature gaps:** no recurring transactions, fee-aware transfers, report export, category ordering/usage count, or automatic budget rollover/recurrence.
- **Maintenance:** most rules in `static/app.css` are compressed into one line, which makes careful visual editing harder.

### Recommendations, not current features

Keep using synthetic data until storage and security choices are reviewed. Do not expose the server beyond loopback. Before adding cloud services, decide who hosts the data, who controls encryption keys, how recovery works, and what happens during conflicting edits or device loss.

## 9. Recommended Next Steps

1. **Stability and security:** add repeatable API/end-to-end tests; test restart persistence and additional restore recovery paths; review plaintext storage, permissions, logs, and dependencies.
2. **UI polish:** test phone/laptop layouts and keyboard access; add a real wallet detail/activity view; make archived categories/budgets easier to review; reformat `app.css` for maintainability.
3. **Deferred future work:** hosted sync, accounts, multi-device deployment, and pCloud OAuth are not part of the approved local release. Revisit them only after a separate product/security decision and explicit approval.

## 10. Project File Map

| Path | Purpose |
|---|---|
| `main.py` | Local HTTP server, JSON routes, CSV/PDF parsing, backup encryption endpoints. |
| `finance_core.py` | SQLite schema and finance rules/calculations. |
| `static/index.html` | Page shell, navigation, sections, SVG icon symbols. |
| `static/app.js` | Navigation, rendering, forms, import/backup interactions. |
| `static/app.css` | Main visual theme and responsive layout. |
| `static/components.css` | Component styling overrides. |
| `static/service-worker.js` | App-shell cache; API and finance data bypass it. |
| `static/manifest.webmanifest` | Web app metadata. |
| `requirements.txt` | `cryptography` and `pypdf` dependencies. |
| `tests/test_finance.py` | Synthetic finance-domain unit tests. |
| `tests/test_import_parsing.py` | Synthetic CSV/PDF parser validation and boundary tests. |
| `tests/test_http_smoke.py` | Opt-in HTTP handler smoke tests using a disposable synthetic database and loopback port. |
| `README.md` | Short setup, privacy, and limitation summary. |
| `docs/architecture.md` | Current technical design and sync boundary. |
| `docs/implementation-plan.md` | Phases, decisions, and recorded verification. |
| `wealth_app_build_spec.md` | Original product requirements; not proof that each item is implemented. |

### Repository history warning

The Chrome profile under `rea_work/chrome-profile/` was present in the initial Git commit. Its 1,058 tracked entries have been removed from the current index and are ignored locally; local files were preserved. Filename inventory identified browser stores such as Cookies, Login Data, and Web Data. No profile database contents or matched values were opened or disclosed. A limited pattern scan returned one unclassified match in a Safe Browsing data file; no dedicated secret scanner was available. The profile remains in Git history. Do not commit or publish until history and any remote copies are reviewed and cleaned.
