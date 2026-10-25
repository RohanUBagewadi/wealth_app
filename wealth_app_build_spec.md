# Personal Finance Web App --- Product & Implementation Specification

**Project:** `wealth_app`\
**Goal:** A private, manual-first personal finance web app for laptop
and mobile, with reviewed PDF/CSV imports, cross-device sync, and
encrypted pCloud backups.

> This is a build specification, not a claim that these features already
> exist. Inspect the repository before implementation and preserve
> working code.

## 1. Product scope

Build a Spendee-inspired personal ledger with: - Manual income, expense,
and transfer entry. - Wallets, categories/subcategories, budgets,
dashboard, and reports. - User-reviewed PDF statement import and CSV
import/export. - Cross-device synchronization, offline-safe pending
changes, and conflict resolution. - Encrypted backup/restore and pCloud
integration or manual encrypted upload fallback. - Responsive
mobile/laptop UI, accessibility, tests, and documentation.

**Do not build:** bank connectivity, bank credential collection,
automatic bank scraping, investment/trading/tax features, household
sharing, or automated import without user review.

## 2. Operating principles

1.  Audit the existing repository, `main.py`, dependencies, database,
    tests, and research folder before changing anything.
2.  Implement incrementally; avoid broad rewrites and dependency churn.
3.  Use synthetic data in tests, demos, and screenshots.
4.  Never log transaction amounts, descriptions, counterparties, wallet
    names, balances, notes, statement text, or account identifiers.
5.  Never inspect browser/Spendee data or use REA/browser automation for
    this build.
6.  Never perform destructive migrations without a migration and
    rollback plan.
7.  Imports, transfers, restore, and bulk edits require preview and
    confirmation.
8.  Use stable IDs, versions, idempotency, and atomic financial
    operations.
9.  Use integer minor units or decimal arithmetic for money, never
    binary floating point.
10. Use vetted cryptographic libraries; do not invent encryption.
11. Document assumptions and unresolved decisions rather than pretending
    they are settled.
12. Continue autonomously within scope; ask only when a genuine blocker
    or security boundary requires user input.

## 3. Repository audit (first task)

Inspect: - repository tree and entry point - `main.py` and relevant
modules - current framework and dependencies - persistence/database and
migrations - tests and baseline failures - current routes/screens -
`./rea_work/research/spendee` contents

Do not dump or copy personal financial records. Do not inspect existing
user databases for sample data. Run the current tests and app using
documented commands.

Create/update: - `docs/baseline-report.md`: detected stack, current
capabilities, tests, storage, gaps - `docs/architecture.md`: proposed
architecture and data flow - `docs/implementation-plan.md`: phased
tasks, risks, decisions

Research files are evidence only when actually present. Do not invent
Spendee findings or claim research completion.

## 4. Navigation and UI

Primary navigation: - Dashboard - Transactions - Wallets - Budgets -
Reports - Categories - Import - Settings

Use sidebar/top navigation on wide screens and compact bottom
navigation/drawer on mobile. Include global date range, transaction
search, add transaction, sync state, backup status, and account/session
controls if applicable.

Reusable UI: - buttons, form fields, dialogs, toasts - loading skeletons
and empty states - currency/date formatting - category icon/color
selector - pagination or virtualized transaction list - destructive
confirmation dialogs

Accessibility: - semantic headings/landmarks - keyboard-operable
controls and dialogs - visible focus - accessible icon labels -
reduced-motion support - WCAG AA contrast where feasible - screen-reader
announcements for save/import/sync/errors

## 5. Domain model

Use stable UUIDs, owner scoping, timestamps, and version/revision
fields. Persist money as integer minor units plus ISO 4217 currency or a
fixed-precision decimal type.

### User

`id`, authentication subject/email only if required, timestamps,
preferences reference. Never store plaintext passwords.

### Wallet

`id`, `owner_id`, `name`, `type` (cash/checking/savings/credit/other),
`currency`, `opening_balance_minor`, `opening_date`, `archived_at`,
timestamps, `version`.

Wallet balance is derived from opening balance and ledger entries.
Archiving preserves history. Do not delete wallets with transactions
without an explicit safe migration. Wallet names are sensitive and must
not appear in logs.

### Transaction

`id`, `owner_id`, `wallet_id`, `type` (expense/income/transfer),
positive `amount_minor`, `currency`, `transaction_date`, optional
`category_id`, description/payee, notes, tags, source
(manual/pdf_import/csv_import/restore), import batch, fingerprint,
timestamps, `deleted_at` if soft-delete, `version`.

Expense/income amounts are positive magnitudes; type determines ledger
sign. Date, amount, wallet, and type are required. Category may be null.
Transaction currency must match wallet currency in v1. Treat all
descriptions and notes as sensitive.

