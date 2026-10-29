# Wealth App Security Reviews

## Purpose and scope

This document preserves four read-only security reviews recorded for `wealth_app`. The reviews are evidence summaries, not a certification that the application is secure or vulnerability-free. The broader review was static; the database and dependency reviews inspected metadata/source only; the backup review inspected source and test definitions only.

No live financial records, database contents, secrets, credentials, Git history, or Chrome profile contents are included here. The broader review did not execute tests. Recommendations below have not been implemented unless explicitly stated otherwise.

**Phase 5 status: IN PROGRESS.**

## Security architecture and trust boundaries

**Source-level observations:** The app is a Python standard-library HTTP server, SQLite, and vanilla browser UI. It is designed for local single-user use and refuses to bind outside `127.0.0.1`. There is no login or API authentication; local callers are trusted. Financial data is stored in a plaintext SQLite database. CSV/PDF files are processed locally and imports are staged for review. Encrypted backups use AES-GCM and scrypt.

Loopback binding limits network reachability but does not authenticate local processes. Browser same-origin protections and request checks are part of the boundary, particularly because the API exposes financial data. Filesystem permissions protect against other ordinary local accounts only when the configured directory and its parents remain appropriately restricted; they do not encrypt the database or protect against the same user, administrators, or malware running as that user.

## Review 1: Database file and directory permissions

### Status and method

**Complete; read-only metadata and source review.** No application startup, database opening, test execution, or permission changes were performed.

### Files and areas examined

- `main.py`: `data_directory()` and `STORE` initialization.
- `finance_core.py`: `FinanceStore.__init__()`, SQLite WAL setup, and database permission handling.
- `README.md`, `docs/architecture.md`, `docs/implementation-plan.md`, and `docs/wealth_app_guide.md` for storage configuration.
- macOS filesystem metadata for the observed default database path and its directory ancestors.

### Confirmed safeguards and observations

- Default database path is project-root `instance/wealth_app.sqlite3`.
- `WEALTH_APP_DATA_DIR` overrides the directory; `~` is expanded, and a relative value is relative to the process working directory.
- The inspection shell had no override set, and the default database file existed. A separately launched application environment was not inspected.
- Observed default `instance/` mode was `0700`; database and WAL were `0600`; SHM was `0644`; rollback journal was absent.
- The database, sidecars, and data directory owner UID/GID matched the inspection user (`503:20`).
- The `0700` directory prevents ordinary group/other access to the SHM file despite its `0644` mode.
- No ACL entries were observed on the database or data directory. Some higher ancestors had ACL entries; their rules/identities were not inspected. Parent directory modes varied but the private data directory blocks ordinary traversal.
- `main.py` creates/sets the configured data directory to `0700` best-effort. `FinanceStore` sets the database to `0600` best-effort after SQLite initialization. SQLite creates WAL/SHM files; the app does not explicitly chmod those sidecars.
- Backup creation returns an encrypted file as a browser download; the app does not save it into the database directory.

### Findings and recommendations

| Finding | Attention | Evidence/status |
|---|---|---|
| Default database and containing directory are owner-only under observed mode bits | PASS | Metadata observed for the default path only. |
| SHM has group/other read bits | NEEDS ATTENTION | Mode `0644`, but access was blocked by observed `0700` parent directory. |
| Custom `WEALTH_APP_DATA_DIR` permissions | NOT VERIFIED | Its value/path was not printed or inspected. |
| Browser download/backup destination permissions | NOT VERIFIED | Destination depends on browser/OS/user choice and was not inspected. |
| Live database is plaintext | Informational risk | Confirmed from source/documentation; filesystem permissions are not encryption. |

The review recommended considering a restrictive launch umask such as `077` for newly created SQLite sidecars, and checking ownership/permissions for any custom data directory and its path. It advised against chmodding SHM while SQLite may be using it. No permission changes were applied.

### Tests/checks

Read-only source searches and file reads plus `stat -f` / `ls -lde` metadata inspection. No tests were run. The actual database contents were not opened.

## Review 2: Dependencies

### Status and method

**Complete; read-only declaration and import review.** No package installation, upgrade, scanner installation, network access, or application execution was performed.

### Files and areas examined

- `requirements.txt`
- Python imports in `main.py`, `finance_core.py`, and `tests/*.py`
- Frontend resource references in `static/index.html`, `static/app.js`, and `static/service-worker.js`
- Setup instructions in `README.md` and `docs/wealth_app_guide.md`

### Confirmed dependencies and usage

