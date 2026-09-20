# ghl-proposal

A [Claude Code](https://claude.com/claude-code) skill that turns call notes into a priced estimate in your GoHighLevel account. Tell Claude who the client is and what was discussed; it drafts the scope, creates the estimate in GHL, reads it back to verify it, and gives you the link. You review and press Send in GHL.

Free to use (MIT).

## What you get

- **Straight from Claude to GHL.** No copy-paste, no PDF, no template to build.
- **Your prices, not the model's.** Amounts come from your `rate_card.json` or from a number you give. A dry run shows every line and where its price came from before anything is created.
- **Verified.** After creating, it reads the estimate back from GHL and fails loudly if the contact, line items, total or text don't match.
- **Doesn't fail silently.** Transient errors are retried; anything else stops, writes an alert, and tells you the fix ([RUNBOOK.md](ghl-proposal/RUNBOOK.md)). Re-running a failed run never creates a duplicate. A watchdog flags runs that hang.

## Install (5 minutes)

Requires Claude Code and Python 3 (nothing to `pip install`).

```bash
git clone https://github.com/MatthewCline-git/ghl-proposal-skill.git
ln -s "$PWD/ghl-proposal-skill/ghl-proposal" ~/.claude/skills/ghl-proposal
cd ghl-proposal-skill/ghl-proposal && cp .env.example .env
```

1. In GHL, open the sub-account: **Settings → Private Integrations → Create new integration.** Grant view + edit on Contacts and Invoices/Estimates, and view on Locations and Users. Copy the token (shown once) into `.env` as `GHL_TOKEN`.
2. Put the sub-account id (the `<id>` in `app.gohighlevel.com/v2/location/<id>/...`) in `.env` as `GHL_LOCATION_ID`.
3. Edit `rate_card.json`: your services, descriptions, prices and standard terms. The shipped ones are placeholders.
4. Restart Claude Code so it picks up the skill.

## Use

In Claude Code:

> /ghl-proposal Proposal for Dana Reyes, Reyes Roofing, dana@reyesroofing.com. Notes: crew is on roofs all day so calls go to voicemail; leads go cold for two days; no idea which jobs come from where.

Claude shows the priced lines for approval, creates a **draft** estimate, and returns a link like `.../payments/v2/estimates/edit/<id>`. Open it in GHL, review, and send. To use a price other than the rate card's, or an item that isn't on it, just tell Claude the number.

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

- It creates **estimates**, GHL's priced-quote object (accepted estimates convert to invoices). It does not create Documents & Contracts e-signature proposals: GHL's public API can send an existing template but can't create one or fill its content.
- It creates drafts. Sending is your call, in GHL.
- Not affiliated with HighLevel.
