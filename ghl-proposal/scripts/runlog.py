"""Run log + alerting. Append-only JSONL so a crashed run still leaves a
`start` event with no `finish` — which is exactly what the watchdog looks for.
A workflow that fails silently and sits for two weeks is the failure this file
exists to prevent."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from ghl import NETWORK_ERRORS, http

RUNS_DIR = Path(os.environ.get("GHL_PROPOSAL_RUNS_DIR")
                or Path(__file__).resolve().parent.parent / "runs")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def event(run_id: str, kind: str, **fields) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNS_DIR / "runs.jsonl", "a") as f:
        f.write(json.dumps({"ts": _now(), "run_id": run_id, "event": kind, **fields}) + "\n")


def read_events() -> list[dict]:
    p = RUNS_DIR / "runs.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def alert(run_id: str, level: str, message: str) -> dict:
    """Always written to alerts.log. Pushed to whichever channel is configured:
    ALERT_WEBHOOK_URL (Slack-compatible) and/or ALERT_EMAIL via Resend. Returns
    which channels actually accepted it — a run that reports 'alerted' without
    a delivered channel is lying."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{_now()} [{level}] run={run_id} {message}"
    with open(RUNS_DIR / "alerts.log", "a") as f:
        f.write(line + "\n")
    delivered = {"log": True}
    text = f"[ghl-proposal {level}] {message} (run {run_id})"

    hook = os.environ.get("ALERT_WEBHOOK_URL")
    if hook:
        try:
            delivered["webhook"] = http("POST", hook, headers={"Content-Type": "application/json"},
                                        body={"text": text}, timeout=10)[0] < 300
        except NETWORK_ERRORS + (ValueError,):
            delivered["webhook"] = False

    to, key = os.environ.get("ALERT_EMAIL"), os.environ.get("RESEND_API_KEY")
    if to and key:
        try:
            code, _ = http("POST", "https://api.resend.com/emails",
                           headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                           body={"from": os.environ.get("ALERT_FROM", "onboarding@resend.dev"),
                                 "to": [to], "subject": f"[{level}] proposal agent", "text": text},
                           timeout=10)
            delivered["email"] = code < 300
        except NETWORK_ERRORS + (ValueError,):
            delivered["email"] = False
    return delivered


def stuck_runs(max_age_min: float) -> list[dict]:
    """Runs that started and never finished, older than the threshold."""
    by_run: dict[str, dict] = {}
    for e in read_events():
        r = by_run.setdefault(e["run_id"], {"run_id": e["run_id"], "finished": False})
        if e["event"] == "start":
            r["started"] = e["ts"]
        if e["event"] == "finish":
            r["finished"] = True
    out = []
    for r in by_run.values():
        if r["finished"] or "started" not in r:
            continue
        age = (time.time() - datetime.fromisoformat(r["started"]).timestamp()) / 60
        if age >= max_age_min:
            out.append({**r, "age_min": round(age, 1)})
    return out


def unresolved_failures(max_age_min: float) -> list[dict]:
    """Runs whose last finish was `failed` and never succeeded afterwards."""
    last: dict[str, dict] = {}
    for e in read_events():
        if e["event"] == "finish":
            last[e["run_id"]] = e
    out = []
    for e in last.values():
        if e.get("status") != "failed":
            continue
        age = (time.time() - datetime.fromisoformat(e["ts"]).timestamp()) / 60
        if age >= max_age_min:
            out.append({"run_id": e["run_id"], "failed_at": e["ts"], "age_min": round(age, 1),
                        "error": e.get("error", "")})
    return out