| Package | Declared constraint | Usage |
|---|---|---|
| `cryptography` | `>=44,<45` | Runtime AES-GCM backup encryption/decryption and scrypt key derivation. |
| `pypdf` | `>=5,<6` | Runtime local PDF text extraction; also builds synthetic test PDFs. |

The app otherwise uses the Python standard library for HTTP, SQLite, CSV/JSON, and core calculations. No third-party JavaScript package declaration or package manager lockfile was found. The reviewed frontend uses local assets and showed no external runtime CDN/service dependency.

### Findings and recommendations

- **Confirmed:** constraints permit multiple patch releases; there is no exact-version lockfile or hash-checking declaration.
- **Confirmed:** the README installs dependencies from `requirements.txt`. No project-level custom package index was found; machine-level pip settings were not inspected.
- **Candidate assessment:** no dependency appeared unused. Removing either package would disable PDF import or encrypted backup/restore.
- **Not verified:** current upstream maintenance status and known vulnerability advisories. The review did not contact advisory services.
- **Scanner availability:** `pip-audit`, `safety`, `bandit`, `osv-scanner`, and `trivy` were not found on `PATH`. No scanner was installed or run. The review did not establish that the dependencies are vulnerability-free.

Recommendations were to consider exact versions and hashes for reproducible installs, scan the installed environment against a trusted advisory source when tooling is available, and review machine-level pip index settings before future installation. No dependency or configuration changes were applied.

### Tests/checks

Read-only declaration/import/resource searches and local `command -v` scanner checks. No tests or package scans were run.

## Review 3: Backup and recovery edge cases

### Status and method

**Complete; read-only source and test-definition review.** The app and tests were not run; no backup was created, opened, restored, or modified.

### Files and functions examined

- `main.py`: `encrypt_backup()`, `decrypt_backup()`, backup HTTP routes, body handling, and error handling.
- `finance_core.py`: `backup_payload()`, `preview_restore()`, `restore_payload()`, `_write()`, and relevant schema/foreign keys.
- `static/app.js`, `static/index.html`: backup creation, preview, merge, and replacement UI.
- Backup-related tests in `tests/test_import_parsing.py`, `tests/test_finance.py`, and `tests/test_http_smoke.py`.

### Confirmed safeguards

- Backup format is version 1 and serializes owner-scoped rows from wallets, categories, transactions, transfers, and budgets.
- Encryption uses random 16-byte salt, 12-byte nonce, AES-256-GCM, fixed associated data, and scrypt work factors fixed at `N=2^15, r=8, p=1`.
- Decryption checks format, version, cipher, KDF, exact work factors, strict base64, salt/nonce lengths, and minimum ciphertext length. Authentication failure and unexpected parsing errors are converted to generic decryption errors.
- Restore preview validates top-level shape, required table lists, per-list record bounds, IDs, required non-default database fields, wallet-currency conflicts, and transaction references/type/positive amount.
- Preview performs reads and `PRAGMA table_info`; it does not write records.
- Replacement confirmation is required in the UI and HTTP handler. Restore writes run in `_write()` using `BEGIN IMMEDIATE`, commit on success, and rollback on exception.
- The database uses WAL mode. No runtime crash-recovery experiment was performed.

### Findings and recommendations

| Finding | Severity/attention | Evidence/status |
|---|---|---|
| Preview response returns the entire decrypted payload and the UI retains it in JavaScript state | Moderate privacy/data-minimization concern | Source observed; UI renders counts and restore resubmits the encrypted archive. Not dynamically measured. |
| Creation has no explicit archive-size limit, while restore JSON is capped at 12 MiB and carries base64 data | Moderate reliability/resource concern | Source observed; base64 expansion can make an archive too large to restore through the endpoint. No boundary test. |
| Some restore domain/type/reference validation is incomplete before writes | Moderate integrity concern | Preview validates selected transaction references but not every field/relationship. SQLite constraints and transaction rollback catch some failures; semantic invalidity may remain. |
| Merge skips matching IDs without comparing content | Low–Moderate behavior concern | Source observed; preview reports matching-ID counts and UI says existing IDs are kept. |
| Structurally valid empty backup can be used for confirmed replacement | Low-frequency destructive-operation concern | Source observed; confirmation is required, but there is no non-empty guard. May be intentional. |
| Backup serialization lacks a cross-process snapshot transaction | Low, conditional consistency concern | In-process lock serializes this store’s writes; a separate process could write between table reads. Inference, not reproduced. |

Recommendations were to minimize plaintext preview data, align all size limits, validate all restored fields and relationships, clarify merge conflict semantics, expand synthetic malformed/size/reference tests, and use a consistent SQLite read transaction if cross-process writers must be supported. No recommendations were implemented in this review.

### Existing tests/checks

