---
name: ghl-proposal
description: Draft a client proposal from call notes and create it in GoHighLevel as a draft proposal document (from the user's template) or a priced estimate, by calling GHL's API directly with curl. Use when asked to write, generate, or send a proposal or estimate for a GHL client or prospect.
---

# GHL proposal (curl edition)

You draft the proposal and make every GHL call yourself with `curl`. No scripts, nothing to install. The API quirks below are already tested against a live account; follow them, don't rediscover them.

## Ground rules

- **Prices and terms come from the user.** Every number and term on a proposal was given to you by the user in this conversation (or is a saved default in `defaults.json`). Never estimate, round or invent one. If it's missing, ask.
- **Never print, echo or log the token.** Never put it in a message.
- **Drafts only.** Never send a document to a client. The user reviews it in GHL and presses Send. (Estimates may be sent only if the user explicitly says send.)
- **Get a yes before writing anything to GHL.** Show the dry run (step 2) first.
- **Report only what you verified,** and say what you could not verify.

## Setup (once)

`.env` next to this file with `GHL_TOKEN` and `GHL_LOCATION_ID`, plus a one-time proposal template named exactly `Proposal` (see `template/README.md`). If either is missing, walk the user through setup: the full guide is `ONBOARDING.md` at github.com/MatthewCline-git/ghl-proposal-skill.


## Setup check

When asked to check setup (onboarding uses this), run these reads and report ✓ or ✗ for each, with the fix for any ✗ from the Failures table:
1. `GET $B/locations/$GHL_LOCATION_ID` → the business name.
2. `GET $B/contacts/?locationId=$GHL_LOCATION_ID&limit=1`
3. `GET $B/users/?locationId=$GHL_LOCATION_ID` → at least one user.
4. `GET $B/locations/$GHL_LOCATION_ID/customFields` → then create any of the five proposal fields that are missing (step 3 below); say you did.
5. `GET $B/proposals/templates?locationId=$GHL_LOCATION_ID&limit=20&skip=0` → a proposal template named `Proposal` exists.
A 401/403 on one read means that scope is missing from the token; name it (contacts, users, custom fields, Documents & Contracts).

## What a proposal needs

Exactly what the template merges in, and nothing else:

| item | source |
|---|---|
| client name, company, email (phone optional) | the user |
| **intro**: what they told us and why this scope | the user's notes; you write it |
| **scope**: what will be delivered, one line each | what the user says they'll deliver; you word the lines. A client's problems alone are not a scope |
| **total**: one price | the user, verbatim; 0 is fine |
| **terms**: how they get paid, anything else standard | the user, verbatim, or saved defaults in `defaults.json`. An empty `terms` list there means none are saved: ask |
| **valid for** N days | the user, else `defaults.json` (14) |

## Intake: ask once, all up front

0. **Preflight.** Confirm the `.env` next to this file exists and has both keys set (never print it). If not, stop and go to Setup before asking anything.
1. Pull everything above out of the user's message. Raw call notes are the input for the intro; don't make them restate them. If they only described the client's problems, you still need what they will deliver.
2. If anything is missing, send **one** message: a line on what you already have, then only the missing items as a short numbered list with an example each (e.g. "Total price, one number: 3,500"). Examples only show the format; say so, and never treat a "yes" or silence as accepting an example. If you'd like to help with scope, you may offer suggested lines clearly labelled as your suggestion, but use them only if the user says yes. State the validity default in one clause instead of asking. Say one free-form reply covering all of it is fine. Never ask one question at a time, and don't start creating anything until you have it all.
3. Never invent a price, a term, a deliverable or a client detail. A missing price or term is a question, not a guess.
4. If the client's email looks like a placeholder (`example.com`, `.test` and the like), point it out once in case it's a typo. Documents are always drafts, so proceed if they confirm.

## Edit their input

Their wording will be rough. Turn it into proposal-ready text:
- **intro**: 2-3 plain sentences addressed to the client by first name ("Priya, you told us..."): what they said and why this scope. Paraphrase faithfully; don't invent quotes or sharpen their claims. No sales copy.
- **scope**: one plain deliverable per line, worded from what the user said they'll deliver. Don't add channels, timing, cadence or detail they didn't state; if a line is too vague to be a deliverable, ask about it in the intake message.
- **terms**: tidy the wording and punctuation only. "Half up front" may become "50% due up front" (same number). Never compute or add an amount (like "$2,250"), a condition or a term they didn't state, and use exactly the terms they gave (no "standard" extras).

You may fix grammar, tighten, reorder and drop chatter. You may **not** change the meaning, change a number, or add a commitment, deliverable or assumption they didn't state. The total is verbatim. **If a phrase is ambiguous** (for example "when it's live", "after we start"), keep their meaning as written and flag it in your note ("I read 'after we start' as 'once work has started'; tell me if not") instead of quietly resolving it.

**The dry run** is the formatted text the client will see (intro, scope, total, terms, valid-through), then one line on what you changed and any phrase you flagged. It needs no GHL calls; make the lookups only after the user says yes. If they want it different, edit and show again.

After the first successful proposal, offer once to save their terms (and validity period) as defaults in `defaults.json` so they don't have to say them again.

## Calling GHL

Each Bash call is a fresh shell, so start every command with this (use the real path of this skill's folder):

```bash
cd "<this skill folder>" && set -a && . ./.env && set +a
B=https://services.leadconnectorhq.com
ghl() { curl -sS -H "Authorization: Bearer $GHL_TOKEN" -H "Version: 2021-07-28" -H "Content-Type: application/json" -w '\nHTTP %{http_code}\n' "$@"; }
```

Always read the `HTTP` status line. For request bodies, write JSON to a temp file with a quoted heredoc (`<<'JSON'`) and pass `--data @file`; escape quotes and use `\n` for line breaks inside strings. Don't pipe responses anywhere that could print the token (it is never in a response).

## Procedure: proposal document (default)

**1. Intake and edit.** Follow "Intake" and "Edit their input" above.

**2. Dry run.** Build the five field values below and show the user the exact text that will appear, the total, and the terms, plus your one-line note on what you changed. Wait for a yes, unless the user has already told you to proceed.

| custom field (key) | dataType | value |
|---|---|---|
| Proposal intro (`contact.proposal_intro`) | LARGE_TEXT | the edited intro |
| Proposal scope (`contact.proposal_scope`) | LARGE_TEXT | the scope lines, one per line, joined with `\n` |
| Proposal total (`contact.proposal_total`) | TEXT | `$3,500` (thousands commas, no cents if whole, `$0` if free) |
| Proposal terms (`contact.proposal_terms`) | LARGE_TEXT | the terms, one per line, then `Assumes: ...` for each assumption the user stated, joined with `\n` |
| Proposal valid through (`contact.proposal_valid_through`) | TEXT | today + valid days, in the **user's local date** (`date +%F`, not UTC), written as `October 3, 2026`. Date maths: `date -v+14d +%F` on macOS, `date -d '+14 days' +%F` on Linux/Git Bash. |

**3. Look up ids** (all reads):
- Custom fields: `ghl "$B/locations/$GHL_LOCATION_ID/customFields"` (under `customFields`) → match `fieldKey` to the five keys above and note each `id`. Create any missing one: `POST $B/locations/$GHL_LOCATION_ID/customFields` with `{"name":"Proposal intro","dataType":"LARGE_TEXT","model":"contact"}` (response `customField.id`).
- Template: `ghl "$B/proposals/templates?locationId=$GHL_LOCATION_ID&limit=20&skip=0"` (the list is under `data`) → the entry with `"type":"proposal"`, `"deleted":false` and name `Proposal` (case-insensitive) → its `_id`. If none, stop: the template isn't built (`template/README.md`).
- User id: `ghl "$B/users/?locationId=$GHL_LOCATION_ID"` (the list is under `users`) → `users[0].id`.

**4. Contact.** `POST $B/contacts/upsert` with `{"locationId":"...","name":"...","email":"...","companyName":"...","phone":"..."}` (omit `phone` if unknown) → `contact.id`. Upsert matches on email, so it's safe to repeat.

**5. Write the fields.** `PUT $B/contacts/<contactId>` with `{"customFields":[{"id":"<fieldId>","field_value":"..."}, ...five...]}`. Then `GET $B/contacts/<contactId>` and confirm each of the five values in `contact.customFields[]` (`id`, `value`) is exactly what you wrote. If any differ, stop and report.

**6. Create the draft, once.**
1. First check nothing was already created for this client in this run: `ghl "$B/proposals/document?locationId=$GHL_LOCATION_ID&limit=20&skip=0"` (the list is under `documents`; every one is named `Proposal`, so match on the contact). A document with this contact's id in `recipients[].id` and `createdAt` within the last 10 minutes means it already exists. Use it; do not create another. Read `skip=20`, `skip=40` too if the whole page is that recent. **Skip this check** only if the user explicitly asked for a second proposal for the same client.
2. Otherwise: `POST $B/proposals/templates/send` with `{"templateId":"...","userId":"...","locationId":"...","contactId":"...","sendDocument":false}` → `document._id`. **`sendDocument` must be `false`.**

**7. Verify** (do all; don't skip):
- The document appears in the list from 6.1 with `"status":"draft"` and the contact in `recipients`.
- The stored copies: the create response has a `document.versionHistory` array (currently two entries a fraction of a second apart). Fetch **every** entry's `downloadUrl` with plain `curl -sS "<url>"` (no auth header). Each must contain all five `{{contact.proposal_...}}` placeholders and a node with `"type":"Signature"`. If a placeholder is missing, the template was edited wrongly; say so.
- The API cannot show how the merge renders. **Tell the user to open it** (Payments > Documents & Contracts > Documents), check the names and text filled in, the layout, and that the signature is on its own page, then send.

**8. Log the run.** Append one line: `echo "$(date -u +%FT%TZ) | ok | <company> (<contact name>) | <total> | doc <id>" >> runs.log` (or `failed | <what>`). Times in this log are UTC.

## Failures

- **Retry** (max 3 times, waiting 2s, 4s, then 8s with `sleep`): HTTP 429, 5xx, a network error, **or a 401 whose message says "timed out"** (GHL's gateway sometimes reports a backend timeout as a 401; the token is fine). Before retrying any create, re-run the existence check in 6.1: a 5xx can hide a write that succeeded.
- **Stop and tell the user, no retry, no workaround:** any other 4xx. Give the exact error and the fix:

| you see | meaning / fix |
|---|---|
| 401 / 403 (not "timed out") | token invalid, revoked, or missing a scope. Edit or recreate it in the sub-account: Settings > Private Integrations. It needs: contacts.readonly, contacts.write, locations.readonly, users.readonly, locations/customFields.readonly, locations/customFields.write, all Documents & Contracts entries (documents and templates), and for estimates invoices/estimate.readonly and invoices/estimate.write. |
| 401 "Location is not active" | the sub-account is deactivated (e.g. an expired trial) or the token belongs to another location. |
| 422 "title/name must be shorter than or equal to 40 characters" | estimates only: shorten it. |
| 422 "limit must not be greater than 21" | list calls: use `limit=20`. |
| 400 "Estimate number already exists" | pick another `estimateNumber`, or omit it. |

- If a run fails midway, report which steps completed (contact, fields, document) and that re-running is safe: upsert is idempotent and step 6.1 prevents a duplicate.
- Nothing watches for failures when you're not in the session; the user finds out because you tell them. Say so if they ask about alerts.

## Procedure: estimate (only if the user asks for an estimate)

Same steps 1-2 (no custom fields or template); for an estimate the user must give each line's name, description and amount. Then:

1. Contact: step 4.
2. `POST $B/invoices/estimate` with:
   `altId` = location id, `altType` `"location"`, `liveMode` `true`, `currency` `"USD"`, `name` and `title` (**each 40 characters max**; put a run id like `p-1a2b3c4d` in `name` and in `meta`: `{"runId":"p-1a2b3c4d"}`), `businessDetails` `{"name":"<location name>"}`, `contactDetails` `{"id","name","email","phoneNo":"","companyName"}`, `items` `[{"name","description","currency":"USD","amount":750,"qty":1,"type":"one_time"}]`, `discount` `{"type":"percentage","value":0}`, `frequencySettings` `{"enabled":false,"schedule":{}}`, `termsNotes` (HTML: intro, assumptions, terms), `userId`, `issueDate` and `expiryDate` (**required**, `YYYY-MM-DD`), optional `estimateNumber` (integer; must be unused).
3. Idempotency: before creating, `GET $B/invoices/estimate/list?altId=$GHL_LOCATION_ID&altType=location&limit=20&offset=0&search=<runId>` and look for `meta.runId`.
4. Verify from that same list: right contact, `total` equals your sum, items match, `estimateStatus` is `draft`. There is no get-by-id endpoint.
5. Link: `https://app.gohighlevel.com/v2/location/$GHL_LOCATION_ID/payments/v2/estimates/edit/<estimateId>`.
6. Send only on an explicit yes: `POST $B/invoices/estimate/<id>/send` with `{"altId","altType":"location","action":"email","liveMode":true,"userId","estimateName"}`. Refuse placeholder addresses (`example.com` etc.).

## Cleaning up test data

There is no API to delete documents; the user deletes them in the GHL UI. Estimates: `DELETE $B/invoices/estimate/<id>` with body `{"altId":"...","altType":"location"}`.
