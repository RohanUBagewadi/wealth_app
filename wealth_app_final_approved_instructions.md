# wealth_app --- Final Approved Instructions for Remaining Work

## Purpose

This is the **final agreed instruction document** for continuing
`wealth_app`.

Use it together with the project's existing `implementation-plan.md`,
current source code, and existing documentation.

### Final decisions approved by the user

-   Keep the app **local-first**.
-   Do **not** implement hosted sync, cloud accounts, authentication,
    pCloud OAuth, or automatic uploads now.
-   Keep manual encrypted backup/restore as the supported backup
    approach.
-   Finish the remaining hardening and reliability work.
-   Prepare a stable local-first release.
-   Preserve the original implementation plan's phase numbers, titles,
    order, and completed status. Do not invent or renumber development
    phases. Git setup and testing/push approval are workflow
    requirements, not phases.
-   Work on one existing phase at a time. Introduce it, ask for
    approval, implement it, test it, review with the user, and ask for
    push approval. Never push automatically.

## Project constraints

The app is a local-first personal finance application using Python 3.9
standard-library HTTP server, SQLite, and vanilla HTML/CSS/JavaScript.

-   Keep the server bound to `127.0.0.1`; do not expose it to the
    network.
-   SQLite live data is plaintext. Do not describe the database as
    encrypted at rest.
-   Encrypted backups use the existing AES-GCM/scrypt implementation.
-   Use synthetic data for all tests and demos.
-   Do not commit real financial records, statements, exports, database
    files, database sidecars, backup files, passwords, credentials, or
    encryption keys.
-   No bank scraping, bank connectivity, hosted sync,
    analytics/telemetry, or new dependencies without explaining and
    asking the user first.
-   pCloud remains manual encrypted file transfer only; no OAuth/API
    integration is approved.
-   Keep imports local and staged for review before applying.
-   PDF import remains limited to supported selectable-text layouts; no
    OCR or external processing is approved.

------------------------------------------------------------------------

# Final scope by original plan phase

**Before acting, inspect the actual `implementation-plan.md` and
repository. Use its exact phase titles and numbering in every report.**
The scope decisions below are approved, but do not rename original
phases to match this document. If the existing plan assigns
backup/restore or hardening to a different phase than the shorthand
below, keep the original assignment and place the work under the
original phase title.

## Existing Phase 4 --- Sync/Auth (decision: defer hosted sync)

### Approved outcome

Keep the application local-first. **Do not build hosted sync or
authentication in this work.**

### Do

-   Verify the current app's local-only behavior and document it
    accurately.
-   Confirm the app does not falsely advertise sync or cloud accounts.
-   Document that manual encrypted backups are the available
    transfer/recovery method.
-   Record hosted sync/auth as deferred future work, not a current
    release requirement.
-   If useful, provide a short future-decision note listing unresolved
    sync questions, without implementing them.

### Do not

-   Add server-side accounts, login, sessions, hosted APIs, cloud
    database, remote sync, offline sync queue, conflict resolution,
    pCloud OAuth, or automatic upload.
-   Add a deployment/hosting setup.
-   Change local data architecture to prepare for sync without approval.

### Checks

-   Verify server loopback binding.
-   Verify local app startup and existing local functionality.
-   Review documentation and UI for misleading sync/cloud claims.
-   Confirm no new external runtime requests or remote services were
    introduced.

### Acceptance

The app remains local-first; sync/auth are explicitly deferred; existing
local functionality remains intact. Do not push until the phase review
and user approval.

## Existing Phase 5 --- Backup/Restore (finish and verify)

### Goal

Complete and verify safe encrypted backup/restore behavior while
retaining manual encrypted backup.

### Tasks

-   Inspect current backup and restore code and the original plan's
    outstanding items.
-   Verify backup creation and restore behavior end-to-end.
-   Confirm restore validates the file and password before altering
    existing data.
-   Review wrong-password, invalid-format, corrupt/tampered backup, and
    failed restore behavior.
-   Verify a restore does not unexpectedly overwrite or corrupt local
    records.
-   Make restore confirmation and error messages understandable.
-   Confirm backup files and local databases are excluded from Git.
-   Keep pCloud manual; no direct integration.

### Tests

-   Synthetic-data backup → restore → verify records round-trip.
-   Wrong password.
-   Modified/tampered backup.
-   Corrupt or invalid backup format.
-   Restore failure and preservation of existing data.
-   Relevant persistence and regression tests.
-   Python compilation and applicable API/loopback smoke tests.

### Acceptance

Backup/restore behavior is documented and tested; unsafe restore
failures are handled; synthetic records round-trip correctly; private
files remain out of Git. Present results and ask before
committing/pushing.

## Existing Phase 6 --- Hardening (finish remaining work)

### Goal

Improve security, correctness, privacy, resilience, and usability
without adding unrelated features.

### Priority work

1.  **CSV formula injection**
    -   Apply safe export handling to all user-controlled fields,
        including description/note, wallet, category, and any other
        exported text.
    -   Test formula-like values and ensure CSV quoting and escaping are
        correct.
2.  **Import validation**
    -   Test malformed, oversized, unusual, empty, and invalid CSV/PDF
        inputs.
    -   Preserve staged review before applying.
    -   Ensure canceling review does not write records.
    -   Clearly explain unsupported PDF layouts; no OCR.
3.  **Persistence integrity**
    -   Review transaction boundaries and partial-failure behavior.
    -   Test create/update/delete/reload for affected data.
