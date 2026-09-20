---
name: ghl-proposal
description: Draft a client proposal from call notes and create it in GoHighLevel as a draft proposal document (from the user's template) or a priced estimate, verified and logged. Use when asked to write, generate, or send a proposal or estimate for a GHL client or prospect, or to check on failed or stuck proposal runs.
---

# GHL proposal

You draft. The script executes. Everything that must not be improvised — prices,
API calls, retries, verification, alerting — lives in `scripts/create_proposal.py`.

## Setup (once)

Needs `GHL_TOKEN` (a sub-account Private Integration Token) and `GHL_LOCATION_ID`
in a `.env` next to this file, and a one-time proposal template named `Proposal`
(see `template/README.md`). `python3 scripts/check_setup.py` verifies all of it
and says what to fix. If setup isn't done, follow the repo's `ONBOARDING.md`
(github.com/MatthewCline-git/ghl-proposal-skill). Python 3, standard library only. Never print or echo the token.

Optional alerts: `ALERT_WEBHOOK_URL` (Slack-compatible) and/or `ALERT_EMAIL` +
`RESEND_API_KEY`. With neither, alerts only reach `runs/alerts.log`.

## Workflow

1. **Collect** from the user: client name, company, email (phone optional) and
   the call notes. If the notes don't say what was discussed, ask — don't invent scope.
2. **Read `rate_card.json`** — the user's default price list. If it says `"configured": false`, run the rate card interview below first. Use its skus where
   they fit. If the user gives a different price, or something that isn't on the
   card, use an `amount` override or a custom line (`name`, `description`,
   `amount`). **Every number on a proposal must be one the user gave you or that is
   on the card. Never estimate, round or invent a price;** if a price is missing,
   ask. **Only include what the notes call for**; if an item looks like a technical
   prerequisite of something they asked for, leave it out and suggest it in the dry
   run instead.
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
5. **Create:** same command without `--dry-run`. By default this fills the user's
   GHL proposal template (`--format document`) and creates a *draft* document for
   the client; `--format estimate` creates a GHL estimate instead. Use documents
   unless the user asks for an estimate.
6. **Sending:** documents are always drafts; the user reviews and presses Send in
   GHL. `--send` exists only for estimates and only if the user explicitly says
   send; it refuses placeholder addresses.

## Rate card interview (when `rate_card.json` says `"configured": false`)

Do this before the first proposal. Ask one question at a time, in plain language, and don't suggest services for them:

1. **What do you sell?** For each service: a short name, one plain sentence a client would understand, and the price. If a service is recurring (monthly), use the first month as the amount and put "then $X/month" in the description.
2. **Standard prices or quoted per job?** For any service they quote each time, leave its `amount` out of the file; you'll ask for the number on every proposal.
3. **Standard terms.** How do they get paid (deposit, on delivery, net 30)? Anything standard about revisions, cancellation or ongoing work? These print on every proposal. A term that applies only with one service is `{"text": "...", "only_with": "<sku>"}`.
4. **How many days** should a proposal stay valid (default 14), and which currency (default USD)?

Then rewrite `rate_card.json` (skus are short lowercase-hyphen slugs, `"configured": true`, `items` may be empty if they quote everything), show it to the user, and get a yes. Until then don't create a proposal.

## Reporting results

Report only what the script's JSON says. `status: success` or `recovered` means
the draft exists in GHL and passed the checks listed in `checked`. Say the total
and, for an estimate, the `url`. Always say it is a draft, not sent. For a
document, also relay `not_checked`: how the merge renders can't be verified by
the API, so tell the user to open it in GHL (Payments > Documents & Contracts >
Documents) before sending. Never claim it looks right.

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
