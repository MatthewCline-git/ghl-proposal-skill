---
name: ghl-proposal
description: Draft a client proposal from call notes and create it in GoHighLevel as a draft proposal document (from the user's template) or a priced estimate, by calling GHL's API directly with curl. Use when asked to write, generate, or send a proposal or estimate for a GHL client or prospect.
---

# GHL proposal (curl edition)

You draft the proposal and make every GHL call yourself with `curl`. No scripts, nothing to install. The API quirks below are already tested against a live account; follow them, don't rediscover them.

## Ground rules

- **Prices.** Every number on a proposal is on `rate_card.json` or was given to you by the user in this conversation. Never estimate, round or invent one. If a price is missing, ask.
- **Never print, echo or log the token.** Never put it in a message.
- **Drafts only.** Never send a document to a client. The user reviews it in GHL and presses Send. (Estimates may be sent only if the user explicitly says send.)
- **Get a yes before writing anything to GHL.** Show the dry run (step 3) first.
- **Report only what you verified,** and say what you could not verify.

## Setup (once)

`.env` next to this file with `GHL_TOKEN` and `GHL_LOCATION_ID`, plus a one-time proposal template named exactly `Proposal` (see `template/README.md`). If either is missing, walk the user through setup: the full guide is `ONBOARDING.md` at github.com/MatthewCline-git/ghl-proposal-skill.

**Rate card check.** If `rate_card.json`'s `_comment` still says SAMPLE, the prices are placeholders. Before the first proposal, tell the user and either get their real prices (rewrite the file with them) or get an explicit "use the sample prices for this test".

## Setup check

When asked to check setup (onboarding uses this), run these reads and report ✓ or ✗ for each, with the fix for any ✗ from the Failures table:
1. `GET $B/locations/$GHL_LOCATION_ID` → the business name.
2. `GET $B/contacts/?locationId=$GHL_LOCATION_ID&limit=1`
3. `GET $B/users/?locationId=$GHL_LOCATION_ID` → at least one user.
4. `GET $B/locations/$GHL_LOCATION_ID/customFields` → then create any of the five proposal fields that are missing (step 4 below); say you did.
5. `GET $B/proposals/templates?locationId=$GHL_LOCATION_ID&limit=20&skip=0` → a proposal template named `Proposal` exists.
A 401/403 on one read means that scope is missing from the token; name it (contacts, users, custom fields, Documents & Contracts).

## Calling GHL

Each Bash call is a fresh shell, so start every command with this (use the real path of this skill's folder):

```bash
cd "<this skill folder>" && set -a && . ./.env && set +a
B=https://services.leadconnectorhq.com
ghl() { curl -sS -H "Authorization: Bearer $GHL_TOKEN" -H "Version: 2021-07-28" -H "Content-Type: application/json" -w '\nHTTP %{http_code}\n' "$@"; }
```

Always read the `HTTP` status line. For request bodies, write JSON to a temp file with a quoted heredoc (`<<'JSON'`) and pass `--data @file`; escape quotes and use `\n` for line breaks inside strings. Don't pipe responses anywhere that could print the token (it is never in a response).

## Procedure: proposal document (default)

**1. Collect** client name, company, email (phone optional) and the call notes. If the notes don't say what was discussed, ask; don't invent scope.

**2. Draft** from `rate_card.json` (the user's default price list; use skus where they fit; add a custom line or override a price only with a number the user gave you). **Only include what the notes call for.** Never add scope they didn't discuss. If an item looks like a technical prerequisite of something they did ask for (for example texting setup for a text-back feature), leave it out and mention it in the dry run as a suggestion they can accept. Never add a sku just because it exists.
- `intro`: 2-3 plain sentences in the client's own words: what they told us and why this scope. No sales copy.
- deliverables: chosen items, each with an optional one-sentence note tying it to something they said.
- `assumptions`: only ones the notes support.

**3. Dry run.** Build the five field values below and show the user the priced lines (with where each price came from), the total, and the text. Wait for a yes, unless the user has already told you to proceed.

| custom field (key) | dataType | value |
|---|---|---|
| Proposal intro (`contact.proposal_intro`) | LARGE_TEXT | the intro |
| Proposal scope (`contact.proposal_scope`) | LARGE_TEXT | one line per deliverable: `Name ($1,250): <rate card description> <your note>`. Prices use thousands commas, no cents if whole; if qty > 1 write `($1,250 for 2)` with the line total. Drop the note if it just repeats the description. Join lines with `\n`. |
| Proposal total (`contact.proposal_total`) | TEXT | `$3,500` (no cents if whole) |
| Proposal terms (`contact.proposal_terms`) | LARGE_TEXT | the rate card `terms` (skip a term whose `only_with` sku isn't on the proposal), then `Assumes: ...` per assumption; joined with `\n`. The user may replace the terms for one proposal, e.g. a free deal. |
| Proposal valid through (`contact.proposal_valid_through`) | TEXT | today + `valid_days` in the **user's local date** (`date +%F`, not UTC), written as `October 3, 2026` |

**4. Look up ids** (all reads):
- Custom fields: `ghl "$B/locations/$GHL_LOCATION_ID/customFields"` (under `customFields`) → match `fieldKey` to the five keys above and note each `id`. Create any missing one: `POST $B/locations/$GHL_LOCATION_ID/customFields` with `{"name":"Proposal intro","dataType":"LARGE_TEXT","model":"contact"}` (response `customField.id`).
- Template: `ghl "$B/proposals/templates?locationId=$GHL_LOCATION_ID&limit=20&skip=0"` (the list is under `data`) → the entry with `"type":"proposal"`, `"deleted":false` and name `Proposal` (case-insensitive) → its `_id`. If none, stop: the template isn't built (`template/README.md`).
- User id: `ghl "$B/users/?locationId=$GHL_LOCATION_ID"` (the list is under `users`) → `users[0].id`.

**5. Contact.** `POST $B/contacts/upsert` with `{"locationId":"...","name":"...","email":"...","companyName":"...","phone":"..."}` (omit `phone` if unknown) → `contact.id`. Upsert matches on email, so it's safe to repeat.

**6. Write the fields.** `PUT $B/contacts/<contactId>` with `{"customFields":[{"id":"<fieldId>","field_value":"..."}, ...five...]}`. Then `GET $B/contacts/<contactId>` and confirm each of the five values in `contact.customFields[]` (`id`, `value`) is exactly what you wrote. If any differ, stop and report.

**7. Create the draft, once.**
1. First check nothing was already created for this client in this run: `ghl "$B/proposals/document?locationId=$GHL_LOCATION_ID&limit=20&skip=0"` (the list is under `documents`; every one is named `Proposal`, so match on the contact). A document with this contact's id in `recipients[].id` and `createdAt` within the last 10 minutes means it already exists. Use it; do not create another. Read `skip=20`, `skip=40` too if the whole page is that recent. **Skip this check** only if the user explicitly asked for a second proposal for the same client.
2. Otherwise: `POST $B/proposals/templates/send` with `{"templateId":"...","userId":"...","locationId":"...","contactId":"...","sendDocument":false}` → `document._id`. **`sendDocument` must be `false`.**

**8. Verify** (do all; don't skip):
- The document appears in the list from 7.1 with `"status":"draft"` and the contact in `recipients`.
- The stored copies: the create response has a `document.versionHistory` array (currently two entries a fraction of a second apart). Fetch **every** entry's `downloadUrl` with plain `curl -sS "<url>"` (no auth header). Each must contain all five `{{contact.proposal_...}}` placeholders and a node with `"type":"Signature"`. If a placeholder is missing, the template was edited wrongly; say so.
- The API cannot show how the merge renders. **Tell the user to open it** (Payments > Documents & Contracts > Documents), check the names and text filled in, the layout, and that the signature is on its own page, then send.

**9. Log the run.** Append one line: `echo "$(date -u +%FT%TZ) | ok | <company> (<contact name>) | <total> | doc <id>" >> runs.log` (or `failed | <what>`). Times in this log are UTC.

## Failures

- **Retry** (max 3 times, waiting 2s, 4s, then 8s with `sleep`): HTTP 429, 5xx, a network error, **or a 401 whose message says "timed out"** (GHL's gateway sometimes reports a backend timeout as a 401; the token is fine). Before retrying any create, re-run the existence check in 7.1: a 5xx can hide a write that succeeded.
- **Stop and tell the user, no retry, no workaround:** any other 4xx. Give the exact error and the fix:

| you see | meaning / fix |
|---|---|
| 401 / 403 (not "timed out") | token invalid, revoked, or missing a scope. Edit or recreate it in the sub-account: Settings > Private Integrations. It needs: contacts.readonly, contacts.write, locations.readonly, users.readonly, locations/customFields.readonly, locations/customFields.write, all Documents & Contracts entries (documents and templates), and for estimates invoices/estimate.readonly and invoices/estimate.write. |
| 401 "Location is not active" | the sub-account is deactivated (e.g. an expired trial) or the token belongs to another location. |
| 422 "title/name must be shorter than or equal to 40 characters" | estimates only: shorten it. |
| 422 "limit must not be greater than 21" | list calls: use `limit=20`. |
| 400 "Estimate number already exists" | pick another `estimateNumber`, or omit it. |

- If a run fails midway, report which steps completed (contact, fields, document) and that re-running is safe: upsert is idempotent and step 7.1 prevents a duplicate.
- Nothing watches for failures when you're not in the session; the user finds out because you tell them. Say so if they ask about alerts.

## Procedure: estimate (only if the user asks for an estimate)

Same steps 1-3 (no custom fields or template). Then:

1. Contact: step 5.
2. `POST $B/invoices/estimate` with:
   `altId` = location id, `altType` `"location"`, `liveMode` `true`, `currency` `"USD"`, `name` and `title` (**each 40 characters max**; put a run id like `p-1a2b3c4d` in `name` and in `meta`: `{"runId":"p-1a2b3c4d"}`), `businessDetails` `{"name":"<location name>"}`, `contactDetails` `{"id","name","email","phoneNo":"","companyName"}`, `items` `[{"name","description","currency":"USD","amount":750,"qty":1,"type":"one_time"}]`, `discount` `{"type":"percentage","value":0}`, `frequencySettings` `{"enabled":false,"schedule":{}}`, `termsNotes` (HTML: intro, assumptions, terms), `userId`, `issueDate` and `expiryDate` (**required**, `YYYY-MM-DD`), optional `estimateNumber` (integer; must be unused).
3. Idempotency: before creating, `GET $B/invoices/estimate/list?altId=$GHL_LOCATION_ID&altType=location&limit=20&offset=0&search=<runId>` and look for `meta.runId`.
4. Verify from that same list: right contact, `total` equals your sum, items match, `estimateStatus` is `draft`. There is no get-by-id endpoint.
5. Link: `https://app.gohighlevel.com/v2/location/$GHL_LOCATION_ID/payments/v2/estimates/edit/<estimateId>`.
6. Send only on an explicit yes: `POST $B/invoices/estimate/<id>/send` with `{"altId","altType":"location","action":"email","liveMode":true,"userId","estimateName"}`. Refuse placeholder addresses (`example.com` etc.).

## Cleaning up test data

There is no API to delete documents; the user deletes them in the GHL UI. Estimates: `DELETE $B/invoices/estimate/<id>` with body `{"altId":"...","altType":"location"}`.