### Transfer

Represent as a logical transfer plus linked outgoing/incoming legs, or
equivalent atomic structure. Fields include transfer ID,
source/destination wallets, amount, currency, date, optional fee, linked
legs.

Rules: - wallets differ - amount positive - same currency in v1 -
excluded from income/expense reports - create/update/delete both legs
atomically - sync and edit as one logical unit

### Category

`id`, `owner_id`, `name`, kind (expense/income/both), optional parent,
icon, color, system flag, archive timestamp, timestamps, version.

Prevent cycles/self-parenting. Archive rather than destroy historical
categories. Deletion requires reassignment. Seed defaults but allow user
customization.

### Budget

`id`, `owner_id`, name, period, start/end, amount, currency, scope
(overall/category/wallet), optional category/wallet, rollover flag,
timestamps, version.

Budget spending includes expenses only and excludes transfers. Define
calendar vs rolling periods explicitly. Avoid double counting and show
currency incompatibility.

### Import batch

`id`, owner, source type, status
(uploaded/parsed/review/committed/failed/cancelled), created/completed
timestamps, counts, parser version, optional encrypted temporary-file
reference.

Imports remain staged until user confirms. Delete temporary statement
files after processing according to retention policy. Never send
statement content to external AI/OCR without explicit opt-in and
disclosure.

### Preferences

Locale, display currency, date format, week start, theme, default
wallet/date range, backup preferences. Collect only necessary profile
data.

## 6. Financial logic

Centralize all calculations in tested domain functions: - wallet balance
= opening balance + signed ledger movements - income = income
transactions - expenses = expense transactions - net = income −
expenses - transfers excluded from income/expense/net - category totals
filter by category and type - date boundaries consistently
inclusive/exclusive

Use currency metadata for minor-unit precision. Validate zero, negative,
malformed, oversized, and unsupported amounts. Do not combine balances
across currencies without explicit conversion model.

Tests must cover opening balance, income/expense, transfers, fees if
supported, date boundaries/leap day, category archive, empty budgets,
currency restrictions, amount validation, and idempotent retries.

## 7. Wallets

Wallet list shows name, type, currency, derived balance, archived
status. Actions: create, edit metadata, archive/unarchive, view
transactions, add transaction, transfer.

Wallet detail shows derived balance, scoped transaction list, date
filter, period income/expense, and actions.

Validate trimmed nonempty name, type, supported currency, opening date,
and amount precision. Block currency changes after transactions exist
unless a deliberate conversion workflow is designed.

## 8. Transactions

List: - newest first by default - search description/payee/notes -
filters: wallet, type, category, date range, import batch -
pagination/virtualization - clear filter/reset and empty states

Create/edit fields: type, wallet, amount, date, category,
description/payee, notes, tags. Validate inline, preserve form on save
failure, prevent duplicate submit, update all views after save, and
route transfer editing to transfer editor.

Delete requires confirmation and sync tombstone. Soft-delete/undo if
feasible. Never delete one transfer leg independently.

Search is bounded/debounced and must not leak query or transaction text
to analytics/logging.

## 9. Categories

Management screen supports expense/income groups, create/edit,
icon/color, hierarchy, ordering, archive, and usage count. Category
selector supports uncategorized and quick reassignment.

Bulk categorization requires preview/confirmation. Archived categories
remain attached to historical records. Validate parent-child
compatibility and prevent cycles.

## 10. Budgets

Budget list shows amount, spent, remaining, period, scope, progress, and
near/exceeded status. Editor supports name, period, amount,
category/wallet scope, and explicit rollover explanation.

Calculation uses transaction date, expenses only, and excludes
transfers. Transactions remain allowed when budget is exceeded. Avoid
shaming language. Show calculation details and incompatible currency
warnings.

## 11. Dashboard and reports

Dashboard: - balance by wallet/currency (never sum unlike currencies) -
income, expenses, net for selected range - budget progress - recent
transactions - category spending summary

Reports: 1. income vs expenses over time 2. spending by category 3.
spending by wallet 4. cash-flow trend 5. budget performance 6. filtered
transaction report

Every report needs date range, filters, accessible chart labels/text
equivalent, empty/loading/error states, currency grouping, transfer
exclusion, and export where available. Reuse existing chart library if
appropriate; avoid large dependency without evaluation.

## 12. PDF/CSV import

High-risk workflow must be staged and user-reviewed.

PDF: 1. select file 2. validate type/size/pages 3. parse locally where
feasible 4. extract text using maintained parser 5. OCR only as clearly
disclosed opt-in; no automatic external upload 6. detect candidate rows
7. normalize date, description, debit/credit, amount, currency, optional
balance 8. choose wallet 9. preview editable rows 10. map categories 11.
flag possible duplicates 12. validate 13. review accepted/skipped rows
14. commit accepted rows atomically 15. show summary and undo if
possible

