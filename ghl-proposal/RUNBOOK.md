# Runbook — GHL proposal agent

Every alert names one of these sections. Every failure is safe to resume: rerun
the same command with `--run-id <id from the alert>`; the agent checks GHL for an
estimate with that id before creating anything, so nothing is duplicated.

## Alert practice
- **Who gets it:** whoever owns the integration, in the channel set by
  `ALERT_WEBHOOK_URL` / `ALERT_EMAIL`. Every alert also lands in `runs/alerts.log`.
- **What triggers one:** a run that failed, a run that recovered from retries
  (info), and — via `scripts/watchdog.py` — a run that never finished or a
  failure nobody has resolved.
- **Response target (owner's commitment, adjust to your engagement):**
  acknowledge same business day; resolve credential/payload issues the same day.
- **Nothing fails silently:** a stuck or failed run is either alerted in the run
  itself or caught by the watchdog on its next pass.

## §1 credentials (401/403)
GHL rejected the token. It was revoked, rotated, expired or lacks a scope.
1. GHL sub-account > Settings > Private Integrations: confirm the integration exists.
2. Create a new token with contacts, `invoices/estimate` and users scopes.
3. Update `GHL_TOKEN`, then resume with the run id.

## §2 payload rejected (400/422)
GHL refused the estimate's content; the error text names the field. Fix the spec
(or `rate_card.json`), then resume. A 400 "Estimate number already exists" means the `estimate_number` in the spec is taken: pick another or omit it. If it's a field this script builds, that's a bug
to fix in `create_proposal.py`, not to work around by hand.

## §3 GHL unavailable (429/5xx after retries)
The script already retried 3 times with backoff. Check GHL's status page. Resume
when it's back. Nothing was created that the resume won't find.

## §4 verification mismatch
GHL accepted the write but what exists differs from what was requested (wrong
contact, total, or items). The alert lists the differences. **Do not send the
estimate.** Delete it in GHL, then resume with the same run id.

## §5 anything else
Read the last events for the run id in `runs/runs.jsonl`. If a run started and
never finished, the process died mid-flight — resume with the same run id.
