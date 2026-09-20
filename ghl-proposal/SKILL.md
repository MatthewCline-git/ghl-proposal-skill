---
name: ghl-proposal
description: Draft a client proposal from call notes and create it as a real, priced estimate in GoHighLevel, verified and logged. Use when asked to write, generate, or send a proposal or estimate for a GHL client or prospect, or to check on failed or stuck proposal runs.
---

# GHL proposal

You draft. The script executes. Everything that must not be improvised — prices,
API calls, retries, verification, alerting — lives in `scripts/create_proposal.py`.

## Setup (once)

Needs `GHL_TOKEN` (a sub-account Private Integration Token) and `GHL_LOCATION_ID`
as environment variables or in a `.env` next to this file. Scopes: contacts
read/write, `invoices/estimate` read/write, users read (or set `GHL_USER_ID`).
Python 3, standard library only. Never print or echo the token.

Optional alerts: `ALERT_WEBHOOK_URL` (Slack-compatible) and/or `ALERT_EMAIL` +
`RESEND_API_KEY`. With neither, alerts only reach `runs/alerts.log`.

## Workflow

1. **Collect** from the user: client name, company, email (phone optional) and
   the call notes. If the notes don't say what was discussed, ask — don't invent scope.
2. **Read `rate_card.json`** — the user's default price list. Use its skus where
   they fit. If the user gives a different price, or something that isn't on the
   card, use an `amount` override or a custom line (`name`, `description`,
   `amount`). **Every number on a proposal must be one the user gave you or that is
   on the card. Never estimate, round or invent a price;** if a price is missing,
   ask.
3. **Write a spec** to a temp file (see `examples/sample-spec.json`):
   - `intro`: 2–3 plain sentences in the client's own words — what they told us
     and why this scope. No sales copy, no jargon.
   - `items`: chosen `sku`s, each with an optional one-sentence `note` tying it to
     something they actually said. Only add `amount` when the user stated it.
   - `assumptions`: only ones the notes support.
   - `estimate_number` (optional): integer shown on the estimate. Omit to use GHL's running counter (which never reuses deleted numbers). GHL rejects one already in use.
   - `terms` (optional): replaces the rate card's standard terms for this proposal, e.g. for a free or unusual deal. Amount 0 is allowed.
4. **Dry run first:** `python3 scripts/create_proposal.py spec.json --dry-run`.
   Show the user the priced lines (with where each price came from) and the total; get a yes. That confirmation is the check on prices.
5. **Create:** same command without `--dry-run`. This makes a *draft* estimate
   in GHL and reads it back from GHL to verify contact, line items, total and text.
6. **Send only if the user explicitly says send:** add `--send`. It refuses
   placeholder addresses.

## Reporting results

Report only what the script's JSON says. `status: success` or `recovered` means
the estimate exists in GHL and was verified — say the estimate number and total, and give the user the `url` (opens the estimate in their GHL).
Say "draft, not sent" unless `sent: true`.

- `recovered`: it hit transient errors, retried, and verified. Mention the retry count.
- `failed`: the run stopped, an alert was written, and nothing partial is left
  behind. Give the user `error`, `runbook` section, and the `resume` command.
  Do **not** retry in a loop or work around it; follow `RUNBOOK.md`.
- `invalid_spec`: your spec was wrong and nothing was touched. Fix it and rerun.
- If `alert_delivered` shows only `log`, tell the user no push channel is configured.

## Failure demo

To show the failure handling on request: `--inject transient` (fake 503s that
retry and recover) or `--inject hard` (revoked token: a real 401 from GHL, run
stops and alerts). Resume the hard one by rerunning with the same `--run-id`
and no `--inject` — it will not create a duplicate.

## Watching for stuck runs

`python3 scripts/watchdog.py` alerts on runs that started and never finished, and
on failures left unresolved. Schedule it (cron/launchd or a Claude routine).
Every run is logged to `runs/runs.jsonl`.