Test definitions cover encrypted round-trip, wrong passphrase, ciphertext tampering, rejected excessive scrypt parameters, preview/merge, repeated merge with the same IDs, rollback after a forced replacement insert failure, missing required fields, and HTTP rejection of replacement without typed confirmation. These tests were read but not run for this review.

Not covered in the reviewed test definitions: truncated/malformed archives, unsupported versions, invalid decrypted JSON structures, backup size boundaries, preview non-mutation assertion, full replacement success, conflicting same-ID content, all relationship/type validation, cross-process snapshot consistency, and crash/disk failure recovery.

## Review 4: Broader security review

### Status and method

**Complete; static/read-only source, configuration, documentation, and existing test-definition review.** No tests, app startup, scanner, network request, imported file, or backup operation was performed. No remediation was implemented by this review.

### Files and areas examined

- Server/request code: `main.py`
- Domain/SQLite code: `finance_core.py`
- Browser rendering and import/backup handling: `static/app.js`, `static/index.html`
- Caching and app metadata: `static/service-worker.js`, `static/manifest.webmanifest`
- Styles: `static/app.css`, `static/components.css`
- Dependency and ignore configuration: `requirements.txt`, `.gitignore`
- Project security assumptions: `README.md`, `docs/architecture.md`, `docs/implementation-plan.md`, `docs/wealth_app_guide.md`, `docs/baseline-report.md`, `wealth_app_build_spec.md`, `wealth_app_final_approved_instructions.md`
- Existing tests: `tests/test_finance.py`, `tests/test_import_parsing.py`, `tests/test_http_smoke.py`

### Confirmed safeguards

- `serve()` rejects non-loopback binding.
- POST/PATCH/DELETE handlers validate Host and, when present, Origin. Responses do not set permissive CORS headers.
- JSON parsing requires an object, JSON content type, valid UTF-8, positive declared content length, and a 12 MiB body limit.
- Responses include `no-store`, `nosniff`, CSP, referrer, and permissions policies. Request logging is suppressed; unexpected exceptions return generic errors.
- Static files use an explicit allowlist. Most SQL values are parameterized; dynamic table names in restore use fixed internal table names. SQLite foreign keys are enabled and writes use transactional locking/rollback.
- Dynamic UI text and attributes generally pass through `esc()`, while toasts/errors use `textContent`. CSV export applies formula-prefix protection. Import and PDF parser limits are in source.
- The service worker bypasses `/api/` and non-GET requests and only caches successful same-origin non-API GET responses. Current shell/static resources contain no financial data.
- No external runtime service/CDN use was found in reviewed frontend resources.

### Findings

| Severity | Finding | Evidence and qualification |
|---|---|---|
| **High** | Sensitive financial-data GET routes do not validate Host. | Confirmed: `do_GET()` serves `/api/bootstrap`, `/api/transactions`, `/api/reports`, and CSV export without `_check_origin()`. **Potential DNS-rebinding access is an inference and was not executed.** This could allow an attacker-controlled page to read API responses under DNS-rebinding conditions. |
| **Moderate** | Local API has no authentication; local callers are trusted by design. | Confirmed: no login or API authentication. Other local processes may access or change records while the service is running. |
| **Moderate** | PDF limits may not bound parser resources before text extraction. | Confirmed: extracted-text cap applies after parsing/extraction. Compressed content expansion causing resource exhaustion is a risk inference; no adversarial PDF was run. |
| **Moderate** | Backup preview returns decrypted payload and browser retains it. | Confirmed from source; see Review 3. Not dynamically measured. |
| **Moderate** | Backup creation and restore size limits may be inconsistent. | Confirmed from source; see Review 3. No size-boundary test was run. |
| **Low** | Restored category color is not fully validated before inline CSS insertion. | Confirmed: standard category create/update validation requires six-digit hex, but restore preview does not fully validate fields; UI escapes HTML but does not validate CSS syntax. A crafted archive’s CSS effects were not executed. |
| **Low** | Malformed GET pagination filters can return generic 500 responses. | Confirmed: integer conversion can raise and unexpected GET exceptions map to 500. No live request was made. |
| **Low** | Browser reads import files before server limits apply. | Confirmed: client reads selected file into memory before upload. High-memory behavior was not measured. |
| **Informational** | Live SQLite database is plaintext. | Confirmed by prior source review. Earlier permission observations apply only to the observed default path and were not rechecked in this review. Custom directory permissions remain unverified. |
| **Informational** | Dependency advisory status is unknown. | No local scanner was available in the dependency review; no upstream advisory lookup was performed. |

### Recommended remediation order

