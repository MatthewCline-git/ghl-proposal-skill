# ghl-proposal

A [Claude Code](https://claude.com/claude-code) skill that turns call notes into a proposal in your GoHighLevel account. Tell Claude who the client is and what was discussed; it drafts the scope, fills your GHL proposal template, creates the draft for the client, and checks what landed. You review it and press Send in GHL.

Free to use (MIT).

## What you get

- **Straight from Claude to GHL.** No copy-paste and no PDF. (One template is built once, by hand.)
- **Your prices, not the model's.** Amounts come from your `rate_card.json` or from a number you give. A dry run shows every line and where its price came from before anything is created.
- **Verified.** After creating, it reads what landed back from GHL and fails loudly if the contact, fields, template or signature field are wrong.
- **Doesn't fail silently.** Transient errors are retried; anything else stops, writes an alert, and tells you the fix ([RUNBOOK.md](ghl-proposal/RUNBOOK.md)). Re-running a failed run never creates a duplicate. A watchdog flags runs that hang.

## Set up (about 10 minutes)

The easiest way is to let Claude walk you through it. Open Claude Code (the Code tab in the Claude desktop app, or a terminal) and paste:

> Set up the ghl-proposal skill for me. Fetch https://raw.githubusercontent.com/MatthewCline-git/ghl-proposal-skill/main/ONBOARDING.md and follow it exactly, one step at a time.

It installs the skill, sends you to the right GHL pages, and checks each step. You'll need to: create a token in GHL, paste it into a file (never into chat), build one proposal template, and **fully quit and reopen the app** so it picks up the skill.

Prefer to do it yourself? Follow [ONBOARDING.md](ONBOARDING.md); the steps read fine for a person too.

## Use

In Claude Code:

> /ghl-proposal Proposal for Dana Reyes, Reyes Roofing, dana@reyesroofing.com. Notes: crew is on roofs all day so calls go to voicemail; leads go cold for two days; no idea which jobs come from where.

Claude shows the priced lines for approval, then creates a **draft** proposal document for the client. Open it in GHL (Payments → Documents & Contracts → Documents), review, and send. Ask for an estimate instead and it creates a GHL estimate, returning a direct link. To use a price other than the rate card's, or an item that isn't on it, just tell Claude the number.

## See how it handles failure

Ask Claude to run the failure demo, or run the script directly:

```bash
cd ghl-proposal
python3 scripts/create_proposal.py examples/sample-spec.json --dry-run
python3 scripts/create_proposal.py examples/sample-spec.json --inject transient   # fake outage: retries, recovers
python3 scripts/create_proposal.py examples/sample-spec.json --inject hard        # revoked token: real 401, stops, alerts
```

Alerts always go to `runs/alerts.log`. To get them pushed, set `ALERT_WEBHOOK_URL` (Slack-compatible) or `ALERT_EMAIL` + `RESEND_API_KEY`. Schedule `python3 scripts/watchdog.py` (cron, launchd or a Claude routine) to catch runs that started and never finished.

## Limits

- **Proposals** use a template you build once in GHL (GHL's public API can't create or edit templates). The skill fills it through contact custom fields and creates a draft from it. Only the text fields vary per proposal; layout and signature are fixed in the template.
- **Estimates** are the alternative: fully API-driven, no template needed, and an accepted estimate converts to an invoice.
- Everything is created as a draft. Sending is your call, in GHL.
- The API can't tell whether the merge rendered well, so open each draft before sending.
- Not affiliated with HighLevel.