Parser abstraction: detect format, parse candidates, normalize,
validate. Keep format-specific parsers separate; never assume PDF layout
is universal.

Candidate fields: transaction date, booking/value date, description,
debit, credit, signed amount, currency, optional balance, page/row
identifier.

Category mapping must be explainable. Do not create reusable mapping
rules silently from one row. Saving reusable rules requires explicit
user action.

Duplicate fingerprints may use normalized date, amount, wallet,
currency, description/provider reference. Flag likely duplicates but do
not silently discard ambiguous rows. Import retries must be idempotent.

Flag missing date, zero/malformed amount, ambiguous debit/credit,
duplicate, unsupported currency, incompatible wallet, and unsupported
date.

CSV import/export uses documented schema and synthetic sample template.
Validate before commit. Escape cells starting with `=`, `+`, `-`, or `@`
to prevent spreadsheet formula injection.

Security: parser limits, bounded runtime, safe malformed-file handling,
no embedded content execution, temporary-file cleanup, no statement text
in logs, parser version recorded.

## 13. Export, backup, restore

CSV export: - selected date range/filters/fields - preview/count - UTF-8
and documented formats - formula-injection protection - notes excluded
unless selected

Versioned backup archive includes manifest, wallets, categories,
transactions, budgets, preferences, mapping rules, schema version,
export timestamp. Exclude credentials, session tokens, and keys.

Encryption: - encrypt before cloud upload - use vetted authenticated
encryption (e.g. AES-GCM) - derive passphrase key using vetted strong
KDF (Argon2id preferred) - unique random nonce - store
version/salt/nonce/KDF params/tag in format - never store passphrase/key
in source, logs, or pCloud metadata - explain lost-passphrase recovery
limitations - do not implement cryptography from scratch

Restore: 1. select archive 2. validate structure/version 3. decrypt in
trusted boundary 4. validate records/relations 5. preview
counts/conflicts 6. choose merge/replace; replace requires strong
confirmation 7. atomic commit 8. integrity checks and sync 9. provide
outcome/rollback where feasible Never silently overwrite newer records.

pCloud: Research current official OAuth/API docs first. Do not guess
endpoints or token semantics. Use OAuth, least privilege, secure token
storage, dedicated app folder, upload only encrypted archive, handle
revocation/expiry, show backup timestamp/size/status, and provide manual
encrypted upload/download fallback. Never sync raw PDFs or temporary
statements.

## 14. Cross-device sync

Recommended only after auditing current architecture: - local
database/cache - authenticated canonical API - offline outbox - stable
UUIDs - per-record revision - tombstones - idempotency keys

States: Synced, Pending changes, Offline, Syncing, Sync error. Only show
synced after server acknowledgment.

Conflicts: - detect concurrent revisions - never silently overwrite
financial records - explicit conflict UI with both versions and
keep-this/keep-other choices - transfers resolve as a unit -
deletion-vs-edit requires decision - simple metadata may use documented
last-write-wins - no sensitive values in logs

Retries are bounded and idempotent. Offline edits survive restart. Bulk
import commits as batch. Every server query/mutation enforces owner
scope. Use TLS, secure session handling, authorization, rate limits,
payload limits, CSRF protections for cookie auth, and no secrets in
client bundles.

## 15. Authentication and settings

For hosted sync, use established auth/OAuth or secure password
authentication, session expiry/revocation, rate limiting, and secure
recovery. Sign out clears tokens and optionally decrypted cache. Account
deletion must disclose cloud and backup retention. Avoid custom password
storage.

Settings: locale, currency, date format, week start, theme, default
wallet/date, backup destination/status, encryption instructions, sync
status, export/restore, session management, privacy, app/schema version.
Never display secrets.

## 16. Privacy/threat model

Sensitive: amounts, dates, descriptions, payees, wallet names,
categories, notes, statements, balances, identifiers, backups.

Threats: lost device, compromised session, malformed PDF/CSV,
unauthorized API access, sync conflict, accidental import/restore,
leaked backup, token theft, CSV injection.

Required: - no financial data in logs, telemetry, crash reports,
analytics, exception traces, fixtures, screenshots, or committed files -
user-scoped access - TLS and encrypted backups - minimal statement
retention - safe errors and secure secrets - dependency audit -
synthetic fixtures only

Verify with tests/review that representative sensitive values never
appear in logs or telemetry.

## 17. Error handling

Use clear non-sensitive messages: - save failed; changes pending - file
could not be parsed - rows need review - newer version exists; resolve
conflict - backup encryption failed; nothing uploaded - sync paused;
retry later

Never show statement text, descriptions, or raw server payloads in
errors.