1. Apply Host validation to all API requests, including GET routes, and test unexpected Host values on data-returning endpoints.
2. Minimize decrypted backup data returned/stored during preview and establish consistent size limits across archive creation, browser handling, and restore.
3. Validate every restored field and relationship before writes, including category colors and transfer/budget references.
4. Add synthetic coverage for malformed/oversized backups, PDF resource limits, preview non-mutation, restore validation, and browser cross-origin behavior.
5. Add client-side file-size checks before loading large import files.
6. Treat local authentication/access control as a separate product boundary decision; loopback binding does not authenticate local callers.

No remediation was implemented by the broader review. It did not run tests, perform dynamic/browser testing, fuzz inputs, run a security scanner, or verify advisory status.

## Consolidated open findings and follow-up items

| Priority | Open item | Current evidence/status |
|---|---|---|
| 1 | Validate Host for all routes, especially data-returning GET endpoints | High source-level finding; DNS-rebinding path remains an untested inference. |
| 2 | Reduce plaintext backup preview exposure | Full payload response and browser state confirmed in source. |
| 3 | Align backup create/read/restore size limits | Limit mismatch inferred from confirmed body/base64 behavior; boundary untested. |
| 4 | Validate all restored fields and relationships, including category color | Partial validation confirmed; failure/impact cases not executed. |
| 5 | Bound and test PDF parser resource use before extraction | Existing byte/page/text limits confirmed; decompression/resource behavior untested. |
| 6 | Verify custom `WEALTH_APP_DATA_DIR` permissions and ancestors | Not verified; default path metadata only. |
| 7 | Consider file-size checks before browser import reads | Browser reads before server rejects; memory impact unmeasured. |
| 8 | Improve malformed GET filter status handling | Generic 500 behavior follows from source; no request executed. |
| 9 | Establish dependency advisory evidence and reproducible package resolution | No scanner/advisory lookup; requirements are range-constrained without lock/hashes. |
| 10 | Continue evaluating plaintext storage and local-caller trust boundary | Known architecture limitations; no change made in these reviews. |

## Review limitations and status

- Review 1 inspected filesystem metadata for the observed default database path only; custom data-directory and download-destination permissions remain unknown.
- Review 2 did not run an advisory scanner or verify current upstream advisories; dependency freedom from vulnerabilities is not established.
- Review 3 inspected source and existing test definitions but did not prove every recovery scenario safe.
- Review 4 was static/read-only; tests were not run, and the DNS-rebinding path and other inferred risks were not dynamically verified.
- No remediation is recorded as implemented by these four reviews. Their recommendations remain open unless addressed in a separately verified change.
- No live database contents, financial records, secrets, credentials, imported files, or backups were inspected for this document. No code/tests/configuration were changed and no tests were run while writing it.

## Live database protection design review

### Scope and status

**Read-only design review complete.** This section records design options and recommendations; it does not change the database, app, or macOS settings. The live database was not accessed, and neither the app nor tests were run.

### Current plaintext SQLite/WAL protection model

**Source-confirmed:** The app opens the live database through Python's standard `sqlite3` module and enables SQLite WAL mode. The app does not encrypt the live database. AES-GCM/scrypt encryption applies to downloaded `.wbackup` files only. The app attempts to set its data directory to `0700` and database file to `0600`; those operations are best-effort. SQLite creates WAL/SHM sidecars and the app does not explicitly set their modes.

**Prior permission observation, default path only:** `instance/` was `0700`; the main database and WAL were `0600`; SHM was `0644`, but protected from ordinary traversal by the private parent directory. These modes were not rechecked for this design review. Permissions for a custom `WEALTH_APP_DATA_DIR` and encryption of the browser's backup destination remain unverified.

### Protection options

