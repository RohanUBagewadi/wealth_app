# Implementation plan

## Phase 0 — audit (complete)

- Inspected repository, `main.py`, research files, dependencies, run configuration, and PyCharm interpreter.
- Confirmed the repo had no app, tests, persistence, or dependency manifest; sample entry point ran.
- Selected a local-only stdlib + SQLite architecture and documented open hosted-sync decisions.

## Phase 1 — local ledger and UI (implemented and verified)

- Implement wallet/category/transaction/transfer/budget data model and safe calculations.
- Build responsive dashboard and navigation for transactions, wallets, budgets, reports, categories, import, and settings.
- Add safe API validation, local-only binding, empty states, and unit/integration tests with synthetic data.

## Phase 2 — staged import and export (implemented and verified)

- Implement documented CSV format, formula-safe export, local PDF text extraction, duplicate warnings, editable preview, and atomic commit/cancel.

## Phase 3 — encrypted backup/restore (implemented and verified)

- Use vetted AES-GCM and scrypt. Add encrypted archive export, restore preview, conflict handling, and explicit merge/replace confirmation.
- Keep pCloud as manual encrypted upload/download until an OAuth app registration and secure token-storage/deployment plan are available.

## Phase 4 — hosted sync decision (blocked on product/deployment choices)

- Select host, canonical API, auth provider, encryption boundary, owner identity, device/session revocation, retention, and operating cost.
- Implement offline outbox, revisions, idempotency, tombstones, conflict resolution, and mobile/laptop sync only after those decisions.

## Phase 5 — hardening (in progress)

- Implemented in this pass: formula-safe CSV output for all cells; strict and bounded CSV parsing with UTF-8 BOM support; exact decoded PDF size enforcement; restore rollback regression coverage; settings deep-link routing; keyboard focus containment/restoration for dialogs; visible keyboard focus styling; and local-data/secret/IDE ignore rules.
- The regression suite has 29 passing tests. An opt-in HTTP smoke test exercises the actual handler on an ephemeral loopback port with a disposable synthetic database. Chrome 156 browser checks passed for Settings deep links, dialog keyboard navigation, focus containment/restoration, and visible focus styling. Responsive and screen-reader testing, migrations, dependency review, local data permission review, and independent security review remain outstanding.

## Risks and unresolved decisions

- Local-only operation is not cross-device sync.
- PDF candidate extraction is format-dependent and requires user review; no OCR is offered.
- pCloud integration requires an OAuth application and secure server-side token storage; manual encrypted transfer is the safe initial fallback.
- This project has no existing production data schema, so initial schema creation is non-destructive. Future migrations need explicit backup/rollback procedures.
- The live local SQLite database is plaintext. Users need OS disk encryption or a future encrypted storage layer for lost-device protection.
- The Chrome profile was included in the initial Git commit. Its 1,058 tracked entries are removed from the current index and ignored locally, while local files are preserved. Filename inventory identified browser data stores. No profile database contents or matched values were opened or disclosed; a limited pattern scan returned one unclassified match in a Safe Browsing file, and no dedicated secret scanner was available. The profile remains in local history; do not publish until history/remote exposure is reviewed and resolved.
- A dedicated wallet detail view, offline pending-write queue, cross-device sync, and live pCloud OAuth transfer remain unimplemented.

## Verification completed

- `WEALTH_APP_RUN_HTTP_SMOKE=1 .venv/bin/python -m unittest discover -s tests -v`: 29 tests passed, including the actual HTTP handler on an ephemeral loopback port with synthetic data and a test that refuses non-loopback binding.
- `node --check static/app.js` and `node --check static/service-worker.js`: passed.
- Python compilation passed with its bytecode cache redirected to a temporary directory.
- Browser checks on Chrome 156: Settings deep links, modal keyboard traversal, focus containment, Escape/focus restoration, and visible keyboard focus passed. No page runtime errors occurred.
- HTTP smoke coverage included app/static pages, health/bootstrap/reports/settings, synthetic wallet/category/budget/transaction/transfer create and update operations, CSV preview/commit/cancel/export, PDF validation, backup create/preview/restore, invalid requests, and Host/Origin guards.
- Backup regression checks cover AES-GCM round-trip, tampered ciphertext, wrong passphrase, KDF limits, failed-restore rollback, and synthetic restart persistence.
- No browser/Spendee data or real financial records were used.