## 18. Testing

Unit tests: calculations, amount parsing/formatting, date boundaries,
budget totals, transfer integrity, fingerprints, category hierarchy,
encryption roundtrip, CSV escaping, parser normalization.

Integration: database CRUD, owner isolation, save/sync, transfer
atomicity, import stage/commit/cancel, backup/restore, conflicts,
migrations.

UI: transaction CRUD, wallet, category, budget, import review/confirm,
sync states, responsive nav, keyboard access.

Security: cross-user denial, invalid/expired token, malformed/oversized
import, formula injection, XSS rendered as text, unauthorized restore,
sensitive log scan.

Use fictional fixtures only.

## 19. Performance/reliability

Paginate transaction history, index owner/wallet/date/category/revision,
debounce search, background large PDF parsing, progress/cancel, bounded
exponential retry with jitter, idempotency keys, handle refresh with
pending sync, correct cache invalidation, and avoid rendering huge
lists.

## 20. Phased plan

### Phase 0 --- Audit

Inspect repo/research, run baseline tests/app, document
stack/data/migrations/gaps, architecture and decisions. **Exit:**
baseline report, architecture decision, prioritized plan.

### Phase 1 --- Ledger

Wallets, categories, transactions, transfers, validation, calculations,
list/forms. **Exit:** CRUD and calculations tested; transfers atomic.

### Phase 2 --- Dashboard/budgets

Summaries, date filters, budgets, category/wallet reports, accessible
charts. **Exit:** totals reconcile and transfers excluded.

### Phase 3 --- Import/export

CSV, parser abstraction, PDF parsing, preview, mapping, duplicates,
batch commit/undo. **Exit:** synthetic statement reviewed safely;
repeated import idempotent.

### Phase 4 --- Sync/auth

Choose backend, auth, outbox, revisions, conflicts, tombstones.
**Exit:** laptop/mobile sync, offline recovery, explicit conflict
resolution.

### Phase 5 --- Backup/restore

Archive, encryption, pCloud integration or manual fallback, preview,
rollback. **Exit:** encrypted roundtrip and safe
invalid/wrong-passphrase failure.

### Phase 6 --- Hardening

Security, accessibility, mobile, dependency audit, migration,
privacy/log review, deployment docs. **Exit:** release checklist
complete; no known data-loss blocker.

## 21. Definition of done

Feature complete only when UI/domain logic, validation,
loading/empty/success/error states, accessibility, tests, migration
consideration, privacy/log review, documentation, and synthetic
demonstration are done. No unrelated files or features changed.

## 22. Codex execution brief

-   Work autonomously within scope; do not request approval for every
    small step.
-   No REA/browser automation and no Spendee inspection.
-   Do not inspect or copy personal financial data.
-   No bank connections or automatic bank extraction.
-   No destructive database migration without plan/backup.
-   Research official pCloud docs before integration.
-   Use vetted crypto libraries.
-   Never claim completion without implementation and tests.
-   Run tests and inspect diff after each phase.
-   Report changed files, tests, risks, and next work.
-   If blocked, continue independent work and state the exact blocker.
-   Keep changes focused and synthetic data only.

**First task:** audit `wealth_app` and `./rea_work/research/spendee`;
create `docs/baseline-report.md`, `docs/architecture.md`, and
`docs/implementation-plan.md` based on actual findings. Begin Phase 1
only if safe and supported by current architecture.

## 23. Release checklist

-   [ ] baseline and architecture documented
-   [ ] migrations reviewed
-   [ ] derived wallet balances correct
-   [ ] income/expense totals reconcile
-   [ ] transfers excluded from spending reports
-   [ ] category archive preserves history
-   [ ] budgets tested
-   [ ] import preview/confirmation
-   [ ] duplicate detection and idempotency
-   [ ] CSV formula-safe
-   [ ] encrypted backup before cloud upload
-   [ ] restore preview and validation
-   [ ] pCloud OAuth/API verified
-   [ ] owner isolation
-   [ ] offline changes survive restart
-   [ ] conflicts resolvable
-   [ ] no sensitive logs
-   [ ] mobile layout and accessibility reviewed
-   [ ] synthetic fixtures only
-   [ ] tests pass
-   [ ] README and release notes updated

## 24. Open decisions

Resolve after repository audit; do not guess: - current framework and
whether to retain it - database and migrations - local-first
architecture - authentication provider - sync backend/hosting -
encryption boundary - PDF parser/OCR - pCloud OAuth/API vs manual
encrypted archive - currency precision and multi-currency scope - backup
retention and restore conflicts - PWA/offline behavior - deployment/cost

Choose the simplest architecture that meets privacy, sync, backup, and
maintainability needs without destabilizing the existing app.
