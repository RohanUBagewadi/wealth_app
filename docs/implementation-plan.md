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

- Accessibility/responsive review, malformed import and restore tests, migration plan, dependency audit, local data permissions, privacy scan, and deployment documentation.

## Risks and unresolved decisions

- Local-only operation is not cross-device sync.
- PDF candidate extraction is format-dependent and requires user review; no OCR is offered.
- pCloud integration requires an OAuth application and secure server-side token storage; manual encrypted transfer is the safe initial fallback.
- This project has no existing production data schema, so initial schema creation is non-destructive. Future migrations need explicit backup/rollback procedures.
- The live local SQLite database is plaintext. Users need OS disk encryption or a future encrypted storage layer for lost-device protection.
- A dedicated wallet detail view, offline pending-write queue, cross-device sync, and live pCloud OAuth transfer remain unimplemented.

## Verification completed

- `python -m unittest discover -s tests -v`: 13 synthetic domain tests passed.
- `node --check static/app.js` and `node --check static/service-worker.js`: passed.
- Python compilation passed with its bytecode cache redirected to a temporary directory.
- Loopback smoke check: app shell and `/api/health` returned HTTP 200; the new stylesheet was served as CSS; an isolated synthetic wallet and transaction save completed.
- Backup smoke check: AES-GCM encrypted backup round-trip succeeded and a tampered ciphertext was rejected.
- No browser/Spendee data or real financial records were used.