4.  **Privacy and local security**
    -   Review logs/errors for financial payloads, passwords, keys, or
        sensitive file contents.
    -   Check input limits and request validation.
    -   Confirm loopback-only binding and local-only behavior.
    -   Verify no telemetry or external runtime calls.
    -   Confirm Git ignore rules cover database, sidecars, backups,
        statements, exports, secrets, and local config.
5.  **UI and accessibility**
    -   Review keyboard use, focus states, accessible labels, contrast,
        responsive layouts, empty/error states, and archive/delete
        clarity.
    -   Fix only issues in existing hardening scope. Do not add new
        product features or redesign unrelated screens.
6.  **Documentation accuracy**
    -   Document actual supported import/export behavior, local data
        location, plaintext database limitation, encrypted backup
        behavior, manual pCloud transfer, and known limitations.
7.  **Dependencies**
    -   Review dependencies currently used. Do not add or upgrade
        packages without explaining and asking first.

### Tests

-   Formula-like CSV values in every user-controlled export field.
-   CSV quote/newline/Unicode/empty-value cases.
-   Valid, malformed, oversized, and unsupported import files.
-   Import review commit and cancel behavior.
-   Persistence and transaction consistency.
-   Regression tests for transactions, wallets, categories, budgets,
    reports, and dashboard as applicable.
-   Backup/restore tests from the existing backup phase where hardening
    touches them.
-   Python compilation.
-   JavaScript syntax checks.
-   Loopback/API smoke test.
-   Privacy and Git scan.

### Acceptance

Hardening items are fixed or clearly documented; relevant functionality,
feature, regression, and failure tests pass; local-first behavior is
preserved; no private data or secrets are staged. Ask the user before
pushing.

## Final release readiness (final wrap-up after the original phases)

This is a **release-readiness checklist**, not permission to change
original phase numbering or create a new development phase. Complete it
after the relevant original work has passed review.

### Tasks

-   Update README and user guide to reflect actual behavior and setup.
-   Verify clean setup/start instructions.
-   Document local database location and the fact that SQLite is
    plaintext.
-   Document supported CSV/PDF import behavior and limitations.
-   Document encrypted backup/restore and manual pCloud transfer.
-   Explicitly state that hosted sync/auth is not supported in this
    release.
-   Review known limitations, errors, recovery guidance, and
    version/change notes.
-   Verify no sensitive sample data or files are tracked.
-   Do not deploy or host the app.

### Final checks

-   Fresh setup/startup smoke test following the documentation.
-   Full existing test suite.
-   Functionality tests for critical flows: transactions, wallets,
    categories, budgets/reports, import review/commit/cancel, export,
    backup, restore.
-   Feature and regression tests.
-   Python compilation and JavaScript syntax checks.
-   Loopback/API smoke check.
-   Privacy/Git review.
-   Confirm all test data is synthetic.

### Release acceptance

Documentation matches implementation; critical local workflows pass;
known limitations are explicit; no private data is tracked; sync/auth
remains deferred. Present a final review and wait for explicit approval
before any release commit/push.

------------------------------------------------------------------------

# Mandatory Git, test, and push workflow

## Git setup prerequisite (not a development phase)

-   Inspect `git status`, current branch, and remote before modifying
    Git.
-   Preserve existing setup; do not overwrite remotes.
-   Ensure `.gitignore` excludes virtual environments, Python caches,
    IDE-local files, `instance/`, SQLite files and sidecars, `.wbackup`,
    real statements/exports, `.env`, secrets, keys, logs, and
    `.DS_Store`.
-   If GitHub remote setup is missing or ambiguous, explain and ask
    before configuring it.
-   Never stage or commit private financial data.

## For every phase, in this exact order

1.  **Introduce** the original phase using its exact title and number.
    Explain current status, scope, risks, acceptance criteria, and
    planned tests.

2.  **Ask for approval to start.** Wait for user approval.

3.  **Implement only that phase.**

4.  **Run tests before asking to push:**

    -   functionality tests for the actual changed flow
    -   feature tests for normal cases, validation, empty states, and
        edge cases
    -   regression tests for related existing features
    -   applicable Python compile, JavaScript syntax, API/loopback,
        import/export, persistence, backup/restore, and security checks

5.  **Report exact commands and results.** Do not claim tests passed
    unless they ran. List failures, skips, and limitations. Fix and
    rerun affected tests.

6.  **Present review:** behavior, files changed, test results, known
    issues, privacy/Git review, and `git diff` summary. Do not push yet.

7.  **Ask for explicit push approval** using this wording:

    **"Phase \[original number\] --- \[original title\] is implemented
    and tested. Do you approve committing and pushing these reviewed
    changes to GitHub?"**

8.  **Wait.** If user declines, do not commit or push; make requested
    changes, retest, review again, and ask again. Passing tests is not
    permission.

9.  If approved, commit and push only reviewed changes. Do not merge to
    `main` unless separately approved. Report branch, commit hash, and
    push result.

10. Only after that, introduce the next original phase and ask before
    implementation.

## Git review commands

Before any commit: - `git status` - `git diff` - `git diff --cached` -
verify branch and remote - inspect staged files for database/sidecar,
backup, statements, exports, secrets, keys, and private finance data -
verify the phase's required tests were run - show the review and obtain
approval

## Required phase report

-   Original phase number and exact title
-   Status (complete / partial / blocked)
-   Scope and files changed
-   Functionality tests: command and result
-   Feature tests: command and result
-   Regression tests: command and result
-   Other checks: command and result
-   Failures, skipped tests, and limitations
-   Privacy/Git review
-   Diff summary
-   Explicit ask for commit/push approval

**Do not push automatically. Do not start the next phase until the user
approves.**
