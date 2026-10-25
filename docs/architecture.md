# Architecture

## Chosen baseline

- Python 3.9 standard-library HTTP server and SQLite; no web framework or ORM was present.
- Vanilla HTML, CSS, and JavaScript served from the same origin. Inline SVG symbols provide local icons without external assets or CDN requests.
- Bind the web server to `127.0.0.1` only. Local single-user mode requires no password and is not a hosted multi-user service.
- Store the database in `instance/wealth_app.sqlite3` by default, with an environment override for the data directory. Keep runtime data out of version control.
- Use UUIDs, SQLite foreign keys, integer minor units, currency-specific precision, WAL, explicit transactions, and soft-delete/archive semantics.
- The local SQLite database is plaintext. Filesystem permissions reduce access on supported systems; encrypted export backups do not encrypt the live database.

## Data flow

Browser UI → same-origin JSON API → domain validation/calculations → SQLite. CSV/PDF imports are parsed locally into a staged review batch; only explicitly accepted rows commit. Statement bytes are never written to a temporary file. Errors and request logs omit payloads and financial values.

Encrypted backup export serializes supported records, derives a key with scrypt, and encrypts with AES-GCM through PyCA cryptography. Restore validates/decrypts and previews counts/conflicts before a separately confirmed atomic merge or replacement. Manual encrypted file transfer is the initial pCloud-compatible fallback; raw data is never uploaded.

## Sync and deployment decision

Cross-device sync needs a hosted canonical API, identity provider, owner scoping, secret storage, TLS, rate limits, offline outbox, revision/conflict strategy, and operational deployment. None is present in the repo and the specification leaves these decisions open. The app therefore runs local-only, labels remote sync as unconfigured, and does not pretend local storage is cross-device sync. The API/domain boundary is kept separable for a later authenticated sync service.

## PDF parsing

Use maintained `pypdf` for local text extraction. Parsing is best-effort because statement formats vary. A conservative candidate parser stages only recognizable rows; all rows remain editable/reviewable, and ambiguous rows are excluded until the user resolves them. No OCR or external processing is used.

## Privacy and safety

- No telemetry, analytics, external fonts, or third-party runtime requests.
- Bind only to loopback; reject cross-origin state-changing requests; cap JSON/upload sizes; do not log request content.
- Never delete wallet/category history; archive instead. Transaction deletion is a soft delete. Transfers use a parent record with two ledger legs in a single SQLite transaction.
- Imports and restores use preview then explicit commit. Formula-like CSV cells are escaped on export.
- Local-only mode and encrypted backups are not a substitute for a hardened hosted deployment; do not expose this development server to a network.
- The pCloud fallback is manual upload/download of encrypted backup files. OAuth/API upload is deferred pending app registration and server-side token storage.
