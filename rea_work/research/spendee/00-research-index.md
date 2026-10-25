# Spendee research index

**Last updated:** 2026-10-25  
**Research root:** `./rea_work/research/spendee/`  
**Privacy scope:** Generic UI structure and labels only. Exclude account-specific labels, balances, transaction details, bank data, credentials, and identifying financial information. Do not modify Spendee data or our app source.

## Status definitions

- **NOT STARTED:** No feature-specific page/workflow investigation yet.
- **IN PROGRESS:** Some relevant observations exist, but the agreed scope is incomplete.
- **BLOCKED:** Further investigation requires an unavailable tool, page, or external state change.
- **COMPLETED:** Investigation criteria are met; a page label alone is not enough.

## Current session state

- **OBSERVED (tool catalog):** REA MCP tools are exposed in this conversation, including `list_browser_targets`, `inspect_web_page`, `capture_browser_scenario`, and `export_evidence_bundle`.
- **BLOCKED (runtime):** REA `list_browser_targets` again returned `Transport closed`. Chrome's CDP endpoint `http://127.0.0.1:9222` is reachable from the host shell (verified with elevated `curl`; Chrome 156.0.8078.48), but not from the default sandbox shell. REA returned no target ID or page metadata. The local `rea` CLI is not installed, and no MCP restart/management tool is available in this conversation.
- **UNKNOWN:** Installed REA runtime version (including the requested 6.7.0) and live scenario schema could not be confirmed because the REA MCP transport is closed. The tool catalog exposes scenario arguments but types `actions` as an array of unknown variants; the official contract provides documented click/wait examples and CSS locators.
- **Next action:** Restore the REA MCP server transport. Then use REA launch mode or rediscover an existing target and execute one evidence-based scenario before feature research.

## Feature status

| Feature | Status | Pages inspected | Workflows inspected | Evidence collected | Unknowns remaining | Next recommended action | Report file |
|---|---|---|---|---|---|---|---|
| Dashboard and navigation baseline | IN PROGRESS | Dashboard at `/dashboard` in prior REA session; current page not independently verified | Passive accessibility inspection only | Target `ev_d67015d551fcda230be5df15c965b7dee17eaf8f5c32008a188498dc3e15afe3`; page inspection `ev_121e25c4903eea000bab194135db3a26ea1b6483cd46e428239ef58bfd7b2cda` | Current target, full page hierarchy and navigation | Restore REA/CDP; rediscover before inspecting | `01-feature-inventory.md`; dashboard notes in `02-wallets.md` |
| Wallets | BLOCKED | Dashboard wallet list was observed previously; wallet detail is user-reported but not inspected by REA | User reports manually opening a wallet; no wallet workflow observed by REA | Prior dashboard evidence `ev_121e25c4903eea000bab194135db3a26ea1b6483cd46e428239ef58bfd7b2cda`; current target listing failed with `Transport closed` | Detail layout, controls, associated activity, wallet type, management/settings, restrictions, privacy-safe field labels | Keep wallet detail open; restore REA/CDP; then rediscover and passively inspect | `02-wallets.md` |
| Budgets | NOT STARTED | Dashboard Budgets link label only | None | Dashboard accessibility evidence `ev_121e25c4903eea000bab194135db3a26ea1b6483cd46e428239ef58bfd7b2cda` | List/detail/create behavior, controls, restrictions | Investigate after Wallets | `03-budgets.md` (planned) |
| Transactions | NOT STARTED | None | None | None | Views, filters, creation/edit workflows, wallet relationships | Investigate after Wallets | `04-transactions.md` (planned) |
| Categories | NOT STARTED | None | None | None | Category views, controls, customization, restrictions | Investigate after Transactions | `05-categories.md` (planned) |
| Reports and overview | NOT STARTED | Overview heading only | None | Dashboard accessibility evidence `ev_121e25c4903eea000bab194135db3a26ea1b6483cd46e428239ef58bfd7b2cda` | Report types, data presentation, filters, export | Investigate after earlier feature work | `06-reports.md` (planned) |
| Recurring transactions | NOT STARTED | None | None | None | Presence, schedule controls, workflows, restrictions | Investigate only if a generic control is exposed | `07-recurring.md` (planned) |
| Sharing | NOT STARTED | None | None | None | Shared wallets, permissions, invitations, restrictions | Investigate only if a generic control is exposed | `08-sharing.md` (planned) |
| Settings | NOT STARTED | None | None | None | App settings, currency, sync, security and access | Investigate after feature navigation work | `09-settings.md` (planned) |
| Import and export | NOT STARTED | None | None | None | Supported formats, entry points, validation, restrictions | Investigate if generic controls are exposed | `10-import-export.md` (planned) |