| Option | Protects against | Does not protect against | Complexity and compatibility |
|---|---|---|---|
| macOS FileVault | Offline access to the internal disk while the Mac is locked or powered off, including loss/theft scenarios. | Processes and malware with access during an unlocked session; the logged-in user; unencrypted external copies/backups. | No app change. SQLite/WAL continue to work normally. FileVault status must be checked on this Mac; external backup encryption is separate. |
| Restrictive filesystem permissions | Ordinary access by other local accounts when ownership and permissions on the data directory and ancestors are restrictive. | Same-user processes, administrators/root, malware under the user's account, offline disk access without disk encryption, or copies made elsewhere. | Low app complexity and compatible with SQLite/WAL. Existing default-path observations were restrictive; custom path and sidecars need verification. Permissions are not encryption. |
| SQLite encryption library/extension | Plaintext database pages in copied files or offline disk images without the key; journal/WAL protection depends on the chosen implementation. | Access by the running app or malware able to use its key; in-memory data; plaintext exports/backups. | Moderate/high app and build changes. Python's standard `sqlite3` is not encrypted by itself. A compatible driver/build/extension, WAL behavior, backups, restore, macOS packaging, and Python 3.9 compatibility need evaluation. No current maintenance or compatibility research was performed. |
| Application-level encryption | Depends on design: selected field encryption can conceal fields in a file; an encrypted SQLite VFS/layer can protect database pages. | A wrapper that decrypts to a temporary plaintext database does not protect that working copy, WAL/SHM, crash copies, or backups. Field encryption does not protect data while unlocked. | High complexity if implemented directly. Field encryption complicates search, indexes, reports, and migrations. Do not implement custom cryptography; evaluate a maintained SQLite encryption layer if this option is selected. |
| Plaintext SQLite plus FileVault and encrypted backups | FileVault protects the internal disk while locked/offline; encrypted backups protect exported copies; permissions reduce ordinary access by other accounts. | Data while the Mac is unlocked, same-user malware/processes, and any unencrypted copy or backup. | Lowest complexity and best fit with current SQLite/WAL and backup workflow, assuming FileVault and backup destinations are verified. No app change is required. |

The maintenance status and current macOS/Python 3.9 compatibility of any candidate SQLite encryption package were not researched. SQLCipher was mentioned as a possible candidate only, not verified or endorsed by this review.

### Recommended approach for this single-user local app

**Recommendation, not an applied or verified fix:** Use macOS FileVault, a strong account password and short automatic-lock interval, the app's restrictive default data directory, and encrypted backups stored separately with the passphrase stored separately. Verify permissions if `WEALTH_APP_DATA_DIR` is used. This preserves the existing Python `sqlite3` and WAL architecture and avoids adding a database encryption dependency before its compatibility and key-management model have been evaluated.

FileVault status on this Mac was **not checked**. This document does not claim that FileVault is enabled or that real financial data is currently protected by it. Before entering real data, verify FileVault in **System Settings → Privacy & Security → FileVault** (or with the read-only `fdesetup status` command), and separately verify the encryption and permissions of backup destinations such as Time Machine or removable storage.

### Threats and residual risks

- FileVault and file permissions do not protect the database from the logged-in user, malware or processes running as that user, or administrators/root.
- The live database and active SQLite sidecars remain plaintext to the app and accessible to processes with sufficient user access.
- FileVault does not automatically protect external drives, cloud-synced copies, or other backup destinations; their encryption was not verified.
- Custom `WEALTH_APP_DATA_DIR` permissions and ancestor access remain unverified. App permission changes are best-effort and do not make the database encrypted.
- Encrypted backups depend on the user retaining the passphrase. Keeping it beside the archive weakens protection; losing it may prevent recovery.
- Ordinary deletion may not erase old plaintext copies from APFS snapshots, backups, or SSD media reliably.

### Migration considerations if live database encryption is adopted

1. Select an encryption implementation only after verifying maintenance, Python 3.9/macOS support, key handling, WAL/journal behavior, and integration with the current SQLite API. Do not roll a custom encryption scheme.
2. Test the encrypted connection path with synthetic data, including application operations, encrypted backup/restore, WAL recovery, and failure cases.
3. Make and verify an encrypted backup. Stop the app cleanly before migration; do not copy an active database as though it were a consistent snapshot.
4. Migrate into a separate new database file. Validate schema/version, record counts and relationships, SQLite integrity, and app-level results before cutover.
5. Keep the original plaintext file access-restricted and untouched until the new database and restore path are verified. Plan how to preserve writes made after cutover if rollback is needed; switching to a stale original could discard them.
6. Test recovery and key-loss procedures before removing old copies. Account for snapshots and external backups; deleting a file is not proof of secure erasure.

### Evidence, limitations, and items not verified

- **Source-confirmed:** Plaintext `sqlite3` database, WAL mode, separate encrypted-backup mechanism, best-effort directory/database modes, and configurable data directory.
- **Prior metadata observation:** Restrictive modes on the observed default path; not rechecked here.
- **Recommendation:** FileVault plus restrictive storage permissions and encrypted backups is the low-complexity default for this local single-user design.
- **Not verified:** FileVault status on this Mac; custom data-directory permissions; backup destination encryption; current encryption-library maintenance or compatibility; real-data protection in operation.
- No external sources were contacted, no package was installed, no settings were changed, and no live data was accessed.

**Overall review status:** Four security reviews and one database-protection design review documented; findings and recommendations remain open pending separately scoped decisions, remediation, and verification. **Phase 5: IN PROGRESS.**
