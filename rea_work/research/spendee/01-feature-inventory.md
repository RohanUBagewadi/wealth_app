# Spendee feature inventory

**Summary:** Passive inspection of the logged-in Spendee dashboard exposed Dashboard and Budgets navigation links, plus Wallets and Overview headings in the accessible interface. No other requested feature categories were confirmed from visible navigation, and access restrictions cannot be determined without opening sections. Account-specific labels and financial data are intentionally omitted.

- **Date of research:** 2026-10-25
- **Spendee page inspected:** `https://app.spendee.com/dashboard` (page title: “Dashboard | Spendee.com - See where your money goes.”)
- **Site identification:** The page is on the `app.spendee.com` subdomain of `spendee.com` and carries Spendee branding; identified as Spendee's app page.
- **Method and scope:** REA `list_browser_targets` followed by passive `inspect_web_page` on the selected CDP target. No clicks, navigation, form submissions, screenshots, or state changes were performed. Accessibility labels were limited to generic UI terms for this report.

| Category | Feature name | Where it appears | Visibly available | Access restriction or uncertainty | Suggested follow-up investigation |
|---|---|---|---|---|---|
| Accounts / wallets | Wallets | Accessible heading on the dashboard; not confirmed as a navigation link | Yes, as a heading | Whether all wallet actions or wallet types are available is unclear; no section was opened. | With approval, passively inspect the Wallets view and record only generic controls and labels. |
| Budgets | Budgets | Accessible navigation on the dashboard | Yes, as a navigation label | Budget details, creation, and any plan restrictions are unclear; no section was opened. | With approval, passively inspect the Budgets view, avoiding account-specific amounts and names. |
| Dashboard | Dashboard | Accessible navigation and current page title | Yes | Dashboard contents beyond generic navigation were not evaluated. | With approval, continue passive inspection with personal and financial values excluded. |
| Dashboard / overview | Overview | Accessible heading on the dashboard | Yes, as a heading | The scope of this overview is unclear; no section was opened. | With approval, passively inspect the Overview view while filtering out personal and financial data. |
| Transactions | Not observed | No generic transaction navigation label confirmed in the accessible labels inspected | Unclear | The page may expose this elsewhere, but its presence or availability was not established. | Inspect only if a generic Transactions control is visibly exposed in a later approved passive review. |
| Categories | Not observed | No generic category navigation label confirmed | Unclear | Presence and availability are not established. | Check for a generic category control in a later approved passive review. |
| Reports | Not observed | No generic reports navigation label confirmed | Unclear | Presence and availability are not established. | Check for a generic reports control in a later approved passive review. |
| Recurring transactions | Not observed | No generic recurring-transaction navigation label confirmed | Unclear | Presence and availability are not established. | Check for a generic recurring control in a later approved passive review. |
| Sharing | Not observed | No generic sharing navigation label confirmed | Unclear | Presence and availability are not established. | Check for a generic sharing control in a later approved passive review. |
| Settings | Not observed | No generic settings navigation label confirmed in the accessible labels inspected | Unclear | Presence and availability are not established. | Check for a generic settings control in a later approved passive review. |
| Import / export | Not observed | No generic import or export navigation label confirmed | Unclear | Presence and availability are not established. | Check for generic import/export controls in a later approved passive review. |

## Privacy and evidence limits

This report does not include balances, transaction amounts or descriptions, account or bank details, wallet-specific names, or other personal financial information. REA reported partial, policy-filtered coverage; attachment state was unknown, and some origins or sections were excluded. “Not observed” means only that a generic label was not confirmed in this passive inspection; it does not establish that the feature is absent or locked.
