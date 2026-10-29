---
layout: default
title: Privacy Policy — budget-familiare
permalink: /privacy/
---

# Privacy Policy — budget-familiare

**Effective date:** October 25, 2026
**Last updated:** October 25, 2026

## 1. Scope

This Privacy Policy describes how **budget-familiare** (the "Application") accesses,
uses, stores and shares data, including data obtained from Google APIs. The
Application is an open source plugin for [Hermes Agent](https://hermes-agent.nousresearch.com)
that records household expenses and income in a Google Sheets spreadsheet chosen by
the user. Its source code is available at
<https://github.com/l33tleandrew/budget-familiare>.

## 2. Who is responsible

The Application is developed by Andrea Loprieno (the "Developer").

The Application is **self-hosted**: it runs only on the Hermes Agent instance that
the user installs and operates. The Developer operates no servers, databases,
analytics or telemetry for the Application and never receives, accesses or stores
user data. Each user who runs the Application controls the data it processes.

## 3. Data the Application accesses

### 3.1 Google user data

The Application requests the following OAuth 2.0 scope:

| Scope | Purpose |
|---|---|
| `https://www.googleapis.com/auth/spreadsheets` | Append a row to the spreadsheet configured by the user, and check during setup that the spreadsheet and its sheet exist |

The Application uses this scope for two operations: appending one row to the
configured sheet, and, only when the person installing it runs the setup check
(`setup_google.py verifica`), reading the configured spreadsheet's title and the
names of its sheets to confirm the configuration is correct. It does not read
spreadsheet contents (cell values), modify or delete existing rows, access other
spreadsheets, or access Google Drive, Gmail, contacts or account profile information.
The only data it receives from Google APIs is the confirmation of the write (the cell
range of the appended row) and, during the setup check, the spreadsheet's title and
sheet names, which are shown on the installer's terminal and not stored.

### 3.2 Data provided by the user

To record a transaction, the user provides its details in conversation: date, type
(expense or income), category, subcategory, amount, description and notes.

### 3.3 Data not collected

The Application does not use cookies, analytics, advertising identifiers or any
other tracking technology, and does not collect location, device or usage data.

## 4. How data is used

Data is used solely to provide the Application's user-facing feature: guiding the
user through recording a transaction and writing it to the user's own spreadsheet.
Access to Google user data is based on the consent the user grants through Google's
OAuth consent screen, which can be withdrawn at any time (see section 9).

The Application does not use data for advertising, profiling or automated
decision-making.

## 5. Storage and retention

All data remains on the user's machine or in the user's Google account:

| Data | Location | Retention |
|---|---|---|
| OAuth client credentials (`google_client_secret.json`) | Profile directory of the user's Hermes instance | Until the user deletes them |
| OAuth access and refresh tokens (`google_token.json`) | Profile directory of the user's Hermes instance | Until the user revokes access or deletes the file |
| Pending authorization (`budget_oauth_pending.json`, a one-time PKCE verifier) | Profile directory of the user's Hermes instance | Deleted when the authorization completes |
| Draft of the transaction in progress | Profile directory of the user's Hermes instance, or the system temporary directory if that is unavailable | Deleted when the transaction is recorded or after 15 minutes of inactivity |
| Recorded transactions | The user's Google Sheets spreadsheet | Under the user's control |

## 6. Sharing and disclosure

The Application does not sell, rent, transfer or share data with the Developer or
with any third party. Its only network requests are made to Google
(`oauth2.googleapis.com` and `sheets.googleapis.com`).

The messages the user writes to record a transaction are processed by Hermes Agent
and by the language model provider and messaging channel the user has configured
in their own instance. These services are selected and operated by the user and are
governed by their own privacy policies. The Application does not transfer data
obtained from Google APIs to them, except for the write confirmation described in
section 3.1.

## 7. Security

Communication with Google APIs is encrypted in transit over HTTPS. OAuth tokens are
stored only on the user's instance and are never transmitted to the Developer. The
transaction draft is written atomically with permissions restricted to the owning
system user (`0600`). Users are responsible for securing the machine and accounts
on which they run the Application.

## 8. Google API Services User Data Policy

budget-familiare's use and transfer to any other app of information received from
Google APIs will adhere to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements. In particular, data obtained from Google
APIs:

- is used only to provide or improve the user-facing feature described in section 4;
- is not transferred to others, except as necessary to provide that feature, to
  comply with applicable law, or as part of a merger, acquisition or sale of assets
  with notice to users;
- is not read by humans, except with the user's affirmative consent, for security
  purposes, to comply with applicable law, or when aggregated and anonymized for
  internal operations;
- is not used for advertising, is not sold, and is not used to develop, improve or
  train generalized artificial intelligence or machine learning models.

## 9. Your rights and choices

- **Revoke access:** remove the Application's access to your Google account at any
  time at <https://myaccount.google.com/permissions>.
- **Delete data:** delete `google_token.json` and the transaction draft from your
  Hermes instance; edit or delete recorded rows directly in Google Sheets.
- **Data protection rights:** if you are in the European Economic Area, you have
  the rights of access, rectification, erasure, restriction, portability and
  objection under the GDPR. Because the Developer holds no data about you, these
  rights are exercised directly on your own instance and Google account. You also
  have the right to lodge a complaint with a supervisory authority, such as the
  Italian [Garante per la protezione dei dati personali](https://www.garanteprivacy.it).

## 10. International data transfers

The Developer does not transfer user data. Data sent to Google, and to any language
model provider the user chooses, may be processed outside the user's country under
those providers' own terms and safeguards.

## 11. Children

The Application is not directed to children under 16 and does not knowingly
process their data.

## 12. This website

This page is hosted on GitHub Pages. GitHub may collect technical information about
visitors, such as IP addresses, as described in the
[GitHub General Privacy Statement](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement).

## 13. Changes to this policy

Changes are published on this page with an updated "Last updated" date. The full
revision history is available in the project repository.

## 14. Contact

For questions or requests about this Privacy Policy or your data, contact the
Developer at <itsmypersonalagent@gmail.com>.