## Requested autonomous queue

The requested research queue is tracked separately from the earlier feature breakdown. No feature was newly inspected in the current session because REA target discovery failed.

| Feature | Status | Pages inspected | Workflows inspected | Evidence collected | Unknowns remaining | Next recommended action | Report file |
|---|---|---|---|---|---|---|---|
| Wallets | BLOCKED | Existing dashboard notes only; wallet detail user-reported | None newly verified | Existing `02-wallets.md`; official REA docs reviewed | Current target, scenario execution, all wallet subviews | Restore REA MCP transport; rediscover target | `02-wallets.md` |
| Transactions | NOT STARTED | None | None | None | All requested UI and workflows | After Wallets | `03-transactions.md` |
| Categories | NOT STARTED | None | None | None | All requested UI and workflows | After Transactions | `04-categories.md` |
| Budgets | NOT STARTED | Dashboard link label only | None | Existing dashboard Evidence | Budget views and workflows | After Categories | `05-budgets.md` |
| Overview | NOT STARTED | Dashboard heading only | None | Existing dashboard Evidence | Overview sections and interactions | After Budgets | `06-reports.md` |
| Reports | NOT STARTED | None | None | None | Report pages, filters, exports | After Overview | `06-reports.md` |
| Import/export | NOT STARTED | None | None | None | Formats and safe workflow | After Reports | `07-import-export.md` |
| Settings | NOT STARTED | None | None | None | Settings and restrictions | After import/export | `08-settings-sync-backup.md` |
| Synchronization | NOT STARTED | None | None | None | Cross-device behavior and controls | After Settings | `08-settings-sync-backup.md` |
| Backup | NOT STARTED | None | None | None | Backup controls and formats | After Synchronization | `08-settings-sync-backup.md` |

## Session history

- **2026-10-25:** User reported Dashboard; REA target discovery failed with `Transport closed`, so the page was not inspected in that session.
- **2026-10-25:** User later reported opening one wallet from the dashboard wallet list; REA target discovery again failed with `Transport closed`, so the wallet detail page was not inspected.
- **2026-10-25:** Official browser observation, browser scenario contract, and runtime observation references were reviewed. REA MCP tool names and input metadata are present in the conversation catalog, but target discovery returns `Transport closed`; local `rea` CLI is absent. Runtime version and live target ID remain unverified. No Spendee navigation scenario was run.
- **2026-10-25:** Inspected the PyCharm MCP configuration: the enabled `rea` entry contains a server name but no local command, URL, or launch arguments. The documented REA launch-mode scenario was attempted with the installed Chrome executable and `https://app.spendee.com`; the MCP call failed immediately with `Transport closed`, before browser launch or page inspection. Chrome was not launched. No login state could be determined.
- **2026-10-25:** Following the user's approval to proceed, retried both the REA launch scenario and target discovery. Both still return `Transport closed`; no available tool can restart or reconfigure the IDE-managed MCP connection. Chrome remains unlaunched and login state remains unknown.
- **2026-10-25:** User launched Chrome and requested REA navigation. REA target discovery still returns `Transport closed`; `http://127.0.0.1:9222/json/version` refuses the connection, so this Chrome instance does not expose the expected CDP endpoint. No navigation or page inspection occurred.
- **2026-10-25:** User supplied a host-shell CDP response. Elevated verification from this environment confirms Chrome 156.0.8078.48 responds at `http://127.0.0.1:9222/json/version`; the default sandbox shell cannot reach the loopback endpoint. A fresh REA `list_browser_targets` call still returns `Transport closed`, so no Spendee target metadata or page content was inspected.

## Completion criteria

A feature is **COMPLETED** only after relevant pages, generic navigation/control labels, safe workflows, availability/restrictions, observable errors/empty states, and remaining unknowns are documented with REA evidence. Workflows that cannot be reached or safely observed remain **BLOCKED** or **UNKNOWN**, not completed.
- **2026-10-25, after “Continue research”:** User-reported wallet detail page remained the intended target, but the fresh REA target listing again failed with `Transport closed`. No page inspection occurred; Wallets remains BLOCKED.
