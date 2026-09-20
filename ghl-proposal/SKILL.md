---
name: ghl-proposal
description: Draft a client proposal from call notes and create it in GoHighLevel as a draft proposal document (from the user's template) or a priced estimate, verified and logged. Use when asked to write, generate, or send a proposal or estimate for a GHL client or prospect, or to check on failed or stuck proposal runs.
---

# GHL proposal

You draft. The script executes. Everything that must not be improvised — API
calls, retries, the duplicate guard, verification, alerting — lives in
`scripts/create_proposal.py`. Prices and terms come from the user, never from you.

## Setup (once)

Needs `GHL_TOKEN` (a sub-account Private Integration Token) and `GHL_LOCATION_ID`
in a `.env` next to this file, and a one-time proposal template named `Proposal`
(see `template/README.md`). `python3 scripts/check_setup.py` verifies all of it
and says what to fix. If setup isn't done, follow the repo's `ONBOARDING.md`
(github.com/MatthewCline-git/ghl-proposal-skill). Python 3, standard library only. Never print or echo the token.

Optional alerts: `ALERT_WEBHOOK_URL` (Slack-compatible) and/or `ALERT_EMAIL` +
`RESEND_API_KEY`. With neither, alerts only reach `runs/alerts.log`.

## What a proposal needs

Exactly what the template merges in, and nothing else:

| item | source |
|---|---|
| client name, company, email (phone optional) | the user |
| **intro**: what they told us and why this scope | the user's notes; you write it |
| **scope**: what will be delivered, one line each | the user; you write the lines |
| **total**: one price | the user, verbatim; 0 is fine |
| **terms**: how they get paid, anything else standard | the user, verbatim, or the saved defaults in `defaults.json` |
| **valid for** N days | the user, else `defaults.json` (14) |

## Intake: ask once, all up front

1. Pull everything above out of the user's message. Raw call notes are the input for the intro and scope; don't make them restate it.
2. If anything is missing, send **one** message: a line on what you already have, then only the missing items as a short numbered list with an example each (e.g. "Total price, one number: 3,500"). Say one free-form reply covering all of it is fine. Never ask one question at a time, and don't start creating anything until you have it all.
3. Never invent a price, a term, a deliverable or a client detail. A missing price or term is a question, not a guess.

## Edit their input

Their wording will be rough. Turn it into proposal-ready text:
- **intro**: 2-3 plain sentences in the client's own words: what they told us and why this scope. No sales copy.
- **scope**: one specific, plain deliverable per line.
- **terms**: as stated, tidied.

You may fix grammar, tighten, reorder and drop chatter. You may **not** change the meaning, change any number, or add a commitment, deliverable or assumption they didn't state. The total and the terms are verbatim. Show the result in the dry run and say in one line what you changed; if they want it different, edit and show again.

After the first successful proposal, offer once to save their terms (and validity period) as defaults in `defaults.json` so they don't have to say them again.

## Workflow

1. **Intake and edit** as above. Then write a spec to a temp file (see
   `examples/sample-spec.json`):
   - `client`: `name`, `company`, `email` (`phone` optional)
   - `intro`, `scope` (list of lines), `total` (a number; 0 is fine)
   - `terms` (list; optional only if `defaults.json` has default terms),
     `valid_days` (optional), `assumptions` (optional; only ones the user stated)
2. **Dry run first:** `python3 scripts/create_proposal.py spec.json --dry-run`.
   Show the user the exact text (intro, scope, total, terms, valid-through) and
   your one-line note on what you changed. Get a yes unless they already said go.
3. **Create:** same command without `--dry-run`. By default this fills the user's
   GHL proposal template (`--format document`) and creates a *draft* document for
   the client. Use documents unless the user asks for an estimate.
4. **Estimates** (only if asked): `--format estimate`, with `items` instead of
   `scope`/`total`: each `{name, description, amount, qty}` where the user gave
   every amount (see `examples/sample-estimate-spec.json`). Optional
   `estimate_number` (integer; GHL rejects one already in use).
5. **Sending:** documents are always drafts; the user reviews and presses Send in
   GHL. `--send` exists only for estimates and only if the user explicitly says
   send; it refuses placeholder addresses.

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
