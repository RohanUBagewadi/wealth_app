# Architecture

## Chosen baseline

- Python 3.9 standard-library HTTP server and SQLite; no web framework or ORM was present.
- Vanilla HTML, CSS, and JavaScript served from the same origin. Inline SVG symbols provide local icons without external assets or CDN requests.
- Bind the web server to `127.0.0.1` only. Local single-user mode requires no password and is not a hosted multi-user service.
- Store the database in `instance/wealth_app.sqlite3` by default, with an environment override for the data directory. Keep runtime data out of version control.
- Use UUIDs, SQLite foreign keys, integer minor units, currency-specific precision, WAL, explicit transactions, and soft-delete/archive semantics.
- The local SQLite database is plaintext. Filesystem permissions reduce access on supported systems; encrypted export backups do not encrypt the live database.

## Data flow

Browser UI → same-origin JSON API → domain validation/calculations → SQLite. CSV rows and recognizable PDF candidates are parsed locally into a staged review batch; only explicitly accepted rows commit. The PDF parser ignores unrecognized lines, so they are not available for manual repair in the review step. Statement bytes are held in memory rather than written to temporary files. Errors and request logs omit payloads and financial values.

Encrypted backup export serializes supported records, derives a key with scrypt, and encrypts with AES-GCM through PyCA cryptography. Restore validates/decrypts and previews counts/conflicts before a separately confirmed atomic merge or replacement. The app does not integrate with or contact pCloud. A user can manually move an encrypted backup with the pCloud client; the app itself uploads no data.

## Sync and deployment decision

Cross-device sync needs a hosted canonical API, identity provider, owner scoping, secret storage, TLS, rate limits, offline outbox, revision/conflict strategy, and operational deployment. None is present in the repo and the specification leaves these decisions open. The app therefore runs local-only, labels remote sync as unconfigured, and does not pretend local storage is cross-device sync. The API/domain boundary is kept separable for a later authenticated sync service.

## PDF parsing

Use maintained `pypdf` for local text extraction. Parsing is best-effort because statement formats vary. A conservative candidate parser stages only recognizable rows for review. Unrecognized PDF lines are ignored and cannot be corrected in the current UI. No OCR or external processing is used.

## Privacy and safety

- No telemetry, analytics, external fonts, or third-party runtime requests.
- Bind only to loopback; reject cross-origin state-changing requests; cap JSON/upload sizes; do not log request content.
- Never delete wallet/category history; archive instead. Transaction deletion is a soft delete. Transfers use a parent record with two ledger legs in a single SQLite transaction.
- Imports and restores use preview then explicit commit. CSV export prefixes formula-leading content in every output column, including wallet and category values. Spreadsheet programs vary, so this reduces risk but is not a universal compatibility guarantee.
- State-changing requests validate Host and Origin against the server's actual loopback address and port; the server refuses non-loopback binds.
- Local-only mode and encrypted backups are not a substitute for a hardened hosted deployment; do not expose this development server to a network.
- There is no pCloud integration. Users may manually upload/download encrypted backups through a separate pCloud client; the app has no OAuth/API upload path and sends no files to pCloud.

## Repository hygiene warning

The Chrome profile under `rea_work/chrome-profile/` was included in the initial Git commit. Its 1,058 tracked entries are removed from the current index and the directory is ignored locally; local profile files are preserved. Filename inventory included browser stores such as Cookies, Login Data, and Web Data. No profile database contents or matched values were opened or disclosed. A limited pattern scan returned one match in a Safe Browsing data file that has not been classified; no dedicated secret scanner was available. The profile remains in local Git history. Do not publish until the history and any remote copies have been reviewed and cleaned.
